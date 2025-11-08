import os, json, time, requests
from io import BytesIO
from flask import Flask, request, Response, send_file, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from gtts import gTTS

# ====== ENV ======
PROVIDER        = os.getenv("PROVIDER", "gemini")       # "gemini" | "openai"
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL    = os.getenv("GEMINI_MODEL", "models/gemini-2.0-flash")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "*")

COINGECKO_API   = "https://api.coingecko.com/api/v3/simple/price"

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*")  # for realtime typing/bubbles etc.

SYSTEM_PROMPT = (
    "Bạn là RaidenX8 — trả lời ngắn gọn, đúng trọng tâm, giọng trẻ trung."
    "Nếu câu hỏi đòi realtime (thời tiết/giá coin...), nói rõ bạn không có dữ liệu thời gian thực"
    " và chỉ đưa hướng kiểm tra nhanh (CoinGecko, CMC, sàn, v.v.)."
)

# ---------- Helpers ----------
def call_openai_chat(text: str, stream: bool = False):
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role":"system","content":SYSTEM_PROMPT},
            {"role":"user","content":text}
        ],
        "temperature": 0.7,
        "stream": bool(stream),
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    return requests.post(url, headers=headers, json=payload, stream=stream)

def call_gemini_once(text: str):
    url = f"https://generativelanguage.googleapis.com/v1beta/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents":[{"role":"user","parts":[{"text": f"{SYSTEM_PROMPT}\n\nUser: {text}"}]}]}
    return requests.post(url, headers={"Content-Type":"application/json"}, json=payload)

def call_gemini_stream(text: str):
    # SSE-like stream from Gemini (chunked JSON lines)
    url = f"https://generativelanguage.googleapis.com/v1beta/{GEMINI_MODEL}:streamGenerateContent?alt=sse&key={GEMINI_API_KEY}"
    payload = {"contents":[{"role":"user","parts":[{"text": f"{SYSTEM_PROMPT}\n\nUser: {text}"}]}]}
    headers = {"Content-Type":"application/json"}
    return requests.post(url, headers=headers, json=payload, stream=True)

# ---------- Health ----------
@app.get("/health")
def health():
    return {"ok": True, "provider": PROVIDER, "model": (OPENAI_MODEL if PROVIDER=="openai" else GEMINI_MODEL)}

# ---------- Prices ----------
@app.get("/prices")
def prices():
    ids = request.args.get("ids","bitcoin,ethereum,binancecoin,solana,toncoin")
    vs  = request.args.get("vs","usd")
    r = requests.get(COINGECKO_API, params={"ids": ids, "vs_currencies": vs})
    return (r.json(), r.status_code)

# ---------- AI (HTTP once) ----------
@app.post("/ai/chat")
def http_chat():
    data = request.get_json(silent=True) or {}
    msg  = (data.get("message") or "").strip()
    if not msg:
        return {"error":"Empty message"}, 400

    if PROVIDER == "openai":
        if not OPENAI_API_KEY: return {"error":"OPENAI_API_KEY missing"}, 400
        r = call_openai_chat(msg, stream=False)
        if r.status_code >= 400: return (r.text, r.status_code)
        j = r.json()
        reply = j["choices"][0]["message"]["content"]
        return {"reply": reply}
    else:
        if not GEMINI_API_KEY: return {"error":"GEMINI_API_KEY missing"}, 400
        r = call_gemini_once(msg)
        if r.status_code >= 400: return (r.text, r.status_code)
        j = r.json()
        parts = j.get("candidates",[{}])[0].get("content",{}).get("parts",[])
        reply = "".join(p.get("text","") for p in parts)
        return {"reply": reply}

# ---------- AI (SSE stream) ----------
@app.post("/ai/stream")
def http_stream():
    data = request.get_json(silent=True) or {}
    msg  = (data.get("message") or "").strip()
    if not msg:
        return {"error":"Empty message"}, 400

    def sse_from_openai():
        resp = call_openai_chat(msg, stream=True)
        for line in resp.iter_lines():
            if not line: continue
            # OpenAI streams as "data: {...}"
            yield line.decode("utf-8") + "\n\n"

    def sse_from_gemini():
        resp = call_gemini_stream(msg)
        for raw in resp.iter_lines():
            if not raw: continue
            row = raw.decode("utf-8")
            if not row.startswith("data: "):  # keep SSE shape
                yield f"data: {row}\n\n"
            else:
                yield row + "\n\n"

    generator = sse_from_openai if PROVIDER=="openai" else sse_from_gemini
    return Response(generator(), mimetype="text/event-stream")

# ---------- WebSocket (Socket.IO) ----------
@socketio.on("connect")
def on_connect():
    emit("server_msg", {"type":"status","text":"connected"})

@socketio.on("typing")
def on_typing(data):
    # broadcast typing bubbles
    emit("typing", {"who":"user", "text": data.get("text","")}, broadcast=True)

@socketio.on("chat")
def on_chat(data):
    text = (data.get("text") or "").strip()
    if not text:
        emit("server_msg", {"type":"error","text":"Empty message"})
        return
    # simple non-stream reply over WS (one-shot)
    reply = ""
    try:
        if PROVIDER=="openai":
            r = call_openai_chat(text, stream=False)
            j = r.json()
            reply = j["choices"][0]["message"]["content"]
        else:
            r = call_gemini_once(text)
            j = r.json()
            parts = j.get("candidates",[{}])[0].get("content",{}).get("parts",[])
            reply = "".join(p.get("text","") for p in parts)
    except Exception as e:
        reply = f"Lỗi: {e}"
    emit("reply", {"text": reply}, broadcast=True)

# ---------- TTS (gTTS) ----------
@app.post("/api/tts")
def api_tts():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    lang = data.get("lang","vi")
    if not text:
        return {"error":"Empty text"}, 400
    try:
        tts = gTTS(text=text, lang=lang)
        buf = BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return send_file(buf, mimetype="audio/mpeg", as_attachment=False, download_name="speech.mp3")
    except Exception as e:
        return {"error": str(e)}, 500

# ---------- Root ----------
@app.get("/")
def root():
    return jsonify({"ok": True, "provider": PROVIDER, "model": (OPENAI_MODEL if PROVIDER=="openai" else GEMINI_MODEL)})

if __name__ == "__main__":
    # Local run
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
