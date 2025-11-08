# -*- coding: utf-8 -*-
import os, json, time, uuid, tempfile, requests
from flask import Flask, request, jsonify, Response, send_file
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# ================== CONFIG ==================
PROVIDER        = os.getenv("PROVIDER", "gemini").lower()   # "gemini" | "openai"
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL    = os.getenv("GEMINI_MODEL", "models/gemini-2.5-pro-preview-03-25")

OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "*")

SYSTEM_GUIDE = (
  "Bạn là RaidenX8. Trả lời ngắn gọn, cụ thể, tránh rào đón. "
  "Không lặp lại câu hỏi. Nếu thiếu dữ liệu thời gian thực, nói thẳng một câu ngắn gọn và gợi ý 1–2 nguồn uy tín."
)

COINGECKO_API = "https://api.coingecko.com/api/v3/simple/price"

# ================== APP ==================
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": [FRONTEND_ORIGIN, "*"]}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# ================== HELPERS ==================
def _ok_api_key():
    if PROVIDER == "gemini": return bool(GEMINI_API_KEY)
    return bool(OPENAI_API_KEY)

# --- Gemini ---
def g_headers(): return {"Content-Type": "application/json; charset=utf-8"}

def g_body(user_text):
    return {
        "contents": [
            {"role": "user", "parts": [{"text": f"{SYSTEM_GUIDE}

Câu hỏi: {user_text}"}]}
        ]
    }

def g_once(text):
    url = f"https://generativelanguage.googleapis.com/v1beta/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    return requests.post(url, headers=g_headers(), json=g_body(text), timeout=60)

def g_stream(text):
    url = f"https://generativelanguage.googleapis.com/v1beta/{GEMINI_MODEL}:streamGenerateContent?alt=sse&key={GEMINI_API_KEY}"
    return requests.post(url, headers=g_headers(), json=g_body(text), stream=True, timeout=300)

# --- OpenAI ---
def o_headers(): return {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type":"application/json"}

def o_payload(user_text, stream=False):
    return {
        "model": OPENAI_MODEL,
        "messages": [
            {"role":"system","content": SYSTEM_GUIDE},
            {"role":"user","content": user_text}
        ],
        "temperature": 0.7,
        "stream": bool(stream)
    }

def o_once(text):
    return requests.post("https://api.openai.com/v1/chat/completions",
                         headers=o_headers(), json=o_payload(text, False), timeout=90)

def o_stream(text):
    return requests.post("https://api.openai.com/v1/chat/completions",
                         headers=o_headers(), json=o_payload(text, True),
                         stream=True, timeout=300)

# ================== ROUTES ==================
@app.get("/health")
def health():
    return jsonify(ok=True,
                   provider=PROVIDER,
                   model=(GEMINI_MODEL if PROVIDER=="gemini" else OPENAI_MODEL))

@app.get("/prices")
def prices():
    ids = request.args.get("ids","bitcoin,ethereum,binancecoin,solana,toncoin,tether")
    vs  = request.args.get("vs","usd")
    r = requests.get(COINGECKO_API, params={"ids": ids, "vs_currencies": vs}, timeout=12)
    return (r.json(), r.status_code)

@app.post("/ai/chat")
def ai_chat():
    data = request.get_json(force=True, silent=True) or {}
    msg = (data.get("message") or "").strip()
    if not msg: return jsonify(error="Empty message"), 400
    if not _ok_api_key(): return jsonify(error="Missing API key"), 400

    try:
        if PROVIDER=="gemini":
            r = g_once(msg)
            if r.status_code>=400: return jsonify(error=r.text), r.status_code
            j = r.json()
            parts = (j.get("candidates") or [{}])[0].get("content",{}).get("parts",[])
            txt = "".join(p.get("text","") for p in parts)
            return {"reply": txt}
        else:
            r = o_once(msg)
            if r.status_code>=400: return r.json(), r.status_code
            j = r.json()
            txt = j["choices"][0]["message"]["content"]
            return {"reply": txt}
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.post("/ai/stream")
def ai_stream():
    data = request.get_json(force=True, silent=True) or {}
    msg = (data.get("message") or "").strip()
    if not msg:
        return Response("data: [DONE]

", mimetype="text/event-stream")

    def sse_gemini():
        if not GEMINI_API_KEY:
            yield "data: {"error":"Missing GEMINI_API_KEY"}

"; return
        with g_stream(msg) as resp:
            for raw in resp.iter_lines(decode_unicode=True):
                if not raw: continue
                yield raw + "\n"
            yield "data: [DONE]\n\n"

    def sse_openai():
        if not OPENAI_API_KEY:
            yield "data: {"error":"Missing OPENAI_API_KEY"}

"; return
        with o_stream(msg) as resp:
            for line in resp.iter_lines(decode_unicode=True):
                if not line: continue
                yield line + "\n"
            yield "data: [DONE]\n\n"

    try:
        if PROVIDER=="gemini":
            return Response(sse_gemini(), mimetype="text/event-stream")
        else:
            return Response(sse_openai(), mimetype="text/event-stream")
    except Exception as e:
        return Response(f"data: {{"error":"{str(e)}"}}\n\n", mimetype="text/event-stream")

# ================== SOCKET.IO ==================
@socketio.on("connect")
def on_connect():
    emit("server_info", {"ok": True, "provider": PROVIDER})

@socketio.on("typing")
def on_typing(data):
    emit("peer_typing", {"on": bool((data or {}).get("on"))})

@socketio.on("user_message")
def on_user_message(data):
    user_msg = (data or {}).get("message","").strip()
    if not user_msg:
        emit("bot_done", {"reply": ""}); return
    emit("bot_typing", {"on": True})

    try:
        if PROVIDER=="gemini":
            with g_stream(user_msg) as resp:
                full=[]
                for raw in resp.iter_lines(decode_unicode=True):
                    if not raw or not raw.startswith("data: "): continue
                    payload = raw[6:]
                    if payload == "[DONE]":
                        break
                    try:
                        j = json.loads(payload)
                        parts = j.get("candidates",[{}])[0].get("content",{}).get("parts",[])
                        for p in parts:
                            t = p.get("text")
                            if t:
                                full.append(t)
                                emit("bot_delta", {"delta": t})
                    except Exception:
                        continue
                emit("bot_done", {"reply": "".join(full)})
        else:
            with o_stream(user_msg) as resp:
                full=[]
                for line in resp.iter_lines(decode_unicode=True):
                    if not line or not line.startswith("data: "): continue
                    chunk = line[6:]
                    if chunk == "[DONE]": break
                    try:
                        j = json.loads(chunk)
                        delta = j["choices"][0]["delta"].get("content")
                        if delta:
                            full.append(delta)
                            emit("bot_delta", {"delta": delta})
                    except Exception:
                        continue
                emit("bot_done", {"reply": "".join(full)})
    except Exception as e:
        emit("bot_done", {"reply": f"Lỗi: {e}"})
    finally:
        emit("bot_typing", {"on": False})

# ================== TTS ==================
@app.post("/api/tts")
def api_tts():
    """Nếu có OPENAI_API_KEY: dùng OpenAI TTS. Không có → fallback gTTS free."""
    text = (request.get_json(force=True).get("text") or "").strip()
    if not text: return jsonify(error="text is required"), 400

    # OpenAI TTS trước
    if OPENAI_API_KEY:
        try:
            r = requests.post("https://api.openai.com/v1/audio/speech",
                              headers=o_headers(),
                              json={"model":"gpt-4o-mini-tts","voice":"alloy","input":text,"format":"mp3"},
                              timeout=120)
            if r.status_code < 400:
                return Response(r.content, mimetype="audio/mpeg",
                                headers={"Content-Disposition": 'inline; filename="tts.mp3"'})
        except Exception:
            pass  # rớt xuống gTTS

    # gTTS fallback
    try:
        from gtts import gTTS
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        gTTS(text=text, lang="vi").write_to_fp(tmp)
        tmp.flush(); tmp.close()
        return send_file(tmp.name, mimetype="audio/mpeg", download_name="tts.mp3")
    except Exception as e:
        return jsonify(error=f"TTS failed: {e}"), 500

@app.get("/")
def root():
    return jsonify(ok=True, provider=PROVIDER, model=(GEMINI_MODEL if PROVIDER=='gemini' else OPENAI_MODEL))

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 7860)))
