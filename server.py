import os
import json
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit

PORT = int(os.environ.get("PORT", 8000))
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "raidenx8-secret")
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

gemini_model_name = "gemini-2.5-flash-preview-05-20"
_gemini_model = None

def _get_gemini_model():
    global _gemini_model
    if _gemini_model is None and GEMINI_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_KEY)
            _gemini_model = genai.GenerativeModel(gemini_model_name)
        except Exception as e:
            print("Init Gemini failed:", e)
            _gemini_model = None
    return _gemini_model

def rule_based_reply(text: str) -> str:
    t = (text or "").lower()
    if "thời tiết" in t and ("huế" in t or "hue" in t):
        return "Demo thời tiết Huế: có thể mưa rải rác, nhớ mang áo mưa ☔️."
    if "btc" in t or "bitcoin" in t:
        now = datetime.utcnow().strftime("%H:%M UTC")
        return f"Demo giá BTC (không realtime). Cập nhật lúc {now}."
    if "xin chào" in t or "hello" in t:
        return "Chào bạn, mình là RaidenX8. Hỏi thời tiết, giá BTC, hoặc kể chuyện nhé!"
    return ""

def call_gemini(text: str) -> str:
    model = _get_gemini_model()
    if not model:
        return "Lỗi Gemini: chưa cấu hình GEMINI_API_KEY hoặc init thất bại."
    try:
        prompt = (
            "Bạn là trợ lý Việt hoá, trả lời ngắn gọn, thân thiện. "
            "Nếu không có số liệu realtime, nói rõ đây là demo.

"
            f"Người dùng: {text}
Trả lời: "
        )
        resp = model.generate_content(prompt)
        out = getattr(resp, "text", None) or ""
        return out.strip() or "Xin lỗi, mình chưa có câu trả lời."
    except Exception as e:
        return f"Lỗi Gemini: {e}"

def answer(text: str) -> str:
    out = rule_based_reply(text)
    if out:
        return out
    return call_gemini(text)

@app.get("/")
@app.get("/health")
def health():
    return jsonify({"ok": True, "provider": "gemini", "model": gemini_model_name})

@app.post("/api/chat")
def api_chat():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    reply = answer(text)
    return jsonify({"ok": True, "reply": reply})

@socketio.on("connect")
def ws_connect():
    emit("bot_message", {"text": "Xin chào 👋 Hỏi thời tiết, giá BTC… hoặc thử bật đọc truyện nhé."})

@socketio.on("user_message")
def ws_user_message(data):
    try:
        text = (data or {}).get("text", "")
        reply = answer(text)
        emit("bot_message", {"text": reply})
    except Exception as e:
        emit("bot_message", {"text": f"Lỗi server: {e}"})

@socketio.on("disconnect")
def ws_disconnect():
    pass

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=PORT)
