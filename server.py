import os, time
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import requests

# ====== App & Socket ======
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

OPENAI_KEY  = os.getenv("OPENAI_API_KEY", "")
GEMINI_KEY  = os.getenv("GEMINI_API_KEY", "")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini-1.5-flash")

# ====== Helpers ======
def reply_demo(user_text: str) -> str:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    tips = [
        "Mình đang ở chế độ DEMO (không có API key).",
        "Bạn có thể thêm GEMINI_API_KEY hoặc OPENAI_API_KEY vào Render → Environment.",
        "Sau khi thêm key, redeploy là dùng được trả lời AI thật."
    ]
    return f"[DEMO] {now}. Bạn hỏi: “{user_text}”. " + " ".join(tips)

def call_openai(model: str, text: str) -> str:
    """Minimal OpenAI Chat Completions (gpt-4o-mini / gpt-4o)"""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_KEY}"}
    payload = {
        "model": model or "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Bạn là trợ lý nói tiếng Việt, trả lời ngắn gọn, rõ ràng."},
            {"role": "user", "content": text}
        ]
    }
    r = requests.post(url, json=payload, headers=headers, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]

def call_gemini(model: str, text: str) -> str:
    """Google Gemini generateContent v1beta (HTTP)"""
    use_model = model or DEFAULT_MODEL or "gemini-1.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{use_model}:generateContent?key={GEMINI_KEY}"
    payload = {"contents": [{"parts": [{"text": text}]}]}
    r = requests.post(url, json=payload, timeout=60)
    # Gemini trả 200 cả khi lỗi model không tồn tại -> kiểm tra cẩn thận
    if r.status_code != 200:
        raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:500]}")
    data = r.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        # trả thông báo dễ hiểu nếu model sai tên
        msg = data.get("error", {}).get("message") or str(data)[:400]
        raise RuntimeError(f"Gemini response error: {msg}")

def smart_answer(model: str, text: str) -> str:
    text = (text or "").strip()
    if not text:
        return "Bạn hãy nhập nội dung cần hỏi nhé."
    # Một vài rule nhanh (ví dụ thời tiết demo, giờ)
    low = text.lower()
    if "mấy giờ" in low or "thời gian" in low:
        return time.strftime("Bây giờ là %H:%M:%S (giờ máy chủ).")
    # Ưu tiên Gemini nếu có key và model bắt đầu bằng "gemini"
    if GEMINI_KEY and (model.startswith("gemini") or not OPENAI_KEY):
        return call_gemini(model, text)
    if OPENAI_KEY:
        return call_openai(model or "gpt-4o-mini", text)
    # fallback demo
    return reply_demo(text)

# ====== REST endpoints ======
@app.get("/health")
def health():
    return jsonify({"ok": True, "ts": int(time.time())})

@app.post("/ai/chat")
def ai_chat():
    data = request.get_json(silent=True) or {}
    model = (data.get("model") or DEFAULT_MODEL or "").strip()
    text  = data.get("text", "")
    try:
        out = smart_answer(model, text)
        return jsonify({"ok": True, "model": model, "answer": out})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:800]}), 400

# ====== Socket.IO (2 chiều, typing) ======
@socketio.on("connect")
def on_connect():
    emit("status", {"type": "info", "text": "WS connected 🎧"}, broadcast=False)

@socketio.on("disconnect")
def on_disconnect():
    # nothing to broadcast to others on personal app
    pass

@socketio.on("typing")
def on_typing(data):
    # client gửi {typing: true/false}
    emit("typing", {"typing": bool(data.get("typing"))}, broadcast=True, include_self=False)

@socketio.on("message")
def on_message(data):
    """Client gửi {text, model}; server phát lại tin user, gọi AI rồi phát tin AI"""
    text  = (data or {}).get("text", "")
    model = (data or {}).get("model", DEFAULT_MODEL)
    # phát bong bóng người dùng (echo)
    emit("message", {"role": "user", "text": text}, broadcast=True)
    # báo đang gõ
    emit("typing", {"typing": True}, broadcast=True)
    try:
        answer = smart_answer(model, text)
    except Exception as e:
        answer = f"Lỗi: {e}"
    # dừng “typing” và phát trả lời
    emit("typing", {"typing": False}, broadcast=True)
    emit("message", {"role": "assistant", "text": answer}, broadcast=True)

# ====== Entry point (Render sẽ chạy qua Procfile) ======
if __name__ == "__main__":
    # Dành cho chạy local: python server.py
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
