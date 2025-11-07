from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit

app = Flask(__name__)
CORS(app)

# Socket.IO với gevent (websocket)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent")

@app.get("/health")
def health():
    return jsonify(status="ok")

@app.get("/")
def root():
    return jsonify(app="RaidenX8 API (gevent)", ok=True)

# Demo AI chat (echo) – bạn có thể thay bằng gọi OpenAI/Gemini sau
@app.post("/ai/chat")
def ai_chat():
    data = request.get_json(silent=True) or {}
    user_msg = data.get("message", "")
    return jsonify(reply=f"[echo] {user_msg}")

# ===== Socket.IO =====
@socketio.on("connect")
def on_connect():
    emit("server_message", {"msg": "Connected to RaidenX8 gevent server"})

@socketio.on("client_message")
def on_client_message(data):
    # broadcast tin nhắn mọi người cùng nhận
    emit("server_message", {"msg": data.get("msg", "")}, broadcast=True)

# ===== Main (local dev) =====
if __name__ == "__main__":
    # Chạy thử local: python server.py
    socketio.run(app, host="0.0.0.0", port=8000)
