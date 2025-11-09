# ---- MUST BE FIRST (SocketIO + eventlet) ----
import eventlet
eventlet.monkey_patch()
# ---------------------------------------------

import os, re, time, requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO
import google.generativeai as genai

# ====== ENV ======
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
# Mặc định dùng 2.5 preview 05-20; có thể đổi qua env Render
DEFAULT_MODEL  = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-preview-0520").strip()

# ====== APP ======
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ====== UTILS ======
def _strip_md(t: str) -> str:
    """Làm sạch markdown để đọc mượt (không **, bullet, code)."""
    if not t: return ""
    t = re.sub(r"\*\*(.*?)\*\*", r"\1", t)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"^[-*]\s+", "", t, flags=re.M)
    return t.strip()

# ====== CALLERS ======
def call_gemini_15_sdk(model: str, msg: str) -> str:
    """Gemini 1.5 (SDK) – ổn định cho 1.5-pro/flash."""
    m = genai.GenerativeModel(model)
    res = m.generate_content(msg)
    return getattr(res, "text", "") or res.candidates[0].content.parts[0].text

def call_gemini_25_rest(model: str, msg: str) -> str:
    """
    Gemini 2.5 (REST v1beta) – đúng endpoint:
    https://generativelanguage.googleapis.com/v1beta/models/<MODEL>:generateContent?key=...
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"role": "user", "parts": [{"text": msg}]}]}
    r = requests.post(url, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]

def smart_call(model: str, msg: str) -> str:
    mdl = (model or DEFAULT_MODEL).strip()
    if mdl.startswith("gemini-2.5"):
        text = call_gemini_25_rest(mdl, msg)
    else:
        text = call_gemini_15_sdk(mdl, msg)
    return _strip_md(text)

# ====== ROUTES ======
@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "has_key": bool(GEMINI_API_KEY),
        "model": DEFAULT_MODEL
    })

@app.post("/ai/chat")
def ai_chat():
    if not GEMINI_API_KEY:
        return jsonify({"reply": "(demo) Thiếu GEMINI_API_KEY, đang chạy chế độ mô phỏng."})
    data = request.get_json(force=True) or {}
    msg = (data.get("message") or "").strip()
    mdl = (data.get("model") or DEFAULT_MODEL).strip()
    if not msg:
        return jsonify({"reply": ""})
    try:
        text = smart_call(mdl, msg)
    except Exception as e:
        text = f"Lỗi: {e}"
    return jsonify({"reply": text})

# ====== SOCKET.IO ======
@socketio.on("connect")
def on_connect():
    socketio.emit("bot_message", "WS connected 🎧")

@socketio.on("chat")
def on_chat(data):
    msg = (data or {}).get("message", "").strip()
    mdl = (data or {}).get("model", DEFAULT_MODEL).strip()
    socketio.emit("bot_typing")
    time.sleep(0.12)
    if not GEMINI_API_KEY:
        socketio.emit("bot_message", "(demo) Thiếu GEMINI_API_KEY – trả lời giả lập.")
        return
    try:
        text = smart_call(mdl, msg)
    except Exception as e:
        text = f"Lỗi: {e}"
    socketio.emit("bot_message", text)

# ====== MAIN ======
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    socketio.run(app, host="0.0.0.0", port=port)
