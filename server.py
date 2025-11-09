import os, time
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import google.generativeai as genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY","")
GEMINI_MODEL = os.getenv("GEMINI_MODEL","gemini-2.5-flash")

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

@app.get("/health")
def health():
    return jsonify({"ok": True, "gemini": bool(GEMINI_API_KEY), "model": GEMINI_MODEL})

@app.post("/ai/chat")
def ai_chat():
    data = request.get_json(force=True, silent=True) or {}
    msg = data.get("message","")
    mdl = data.get("model") or GEMINI_MODEL
    if not GEMINI_API_KEY:
        return jsonify({"reply": "(demo) WS offline hoặc chưa có GEMINI_API_KEY."})
    m = genai.GenerativeModel(mdl)
    res = m.generate_content(msg)
    text = getattr(res, "text", "(empty)")
    return jsonify({"reply": text})

@socketio.on("chat")
def on_chat(data):
    msg = (data or {}).get("message","")
    mdl = (data or {}).get("model") or GEMINI_MODEL
    emit("bot_typing")
    time.sleep(0.2)
    if not GEMINI_API_KEY:
        emit("bot_message", "(demo) WS offline hoặc chưa có GEMINI_API_KEY.")
        return
    try:
        m = genai.GenerativeModel(mdl)
        res = m.generate_content(msg)
        text = getattr(res, "text", "(empty)")
    except Exception as e:
        text = f"Lỗi: {e}"
    emit("bot_message", text)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    socketio.run(app, host="0.0.0.0", port=port)
