import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit

app = Flask(__name__)
CORS(app)

# Socket.IO (gevent worker trên Render)
socketio = SocketIO(app, cors_allowed_origins="*")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# ===== Health & Root =====
@app.get("/health")
def health():
    return jsonify(status="ok")

@app.get("/")
def root():
    return jsonify(app="RaidenX8 API", ok=True)

# ===== Chat AI (Gemini -> fallback echo) =====
@app.post("/ai/chat")
def ai_chat():
    data = request.get_json(silent=True) or {}
    user_msg = (data.get("message") or "").strip()
    if not user_msg:
        return jsonify(reply="Bạn thử gõ gì đó trước nhé 😄")

    # Nếu chưa có key => echo
    if not GEMINI_API_KEY:
        return jsonify(reply=f"[echo] {user_msg}")

    # Gọi Gemini 1.5 Flash (Google AI Studio)
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
        payload = {
            "contents": [{
                "parts": [{"text": f"Trả lời ngắn gọn bằng tiếng Việt: {user_msg}"}]
            }]
        }
        r = requests.post(f"{url}?key={GEMINI_API_KEY}", json=payload, timeout=20)
        r.raise_for_status()
        js = r.json()
        text = js.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        if not text:
            text = "Xin lỗi, mình chưa nhận được câu trả lời hợp lệ."
        return jsonify(reply=text)
    except Exception as e:
        return jsonify(reply=f"Lỗi gọi Gemini: {e}")

# ===== Socket.IO demo (có thể phát sự kiện nếu muốn) =====
@socketio.on("connect")
def on_connect():
    emit("server_message", {"msg": "✅ Server Socket.IO đã kết nối."})

@socketio.on("client_message")
def on_client_message(data):
    # broadcast cho mọi client
    emit("server_message", {"msg": data.get("msg", "")}, broadcast=True)

# ===== Local dev =====
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
