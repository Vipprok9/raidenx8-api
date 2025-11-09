# ---- MUST BE FIRST ----
import eventlet
eventlet.monkey_patch()
# -----------------------

import os, time, requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import google.generativeai as genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet", ping_interval=25, ping_timeout=20)

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def call_gemini_sdk(model, msg):
    m = genai.GenerativeModel(model)
    res = m.generate_content(msg)
    return getattr(res, "text", "").strip() or "(empty)"

def call_gemini_25_rest(model, msg):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": msg}]}]}
    r = requests.post(url, json=payload, timeout=40)
    r.raise_for_status()
    data = r.json()
    return data["candidates"][0]["content"]["parts"][0].get("text","").strip()

def smart_call(model, msg):
    mdl = (model or DEFAULT_MODEL).strip()
    if mdl.lower().startswith("gemini-2.5-flash-preview-0520"):
        return call_gemini_25_rest(mdl, msg)
    return call_gemini_sdk(mdl, msg)

@app.get("/health")
def health():
    return jsonify({"ok": True, "model_default": DEFAULT_MODEL})

@app.post("/ai/chat")
def ai_chat():
    if not GEMINI_API_KEY:
        return jsonify({"reply": "(demo) Thiếu GEMINI_API_KEY."})
    data = request.get_json(force=True, silent=True) or {}
    msg = (data.get("message") or "").strip()
    mdl = (data.get("model") or DEFAULT_MODEL).strip()
    if not msg:
        return jsonify({"reply": ""})
    try:
        text = smart_call(mdl, msg)
    except Exception as e:
        text = f"Lỗi: {e}"
    return jsonify({"reply": text, "model_used": mdl})

@socketio.on("connect")
def on_connect():
    emit("bot_message", "WS connected ✓")

@socketio.on("chat")
def on_chat(data):
    msg = (data or {}).get("message","").strip()
    mdl = (data or {}).get("model") or DEFAULT_MODEL
    emit("bot_typing")
    time.sleep(0.15)
    if not GEMINI_API_KEY:
        emit("bot_message", "(demo) Thiếu GEMINI_API_KEY.")
        return
    try:
        text = smart_call(mdl, msg)
    except Exception as e:
        text = f"Lỗi: {e}"
    emit("bot_message", text)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    socketio.run(app, host="0.0.0.0", port=port)
