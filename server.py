
import os
import time
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import random

# Optional Gemini import (will only be used when API key exists)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL_DEFAULT = os.getenv("MODEL_DEFAULT", "gemini-1.5-flash-8b")
ALLOW_ORIGIN = os.getenv("ALLOW_ORIGIN", "*")

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ALLOW_ORIGIN}})

# Socket.IO set up with eventlet (Render uses Start command: python server.py)
socketio = SocketIO(app, cors_allowed_origins=ALLOW_ORIGIN, async_mode="eventlet")

# Lazy import to avoid hard dependency when no key
genai = None
if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
    except Exception as e:
        genai = None

@app.get("/health")
def health():
    return jsonify({"ok": True, "ws": True, "time": datetime.utcnow().isoformat() + "Z"})

@app.get("/config")
def config():
    return jsonify({
        "model_default": MODEL_DEFAULT,
        "ws_path": "/socket.io/",
        "note": "Set GEMINI_API_KEY to enable Gemini responses."
    })

def simple_reply(text: str) -> str:
    text = (text or "").strip().lower()
    if not text:
        return "Mình đang nghe đây! Hỏi gì cũng được nè."
    if any(k in text for k in ["hi", "chào", "hello"]):
        return "Chào bạn! 👋 Đây là RX∞8 — chat realtime qua WebSocket."
    if "time" in text or "mấy giờ" in text:
        return f"Bây giờ (UTC) là {datetime.utcnow().strftime('%H:%M:%S')}."
    tips = [
        "Bạn có thể bật ví EVM/Phantom ở phần banner.",
        "Gõ nhanh rồi Enter để gửi; mình sẽ hiện hiệu ứng typing.",
        "Slogan: AI × Web3 × Gen‑Z Future ✨",
    ]
    return random.choice(tips)

def gen_gemini_response(text: str, model: str):
    # Fallback to simple when lib/key missing
    if not (GEMINI_API_KEY and genai):
        return simple_reply(text), False
    try:
        model_name = model or MODEL_DEFAULT
        m = genai.GenerativeModel(model_name)
        resp = m.generate_content(text, safety_settings=None)
        out = getattr(resp, "text", None) or simple_reply(text)
        # clean Vietnamese trailing spaces/dots
        out = out.replace(" .", ".").replace(" ,", ",")
        return out, True
    except Exception as e:
        return f"Lỗi gọi Gemini: {e}. {simple_reply(text)}", False

@socketio.on("connect")
def on_connect():
    emit("server_status", {"ok": True, "ts": time.time()})

@socketio.on("chat_message")
def on_chat_message(data):
    text = (data or {}).get("text", "")
    model = (data or {}).get("model", "")
    # push typing hint
    emit("typing", {"state": "start"}, broadcast=False)
    # generate
    reply, used_ai = gen_gemini_response(text, model)
    # stop typing + send reply
    emit("typing", {"state": "stop"}, broadcast=False)
    emit("chat_reply", {"reply": reply, "used_ai": used_ai, "model": model or MODEL_DEFAULT}, broadcast=False)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    # eventlet WSGI via socketio.run
    socketio.run(app, host="0.0.0.0", port=port)
