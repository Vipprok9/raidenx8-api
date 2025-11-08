import os, json
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import httpx

# -------- Env --------
PROVIDER        = os.getenv("PROVIDER", "gemini").lower()
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL    = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash-preview-05-20")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "*")

# -------- App / CORS / Socket --------
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": FRONTEND_ORIGIN}})
socketio = SocketIO(app, cors_allowed_origins=FRONTEND_ORIGIN, async_mode="eventlet")

SYSTEM_PROMPT = (
    "Bạn là RaidenX8 – trả lời ngắn gọn, tự nhiên, tiếng Việt. "
    "Nếu không có dữ liệu thời gian thực, hãy nói rõ hạn chế và gợi ý câu tiếp theo."
)

# -------- Gemini (httpx) --------
def call_gemini(text: str) -> str:
    if not GEMINI_API_KEY:
        return "Thiếu GEMINI_API_KEY trên server."

    url = f"https://generativelanguage.googleapis.com/v1beta/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": f"{SYSTEM_PROMPT}\n\nNgười dùng: {text}"}]}
        ]
    }

    try:
        limits  = httpx.Limits(max_keepalive_connections=2, max_connections=4)
        timeout = httpx.Timeout(15.0, read=30.0)
        with httpx.Client(limits=limits, timeout=timeout) as client:
            r = client.post(url, json=payload)
            if r.status_code >= 400:
                try:
                    j = r.json()
                    msg = j.get("error", {}).get("message", r.text)
                except Exception:
                    msg = r.text
                return f"Lỗi Gemini: {msg}"

            j = r.json()
            parts = j.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            reply = "".join(p.get("text", "") for p in parts) or "(không có nội dung)"
            return reply

    except httpx.ReadTimeout:
        return "Gemini đang chậm, thử lại nhé."
    except Exception as e:
        return f"Lỗi gọi Gemini: {type(e).__name__}"

# -------- HTTP --------
@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "provider": PROVIDER,
        "model": GEMINI_MODEL
    })

@app.post("/ai/chat")
def http_chat():
    data = request.get_json(silent=True) or {}
    msg  = (data.get("message") or "").strip()
    if not msg:
        return jsonify({"error": "Empty message"}), 400
    reply = call_gemini(msg)
    return jsonify({"reply": reply})

# -------- WebSocket 2 chiều --------
@socketio.on("connect")
def on_connect():
    emit("server_status", {"connected": True})

@socketio.on("disconnect")
def on_disconnect():
    # client sẽ tự tắt đèn trạng thái
    pass

@socketio.on("typing")
def on_typing(data):
    # Echo trạng thái gõ phím về cho client hiển thị "typing..."
    emit("typing", {"typing": bool(data.get("typing"))}, broadcast=False)

@socketio.on("chat")
def on_chat(data):
    """
    Nhận tin nhắn từ web: { msg: "..." }
    → Gọi Gemini → emit('bot_reply', { text })
    """
    msg = (data or {}).get("msg", "")
    if not msg.strip():
        emit("bot_reply", {"text": "Bạn gửi nội dung trống rồi nè."})
        return
    # Cho UI biết đang xử lý
    emit("thinking", {"on": True})
    reply = call_gemini(msg)
    emit("thinking", {"on": False})
    emit("bot_reply", {"text": reply})

# Không dùng app.run khi chạy gunicorn
# if __name__ == "__main__":
#     socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
