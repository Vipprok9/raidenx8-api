import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# Flask init
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Load Gemini key
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

@app.get("/health")
def health():
    return jsonify(status="ok")

@app.get("/")
def home():
    return jsonify(app="RaidenX8 Backend", model=GEMINI_MODEL, ready=bool(GEMINI_KEY))

@app.post("/ai/chat")
def ai_chat():
    """Chat 2 chiều (AI hoặc echo fallback)."""
    data = request.get_json(silent=True) or {}
    user_msg = (data.get("message") or "").strip()
    if not user_msg:
        return jsonify(reply="Xin chào! Bạn muốn hỏi gì nè?")

    # Nếu chưa có key → echo
    if not GEMINI_KEY:
        return jsonify(reply=f"[echo] {user_msg}")

    # Gọi Gemini API (Google AI Studio)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
    payload = {"contents": [{"parts": [{"text": user_msg}]}]}
    try:
        r = requests.post(url, json=payload, timeout=20)
        r.raise_for_status()
        js = r.json()
        reply = js["candidates"][0]["content"]["parts"][0]["text"]
        return jsonify(reply=reply.strip())
    except Exception as e:
        return jsonify(reply=f"(Gemini lỗi hoặc quota hết) {str(e)[:120]}")

# === Socket realtime ===
@socketio.on("connect")
def handle_connect():
    emit("server_message", {"msg": "🔗 Đã kết nối Socket.IO"})

@socketio.on("client_message")
def handle_client_message(data):
    msg = data.get("msg", "")
    emit("server_message", {"msg": f"Echo: {msg}"}, broadcast=True)

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=10000)
