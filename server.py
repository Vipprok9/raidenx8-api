import os, json, requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# ====== Config ======
PROVIDER       = os.getenv("PROVIDER", "gemini")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash-preview-05-20")
FRONTEND_ORI   = os.getenv("FRONTEND_ORIGIN", "*")

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": FRONTEND_ORI}})
socketio = SocketIO(app, cors_allowed_origins=FRONTEND_ORI, async_mode="eventlet")

SYSTEM_PROMPT = (
    "Bạn là RaidenX8 – trả lời ngắn gọn, rõ ràng, tiếng Việt tự nhiên."
)

# ====== Helpers (no recursion) ======
def call_gemini(text: str) -> str:
    """
    Gọi Gemini 1 lần (non-stream). Trả về string.
    """
    if not GEMINI_API_KEY:
        return "Thiếu GEMINI_API_KEY trên server."
    url = f"https://generativelanguage.googleapis.com/v1beta/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": f"{SYSTEM_PROMPT}\n\nNgười dùng: {text}"}]}
        ]
    }
    try:
        r = requests.post(url, json=payload, timeout=30)
        j = r.json()
        if r.status_code >= 400:
            return f"Lỗi Gemini: {j.get('error', {}).get('message', r.text)}"
        parts = j.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        reply = "".join(p.get("text", "") for p in parts) or "(không có nội dung)"
        return reply
    except Exception as e:
        return f"Lỗi gọi Gemini: {e}"

def handle_message(text: str) -> str:
    """
    Tách riêng logic xử lý; KHÔNG emit và KHÔNG tự gọi lại chính nó.
    """
    text = (text or "").strip()
    if not text:
        return "Bạn gửi nội dung trống rồi."
    if PROVIDER == "gemini":
        return call_gemini(text)
    return "Provider không được hỗ trợ."

# ====== HTTP APIs ======
@app.get("/health")
def health():
    return {"ok": True, "provider": PROVIDER, "model": GEMINI_MODEL}

@app.post("/ai/chat")
def http_chat():
    data = request.get_json(force=True, silent=True) or {}
    txt  = data.get("text", "")
    reply = handle_message(txt)
    return jsonify({"reply": reply})

# ====== Socket.IO (2 chiều) ======
@socketio.on("connect")
def on_connect():
    emit("status", {"connected": True})

@socketio.on("disconnect")
def on_disconnect():
    # có thể log nếu muốn
    pass

@socketio.on("typing")
def on_typing(data):
    # FWD typing state cho UI (nếu cần broadcast thì thêm broadcast=True)
    emit("typing", {"typing": True})

@socketio.on("stop_typing")
def on_stop_typing():
    emit("typing", {"typing": False})

@socketio.on("chat")
def on_chat(data):
    """
    Nhận tin nhắn từ client: { text: "..." }
    Trả về một event 'reply' duy nhất -> KHÔNG đệ quy.
    """
    txt = (data or {}).get("text", "")
    reply = handle_message(txt)
    emit("reply", {"text": reply})  # gửi lại cho chính người gửi

if __name__ == "__main__":
    # Dùng cho local test; trên Render dùng gunicorn (Procfile)
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
