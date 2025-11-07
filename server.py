import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import requests

app = Flask(__name__)
CORS(app)

# Socket.IO (gevent worker)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

def call_gemini(prompt: str) -> str:
    """
    Gọi Gemini 1.5 Flash qua REST API.
    Nếu thiếu key hoặc lỗi quota → raise Exception để fallback echo.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("Missing GEMINI_API_KEY")

    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        "models/gemini-1.5-flash-latest:generateContent"
    )
    payload = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 256
        }
    }
    params = {"key": GEMINI_API_KEY}
    r = requests.post(url, json=payload, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()

    # Rút text an toàn
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        raise RuntimeError(f"Gemini bad response: {data}")

@app.get("/health")
def health():
    return jsonify(status="ok")

@app.get("/")
def root():
    return jsonify(app="RaidenX8 API", ok=True)

@app.post("/ai/chat")
def ai_chat():
    data = request.get_json(silent=True) or {}
    user_msg = (data.get("message") or "").strip()
    if not user_msg:
        return jsonify(reply="Bạn chưa nhập nội dung."), 400

    # Thử Gemini → nếu lỗi thì echo
    try:
        reply = call_gemini(user_msg)
    except Exception as e:
        # Không gọi lặp lại hay tự phát sự kiện nữa để tránh đệ quy
        reply = f"[echo] {user_msg}  (AI lỗi: {str(e)[:80]})"

    return jsonify(reply=reply)

# ===== Socket.IO (demo 2 chiều) =====
@socketio.on("connect")
def on_connect():
    emit("server_message", {"msg": "🔌 Socket.IO connected."})

@socketio.on("client_message")
def on_client_message(data):
    # Chỉ broadcast 1 lần, không tự gửi ngược lại client_message để tránh vòng lặp
    txt = (data or {}).get("msg", "")
    emit("server_message", {"msg": f"[echo] {txt}"}, broadcast=True)

# ===== Local dev =====
if __name__ == "__main__":
    # Chạy thử local: python server.py
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
