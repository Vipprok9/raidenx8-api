# -*- coding: utf-8 -*-
# RaidenX8 API — WebSocket 2 chiều + AI (Gemini/OpenAI)
# Giọng đọc: dùng Web Speech trên FRONTEND (backend trả speak=true)

import os, time
import eventlet
eventlet.monkey_patch()

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# ==== ENV ====
PROVIDER        = os.getenv("PROVIDER", "gemini").strip().lower()        # "gemini" | "openai"
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "*")
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL    = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash-preview-05-20")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# ==== APP ====
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": FRONTEND_ORIGIN}}, supports_credentials=True)

socketio = SocketIO(
    app,
    cors_allowed_origins=FRONTEND_ORIGIN,
    async_mode="eventlet",
    ping_interval=25,
    ping_timeout=60,
)

# ==== AI Clients (lazy init) ====
_genai = None
_openai_client = None

SYSTEM_PROMPT = (
    "Bạn là RaidenX8 – trợ lý Gen-Z, trả lời ngắn gọn, rõ ràng, lịch sự, có chiều sâu. "
    "Ngôn ngữ: tiếng Việt. Khi phù hợp, gợi ý ngắn (bullet) hoặc bước làm. "
)

def call_gemini(prompt: str) -> str:
    global _genai
    if not GEMINI_API_KEY:
        return "Chưa cấu hình GEMINI_API_KEY."
    if _genai is None:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        _genai = genai
    model = _genai.GenerativeModel(GEMINI_MODEL)
    resp = model.generate_content([SYSTEM_PROMPT, prompt])
    return (resp.text or "").strip()

def call_openai(prompt: str) -> str:
    global _openai_client
    if not OPENAI_API_KEY:
        return "Chưa cấu hình OPENAI_API_KEY."
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    r = _openai_client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        temperature=0.7,
    )
    return r.choices[0].message.content.strip()

def ai_answer(prompt: str) -> str:
    # Một số rule “live tool” demo để phản hồi tức thì
    low = prompt.lower()
    if "mấy giờ" in low or "bây giờ mấy giờ" in low:
        return time.strftime("Bây giờ là %H:%M UTC, chúc bạn một ngày chill 😎", time.gmtime())

    # Gọi model theo PROVIDER, có fallback sang bên còn lại nếu lỗi.
    try:
        if PROVIDER == "gemini":
            out = call_gemini(prompt)
            if out.startswith("Chưa cấu hình") and OPENAI_API_KEY:
                return call_openai(prompt)
            return out
        else:
            out = call_openai(prompt)
            if out.startswith("Chưa cấu hình") and GEMINI_API_KEY:
                return call_gemini(prompt)
            return out
    except Exception as e:
        # Fallback cuối cùng
        try:
            if PROVIDER == "gemini" and OPENAI_API_KEY:
                return call_openai(prompt)
            if PROVIDER != "gemini" and GEMINI_API_KEY:
                return call_gemini(prompt)
        except:
            pass
        return f"Xin lỗi, AI đang bận: {e}"

# ==== HTTP ROUTES ====
@app.get("/")
def root():
    return jsonify({
        "ok": True,
        "provider": "gemini" if PROVIDER == "gemini" else "openai",
        "model": GEMINI_MODEL if PROVIDER == "gemini" else OPENAI_MODEL,
    })

@app.get("/health")
def health():
    return jsonify({"ok": True, "ts": int(time.time())})

@app.post("/ai/chat_sync")
def chat_sync():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "missing text"}), 400
    answer = ai_answer(text)
    return jsonify({"ok": True, "reply": answer, "speak": True})

# ==== SOCKET.IO ====
@socketio.on("connect")
def on_connect():
    emit("bot_msg", {"text": "Đã kết nối websocket 2 chiều. Hỏi gì cũng được nè!", "speak": True})

@socketio.on("disconnect")
def on_disconnect():
    pass

@socketio.on("user_msg")
def on_user_msg(payload):
    try:
        text = (payload or {}).get("text", "").strip()
        if not text:
            emit("bot_msg", {"text": "Bạn gửi nội dung trống rồi 😅", "speak": True})
            return
        reply = ai_answer(text)
        emit("bot_msg", {"text": reply, "speak": True})
    except Exception as e:
        emit("bot_msg", {"text": f"Lỗi xử lý: {e}", "speak": False})

# Gunicorn entry: server:app
