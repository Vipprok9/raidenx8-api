import os, json, requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# ===== Config =====
MODEL = "gemini-2.5-flash-preview-05-20"  # đúng tên model
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Socket.IO (use eventlet on Render)
socketio = SocketIO(app, cors_allowed_origins="*")

# ===== Helpers =====
def gemini_chat(text: str) -> str:
    """Call Gemini text endpoint. Returns plain text or error message."""
    if not GEMINI_API_KEY:
        return "Thiếu GEMINI_API_KEY trong env."

    try:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{MODEL}:generateContent?key={GEMINI_API_KEY}"
        )
        payload = {"contents": [{"parts": [{"text": text}]}]}
        res = requests.post(url, json=payload, timeout=30)
        data = res.json()
        # Khung phản hồi chuẩn
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"Lỗi Gemini: {e}"

# ===== HTTP =====
@app.get("/")
def root():
    ok = bool(GEMINI_API_KEY)
    return jsonify({"model": MODEL, "ok": ok, "provider": "gemini"})

@app.get("/health")
def health():
    return jsonify({"status": "ok"})

@app.post("/ai/chat")
def ai_chat():
    """REST fallback cho frontend."""
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"error": "missing text"}), 400
    reply = gemini_chat(text)
    return jsonify({"reply": reply})

# ===== WebSocket (Socket.IO) =====
@socketio.on("connect")
def ws_connect():
    emit("status", {"connected": True})

@socketio.on("chat")
def ws_chat(data):
    """
    data: { "text": "..." }
    Trả về sự kiện 'reply': { "reply": "..." }
    """
    try:
        text = (data or {}).get("text", "").strip()
        if not text:
            emit("reply", {"reply": "Bạn chưa nhập nội dung."})
            return
        answer = gemini_chat(text)
        emit("reply", {"reply": answer})
    except Exception as e:
        emit("reply", {"reply": f"Lỗi: {e}"})

if __name__ == "__main__":
    # Chạy local (dev). Trên Render dùng gunicorn (Procfile).
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
