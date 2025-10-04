
import os
import json
import time
import queue
import requests
from threading import Thread
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from flask_socketio import SocketIO, emit

APP_NAME = "RaidenX8 API v8.2-patch.2"

app = Flask(__name__)
CORS(app)
# Use eventlet or gevent on Render; CORS any origin for quick demo
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# ---- Simple in-memory pubsub for SSE ----
_sse_queue = queue.Queue()

def sse_publish(event, data):
    payload = {"event": event, "data": data, "ts": time.time()}
    try:
        _sse_queue.put_nowait(json.dumps(payload))
    except queue.Full:
        pass

def sse_stream():
    # Heartbeat every 20s to keep Render free dyno alive during active clients
    heartbeat = 0
    while True:
        try:
            msg = _sse_queue.get(timeout=20)
            yield f"data: {msg}\n\n"
        except queue.Empty:
            heartbeat += 1
            yield f": ping {heartbeat}\n\n"

@app.get("/")
def index():
    return jsonify({"app": APP_NAME, "ok": True})

@app.get("/health")
def health():
    return jsonify({"status": "ok", "app": APP_NAME, "time": time.time()})

@app.get("/stream")
def stream():
    return Response(sse_stream(), mimetype="text/event-stream")

# ---- Telegram notify ----
@app.post("/notify")
def notify():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return jsonify({"ok": False, "error": "TELEGRAM_BOT_TOKEN missing"}), 500
    data = request.get_json(silent=True) or {}
    chat_id = str(data.get("chat_id", "")).strip()
    text = str(data.get("text", "")).strip()
    if not chat_id or not text:
        return jsonify({"ok": False, "error": "chat_id and text are required"}), 400

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        r = requests.post(url, json=payload, timeout=15)
        # If Telegram returns HTML (rare on edge), treat as error
        if r.headers.get("content-type","").startswith("text/html"):
            return jsonify({"ok": False, "error": "Upstream returned HTML (bad token or blocked)"}), 502
        out = r.json()
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502

    # Broadcast via sockets & SSE
    sse_publish("telegram_sent", {"chat_id": chat_id, "text": text, "tg": out})
    socketio.emit("telegram_ack", {"chat_id": chat_id, "text": text, "tg": out}, broadcast=True)
    return jsonify(out)

# ---- AI relay (OpenAI / Gemini) minimal passthrough ----
@app.post("/ai/openai")
def ai_openai():
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return jsonify({"ok": False, "error": "OPENAI_API_KEY missing"}), 500
    body = request.get_json(force=True)
    try:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        # Default to responses API if provided by client, else use chat.completions
        url = body.pop("_endpoint", None) or "https://api.openai.com/v1/chat/completions"
        r = requests.post(url, headers=headers, json=body, timeout=60)
        return (r.text, r.status_code, {"Content-Type": r.headers.get("Content-Type","application/json")})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502

@app.post("/ai/gemini")
def ai_gemini():
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return jsonify({"ok": False, "error": "GEMINI_API_KEY missing"}), 500
    body = request.get_json(force=True)
    try:
        model = body.pop("_model", "gemini-1.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        r = requests.post(url, headers=headers, json=body, timeout=60)
        return (r.text, r.status_code, {"Content-Type": r.headers.get("Content-Type","application/json")})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502

# ---- Socket.IO events ----
@socketio.on("connect")
def on_connect():
    emit("hello", {"msg": "connected", "app": APP_NAME})

@socketio.on("chat")
def on_chat(msg):
    # msg = {"role":"user","content":"hi"}
    payload = {"ts": time.time(), **(msg or {})}
    emit("chat", payload, broadcast=True)
    sse_publish("chat", payload)

@socketio.on("disconnect")
def on_disconnect():
    pass

if __name__ == "__main__":
    # Local run for debugging
    port = int(os.getenv("PORT", "5000"))
    socketio.run(app, host="0.0.0.0", port=port)
