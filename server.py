import os
import time
from collections import deque
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import requests

# -------- App & Realtime ----------
app = Flask(__name__)
CORS(app)  # cho phép gọi từ pages.dev, localhost, v.v.
socketio = SocketIO(app, cors_allowed_origins="*")  # realtime event bus

# -------- Env vars ----------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")

# -------- In-memory event buffer (polling fallback) ----------
EVENTS = deque(maxlen=200)

def push_event(kind, payload):
    evt = {"ts": int(time.time()), "kind": kind, "data": payload}
    EVENTS.append(evt)
    socketio.emit("message", evt, namespace="/ws")  # broadcast websocket
    return evt

# -------- Routes ----------
@app.route("/", methods=["GET"])
def root():
    # hiển thị ngắn gọn để khỏi 404
    return "RaidenX8 API is up."

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/events", methods=["GET"])
def events():
    """ Polling fallback cho client không dùng WebSocket """
    try:
        since = int(request.args.get("since", 0))
    except Exception:
        since = 0
    data = [e for e in list(EVENTS) if e["ts"] >= since]
    return jsonify({"events": data})

@app.route("/send", methods=["POST"])
def send():
    """
    Gửi tin nhắn Telegram.
    Body JSON: { "text": "hello" }
    """
    if not BOT_TOKEN or not CHAT_ID:
        return jsonify({"ok": False, "error": "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID"}), 400

    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "text is empty"}), 400

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": CHAT_ID, "text": text})
    ok = resp.ok
    data = {}
    try:
        data = resp.json()
    except Exception:
        data = {"raw": resp.text}

    push_event("outgoing", {"text": text, "ok": ok, "tg": data})
    return jsonify({"ok": ok, "tg": data}), (200 if ok else 500)

@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Telegram sẽ POST vào đây.
    Nhớ set webhook: https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook?url=https://<your-app>.onrender.com/webhook
    """
    update = request.get_json(silent=True) or {}
    msg = update.get("message") or update.get("edited_message") or {}
    chat = msg.get("chat") or {}
    text = msg.get("text", "")

    info = {
        "from_chat_id": chat.get("id"),
        "from_title": chat.get("title") or chat.get("username") or chat.get("first_name"),
        "text": text,
        "raw": update,
    }
    push_event("incoming", info)
    return jsonify({"ok": True})

# -------- WebSocket namespace ----------
@socketio.on("connect", namespace="/ws")
def ws_connect():
    emit("ready", {"message": "connected", "ts": int(time.time())})

@socketio.on("send", namespace="/ws")
def ws_send(data):
    """
    Client (frontend) có thể emit("send", {text}) qua WS -> forward sang Telegram
    """
    text = (data or {}).get("text", "").strip()
    if not text:
        emit("error", {"error": "text is empty"})
        return
    if not BOT_TOKEN or not CHAT_ID:
        emit("error", {"error": "Missing TELEGRAM_* envs"})
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": CHAT_ID, "text": text})
    ok = resp.ok
    tg = {}
    try:
        tg = resp.json()
    except Exception:
        tg = {"raw": resp.text}

    push_event("outgoing", {"text": text, "ok": ok, "tg": tg})
    emit("sent", {"ok": ok, "tg": tg})

# -------- Main (Render dùng Gunicorn) ----------
if __name__ == "__main__":
    # chạy local: python server.py
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
