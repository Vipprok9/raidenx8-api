import os, time, json, requests
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from flask_socketio import SocketIO, emit

PROVIDER = os.getenv("PROVIDER", "openai").lower()   # "openai" | "gemini"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.0-pro-exp-02-05")

COINGECKO_API = "https://api.coingecko.com/api/v3/simple/price"

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

SYSTEM_PROMPT = (
  "Bạn là RaidenX8 – trả lời ngắn gọn, cụ thể, không vòng vo. "
  "Nếu không có dữ liệu thời gian thực thì nêu giới hạn và gợi ý cách kiểm tra."
)

# ---------- Helpers ----------
def call_openai_chat(text, stream=False):
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": OPENAI_MODEL,
        "messages": [{"role":"system","content":SYSTEM_PROMPT},
                     {"role":"user","content":text}],
        "temperature": 0.7,
        "stream": bool(stream),
    }
    r = requests.post(url,
                      headers={"Authorization": f"Bearer {OPENAI_API_KEY}",
                               "Content-Type": "application/json"},
                      json=payload, stream=stream, timeout=90)
    return r

def call_gemini_stream(text):  # SSE (alt=sse)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:streamGenerateContent?alt=sse&key={GEMINI_API_KEY}"
    payload = {"contents":[{"role":"user","parts":[{"text": text}]}]}
    r = requests.post(url,
                      headers={"Content-Type":"application/json"},
                      json=payload, stream=True, timeout=90)
    return r

def call_gemini_once(text):    # 1 phát, không stream
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents":[{"role":"user","parts":[{"text": text}]}]}
    r = requests.post(url,
                      headers={"Content-Type":"application/json"},
                      json=payload, timeout=60)
    return r

# ---------- Health ----------
@app.get("/health")
def health():
    return {"ok": True, "provider": PROVIDER,
            "model": OPENAI_MODEL if PROVIDER=="openai" else GEMINI_MODEL}

# ---------- Prices ----------
@app.get("/prices")
def prices():
    ids = request.args.get("ids","bitcoin,ethereum,binancecoin,solana,toncoin,tether")
    vs  = request.args.get("vs","usd")
    r = requests.get(COINGECKO_API, params={"ids":ids,"vs_currencies":vs}, timeout=12)
    return r.json(), r.status_code

# ---------- AI (HTTP once) ----------
@app.post("/ai/chat")
def http_chat():
    msg = (request.get_json(force=True).get("message") or "").strip()
    if not msg: return {"error":"Empty message"}, 400

    if PROVIDER=="openai":
        if not OPENAI_API_KEY: return {"error":"Missing OPENAI_API_KEY"}, 400
        r = call_openai_chat(msg, stream=False)
        j = r.json()
        if r.status_code>=400: return j, r.status_code
        return {"reply": j["choices"][0]["message"]["content"]}
    else:
        if not GEMINI_API_KEY: return {"error":"Missing GEMINI_API_KEY"}, 400
        r = call_gemini_once(msg)
        j = r.json()
        if r.status_code>=400: return j, r.status_code
        parts = j["candidates"][0]["content"]["parts"]
        txt = "".join(p.get("text","") for p in parts)
        return {"reply": txt}

# ---------- AI (SSE stream) ----------
@app.post("/ai/stream")
def http_stream():
    msg = (request.get_json(force=True).get("message") or "").strip()

    def gen_openai():
        with call_openai_chat(msg, stream=True) as resp:
            for line in resp.iter_lines(decode_unicode=True):
                if not line: continue
                yield line + "\n\n"  # đã ở dạng 'data: {...}' / '[DONE]'

    def gen_gemini():
        # Gemini SSE: mỗi dòng 'data: {...}' với parts[].text
        with call_gemini_stream(msg) as resp:
            for raw in resp.iter_lines(decode_unicode=True):
                if not raw or not raw.startswith("data: "): continue
                data = raw[6:]
                try:
                    j = json.loads(data)
                    parts = j.get("candidates",[{}])[0].get("content",{}).get("parts",[])
                    for p in parts:
                        t = p.get("text")
                        if t:
                            yield "data: " + json.dumps({"choices":[{"delta":{"content": t}}]}) + "\n\n"
                except Exception:
                    continue
            yield "data: [DONE]\n\n"

    if PROVIDER=="openai":
        return Response(gen_openai(), mimetype="text/event-stream")
    else:
        return Response(gen_gemini(), mimetype="text/event-stream")

# ---------- WebSocket 2 chiều ----------
@socketio.on("connect")
def on_connect():
    emit("server_info", {"ok": True, "provider": PROVIDER})

@socketio.on("user_message")
def ws_user_message(data):
    msg = (data.get("message") or "").strip()
    if not msg: 
        emit("bot_done", {"reply":"(trống)"}); return

    if PROVIDER=="openai":
        if not OPENAI_API_KEY:
            emit("bot_done", {"reply":"Thiếu OPENAI_API_KEY."}); return
        try:
            with call_openai_chat(msg, stream=True) as resp:
                full=[]
                for line in resp.iter_lines(decode_unicode=True):
                    if not line or not line.startswith("data: "): continue
                    chunk=line[6:]
                    if chunk=="[DONE]": break
                    try:
                        j=json.loads(chunk)
                        delta=j["choices"][0]["delta"].get("content")
                        if delta:
                            full.append(delta); emit("bot_delta",{"delta":delta})
                    except: pass
                emit("bot_done", {"reply":"".join(full)})
        except Exception as e:
            emit("bot_done", {"reply": f"Lỗi: {e}"})
    else:
        if not GEMINI_API_KEY:
            emit("bot_done", {"reply":"Thiếu GEMINI_API_KEY."}); return
        try:
            with call_gemini_stream(msg) as resp:
                full=[]
                for raw in resp.iter_lines(decode_unicode=True):
                    if not raw or not raw.startswith("data: "): continue
                    try:
                        j=json.loads(raw[6:])
                        parts=j.get("candidates",[{}])[0].get("content",{}).get("parts",[])
                        for p in parts:
                            t=p.get("text")
                            if t:
                                full.append(t); emit("bot_delta",{"delta":t})
                    except: pass
                emit("bot_done", {"reply":"".join(full)})
        except Exception as e:
            emit("bot_done", {"reply": f"Lỗi: {e}"})

# ---------- TTS (OpenAI) ----------
@app.post("/api/tts")
def tts():
    # Gemini chưa có TTS trong API public; giữ TTS bằng OpenAI (hoặc dùng Web Speech ở frontend)
    if not OPENAI_API_KEY:
        return {"error":"TTS yêu cầu OPENAI_API_KEY (gpt-4o-mini-tts)."}, 400
    text = (request.get_json(force=True).get("text") or "").strip()
    voice = request.json.get("voice","alloy")
    url = "https://api.openai.com/v1/audio/speech"
    payload={"model":"gpt-4o-mini-tts","voice":voice,"input":text,"format":"mp3"}
    r=requests.post(url, headers={"Authorization": f"Bearer {OPENAI_API_KEY}",
                                  "Content-Type":"application/json"},
                    json=payload, timeout=120)
    if r.status_code>=400: return r.json(), r.status_code
    fn=f"tts_{int(time.time())}.mp3"
    return Response(r.content, mimetype="audio/mpeg",
                    headers={"Content-Disposition": f'inline; filename="{fn}"'})

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 7860)))
