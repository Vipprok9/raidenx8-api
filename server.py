import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# --- INIT ---
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# --- ENV VARS ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# --- ROUTES ---
@app.get("/health")
def health():
    return jsonify(status="ok", model=GEMINI_MODEL, ai=bool(GEMINI_API_KEY))

@app.get("/")
def home():
    return jsonify(app="RaidenX8 Backend", version="v1.0", ready=True)

@app.post("/ai/chat")
def ai_chat():
    data = request.get_json(silent=True) or {}
    msg = (data.get("message") or "").strip()
    if not msg:
        return jsonify(reply="Xin chào, mình là RaidenX8! Bạn muốn hỏi gì nè?")

    # Nếu chưa có key → echo fallback
    if not GEMINI_API_KEY:
        return jsonify(reply=f"[echo] {msg}")

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents": [{"parts": [{"text": msg}]}]}
        res = requests.post(url, json=payload, timeout=20)
        res.raise_for_status()
        data = res.json()
        reply = data["candidates"][0]["content"]["parts"][0]["text"]
        return jsonify(reply=reply.strip())
    except Exception as e:
        return jsonify(reply=f"(Gemini lỗi hoặc quota) {str(e)[:100]}")

# --- SOCKET.IO realtime ---
@socketio.on("connect")
def handle_connect():
    emit("server_message", {"msg": "🔗 Kết nối Socket.IO thành công!"})

@socketio.on("client_message")
def handle_client_message(data):
    msg = data.get("msg", "")
    emit("server_message", {"msg": f"Echo: {msg}"}, broadcast=True)

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=10000)
