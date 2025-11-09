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
DEFAULT_MODEL_ENV = os.getenv("GEMINI_MODEL", "")
API_ROOT = "https://generativelanguage.googleapis.com/v1beta"

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

_models_cache = None
def list_models():
    global _models_cache
    if _models_cache is not None:
        return _models_cache
    url = f"{API_ROOT}/models?key={GEMINI_API_KEY}"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    data = r.json()
    _models_cache = [m["name"].split("/")[-1] for m in data.get("models", [])]
    return _models_cache

def pick_model(requested: str = "") -> str:
    available = []
    try:
        available = list_models()
    except Exception:
        pass

    if DEFAULT_MODEL_ENV and DEFAULT_MODEL_ENV in available:
        return DEFAULT_MODEL_ENV

    req = (requested or "").strip().lower()
    def find(prefix):
        for m in available:
            if m.lower().startswith(prefix):
                return m
        return ""

    if "2.5" in req:
        m = find("gemini-2.5")
        if m: return m
    if "2.0" in req or "preview" in req or "exp" in req:
        m = find("gemini-2.0")
        if m: return m
    if "1.5" in req:
        if "gemini-1.5-flash" in available: return "gemini-1.5-flash"
    if "gemini-1.5-flash" in available:
        return "gemini-1.5-flash"
    if available:
        return available[0]
    return "gemini-1.5-flash"

def call_gemini_rest(model, msg):
    url = f"{API_ROOT}/models/{model}:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents":[{"parts":[{"text":msg}]}]}
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    return (data.get("candidates",[{}])[0]
                .get("content",{})
                .get("parts",[{}])[0]
                .get("text",""))

def call_gemini_sdk(model, msg):
    m = genai.GenerativeModel(model)
    res = m.generate_content(msg)
    return getattr(res, "text", "") or ""

def smart_call(requested_model, msg):
    model = pick_model(requested_model)
    try:
        if model.startswith("gemini-1.5"):
            return call_gemini_sdk(model, msg)
        return call_gemini_rest(model, msg)
    except requests.HTTPError as e:
        if getattr(e.response, "status_code", None) == 404:
            return call_gemini_sdk("gemini-1.5-flash", msg)
        raise

@app.get("/health")
def health():
    ok = bool(GEMINI_API_KEY)
    model = pick_model(DEFAULT_MODEL_ENV or "gemini-1.5-flash")
    return jsonify({"ok": ok, "model": model})

@app.get("/ai/models")
def ai_models():
    try:
        return jsonify({"models": list_models()})
    except Exception as e:
        return jsonify({"models": [], "error": str(e)}), 500

@app.post("/ai/chat")
def ai_chat():
    if not GEMINI_API_KEY:
        return jsonify({"reply": "(demo) Chưa có GEMINI_API_KEY."})
    data = request.get_json(force=True) or {}
    msg = data.get("message","")
    mdl = data.get("model","")
    if not msg:
        return jsonify({"reply": ""})
    try:
        text = smart_call(mdl, msg)
    except Exception as e:
        text = f"Lỗi: {e}"
    return jsonify({"reply": text})

@socketio.on("connect")
def on_connect():
    emit("bot_message", "WS connected 🎧")

@socketio.on("chat")
def on_chat(data):
    msg = (data or {}).get("message","")
    mdl = (data or {}).get("model","")
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
    port = int(os.getenv("PORT","8000"))
    socketio.run(app, host="0.0.0.0", port=port)
