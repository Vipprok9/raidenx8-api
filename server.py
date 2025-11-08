# server.py  – RaidenX8 API (Flask + Socket.IO)
# Safe for Render free tier. Async mode = threading (không cần eventlet).
import os
import time
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# --- Optional Gemini ---
MODEL = "gemini-2.5-flash-preview-05-20"
GEMINI_OK = False
genai = None
if os.getenv("GEMINI_API_KEY"):
    try:
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        GEMINI_OK = True
    except Exception:
        genai = None
        GEMINI_OK = False

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ----------------- Utils -----------------
def rule_based_reply(text: str) -> str:
    t = (text or "").lower().strip()
    if not t:
        return "Bạn muốn hỏi gì nè? Ví dụ: 'Thời tiết Huế hôm nay' hoặc 'Giá BTC bây giờ'."

    if "btc" in t or "bitcoin" in t:
        return "Giá BTC (demo): bản miễn phí chưa gọi API thị trường. Khi có khoá thật mình sẽ trả realtime nhé."

    if "thời tiết" in t or "weather" in t:
        return "Thời tiết (demo): backend chưa bật nguồn dữ liệu công cộng. Đây là bản minh hoạ để test luồng WebSocket/REST."

    if "đọc truyện" in t or "narrate" in t:
        return "Narrate (demo): RaidenX8 mở mắt giữa dải sáng Aurora Pulse, giai điệu chill khẽ ngân..."

    return "Mình đã nhận tin nhắn. Đây là phản hồi demo (fallback). Hãy hỏi thời tiết, giá BTC, hoặc bật đọc truyện nhé."

def call_gemini(prompt: str) -> str:
    if not GEMINI_OK or genai is None:
        return rule_based_reply(prompt)

    try:
        sys_inst = (
            "Bạn là trợ lý Việt hoá, trả lời ngắn gọn, thân thiện.\n"
            "Nếu không có số liệu realtime, nói rõ đây là demo.\n"
        )
        model = genai.GenerativeModel(MODEL, system_instruction=sys_inst)
        resp = model.generate_content(prompt or "Xin chào!")
        # Một số SDK trả về .text, một số trả về candidates
        if hasattr(resp, "text") and resp.text:
            return resp.text.strip()
        if hasattr(resp, "candidates") and resp.candidates:
            parts = resp.candidates[0].content.parts
            texts = [getattr(p, "text", "") for p in parts]
            return "\n".join([s for s in texts if s]).strip() or rule_based_reply(prompt)
        return rule_based_reply(prompt)
    except Exception as e:
        # Không để văng lỗi, luôn trả lời có nghĩa
        return f"Lỗi Gemini (demo trả lời): {e}. Mình sẽ dùng phản hồi mặc định.\n" + rule_based_reply(prompt)

def ai_reply(text: str) -> str:
    # Ưu tiên quy tắc nhỏ cho nhanh, còn lại để Gemini
    base = rule_based_reply(text)
    if base.startswith("Mình đã nhận") and GEMINI_OK:
        return call_gemini(text)
    # Nếu rule đã match thì trả rule; nếu có GEMINI thì vẫn có thể gọi khi người dùng muốn nội dung mở
    if GEMINI_OK and ("?" in (text or "") or "giải thích" in (text or "").lower()):
        return call_gemini(text)
    return base

# ----------------- HTTP endpoints -----------------
@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "provider": "gemini" if GEMINI_OK else "offline",
        "model": MODEL if GEMINI_OK else "rule-based",
        "time": int(time.time())
    })

@app.post("/chat")
def chat():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    reply = ai_reply(text)
    return jsonify({"ok": True, "reply": reply})

# ----------------- Socket.IO (2 chiều) -----------------
# LƯU Ý: dùng event khác tên để tránh echo loop (user_message -> bot_message)
@socketio.on("connect")
def on_connect():
    emit("status", {"ok": True, "message": "connected"}, broadcast=False)

@socketio.on("user_message")
def on_user_message(payload):
    try:
        text = (payload or {}).get("text", "")
        reply = ai_reply(text)
        # Chỉ emit 'bot_message' về client đã gửi, không broadcast
        emit("bot_message", {"text": reply}, broadcast=False)
    except Exception as e:
        emit("bot_message", {"text": f"Lỗi server: {e}"}, broadcast=False)

# ----------------- Entry -----------------
if __name__ == "__main__":
    # Chạy dev local (Render sẽ dùng gunicorn theo Procfile)
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
