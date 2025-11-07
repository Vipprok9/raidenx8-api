# --- PHẢI ĐỂ TRÊN CÙNG ---
import eventlet
eventlet.monkey_patch()

import os, json
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import google.generativeai as genai

# ====== ENV ======
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")      # optional
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")        # optional
TELEGRAM_SECRET    = os.getenv("TELEGRAM_SECRET", "RAIDENX_SECRET_123")

# ====== APP ======
app = Flask(__name__)
# nếu muốn chặt hơn: CORS(app, origins=["https://raidenx8.pages.dev"])
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet",
                    ping_interval=25, ping_timeout=60)

# ====== Gemini (Google AI Studio) ======
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(GEMINI_MODEL)

@app.get("/")
def root():
    return "ok", 200

@app.get("/health")
def health():
    return "ok", 200

def ai_reply(user_text: str) -> str:
    """Gọi Gemini trả lời ngắn gọn, thân thiện (tiếng Việt)."""
    try:
        prompt = (
            "Bạn là Avatar AI của RaidenX8. Trả lời ngắn gọn, thân thiện, rõ ràng.\n"
            f"Người dùng: {user_text}"
        )
        r = model.generate_content(prompt)
        return (getattr(r, "text", "") or "").strip()
    except Exception as e:
        return f"Lỗi tạm thời: {e}"

# ====== Socket.IO ======
@socketio.on("connect")
def on_connect():
    emit("chat", "RaidenX8 đã kết nối. Gõ gì đó đi!")

@socketio.on("chat")
def on_chat(msg):
    emit("chat", ai_reply(str(msg)))

# HTTP fallback cho frontend
@app.post("/ai/chat")
def http_chat():
    data = request.get_json(silent=True) or {}
    return jsonify({"reply": ai_reply(str(data.get("text", "")))})

# ====== TTS endpoint (Chrome Web Speech) ======
# Trả về 'webspeech' để frontend dùng speechSynthesis của Chrome đọc.
@app.post("/tts")
def tts():
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "")[:500]
    return jsonify({"provider": "webspeech", "text": text})

# ====== Telegram webhook (tùy chọn) ======
@app.post("/webhook")
def telegram_webhook():
    if request.headers.get("X-Telegram-Secret-Token") != TELEGRAM_SECRET:
        return "forbidden", 403
    # Tự xử lý nếu cần
    return jsonify(ok=True)

# Local run (Render sẽ chạy bằng gunicorn)
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
