# --- MUST BE FIRST ---
import eventlet
eventlet.monkey_patch()

import os, time
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO
import google.generativeai as genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")

app = Flask(__name__)
CORS(app)
# async_mode='eventlet' để chắc chắn dùng eventlet
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet", ping_interval=25, ping_timeout=60)

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "gemini": bool(GEMINI_API_KEY),
        "model": GEMINI_MODEL
    })

@app.post("/ai/chat")
def ai_chat():
    data = request.get_json(force=True) or {}
    msg = data.get("message", "").strip()
    mdl = data.get("model") or GEMINI_MODEL
    if not msg:
        return jsonify({"reply": "(demo) Nội dung trống."})
    if not GEMINI_API_KEY:
        return jsonify({"reply": "(demo) Thiếu GEMINI_API_KEY nên trả lời demo."})

    try:
        model = genai.GenerativeModel(mdl)
        res = model.generate_content(msg)
        text = getattr(res, "text", "") or "(empty)"
        return jsonify({"reply": text})
    except Exception as e:
        return jsonify({"reply": f"Lỗi: {e}"})

# --- WebSocket 2 chiều ---
@socketio.on("connect")
def on_connect():
    socketio.emit("bot_message", "(WS) Connected 🎧")

@socketio.on("chat")
def on_chat(data):
    msg = (data or {}).get("message", "").strip()
    mdl = (data or {}).get("model") or GEMINI_MODEL
    socketio.emit("bot_typing")
    time.sleep(0.2)

    if not msg:
        socketio.emit("bot_message", "(demo) Bạn chưa nhập nội dung.")
        return
    if not GEMINI_API_KEY:
        socketio.emit("bot_message", "(demo) WS ok nhưng thiếu GEMINI_API_KEY.")
        return

    try:
        model = genai.GenerativeModel(mdl)
        res = model.generate_content(msg)
        text = getattr(res, "text", "") or "(empty)"
    except Exception as e:
        text = f"Lỗi: {e}"
    socketio.emit("bot_message", text)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    socketio.run(app, host="0.0.0.0", port=port)
