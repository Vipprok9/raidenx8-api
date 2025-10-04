import os, time
from collections import deque
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import requests

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

EVENTS = deque(maxlen=200)

def push_event(kind, payload):
    evt = {"ts": int(time.time()), "kind": kind, "data": payload}
    EVENTS.append(evt)
    socketio.emit("message", evt, namespace="/ws")
    return evt

@app.route("/", methods=["GET"])
def root():
    return "RaidenX8 API is up."

@app.route("/health", methods=["GET"])
def health():
    return "ok", 200

@app.route("/events", methods=["GET"])
def events():
    return jsonify({"events": list(EVENTS)})

@app.route("/send", methods=["POST"])
def send():
    if not BOT_TOKEN or not CHAT_ID:
        return jsonify({"error": "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID"}), 400
    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": CHAT_ID, "text": text})
    ok = resp.ok
    data = resp.json() if resp.content else {}
    push_event("outgoing", {"text": text, "ok": ok, "tg": data})
    return jsonify({"ok": ok, "tg": data})

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(silent=True) or {}
    msg = (update.get("message") or update.get("edited_message") or {})
    chat = msg.get("chat") or {}
    text = msg.get("text", "")
    info = {
        "from_chat_id": chat.get("id"),
        "from_title": chat.get("first_name") or chat.get("title"),
        "text": text,
        "raw": update
    }
    push_event("incoming", info)
    return jsonify({"ok": True})

@socketio.on("connect", namespace="/ws")
def ws_connect():
    emit("ready", {"message": "connected"})

@socketio.on("send", namespace="/ws")
def ws_send(data):
    # Forward như /send
    text = (data or {}).get("text", "").strip()
    if not text:
        emit("error", {"error": "text is required"})
        return
    if not BOT_TOKEN or not CHAT_ID:
        emit("error", {"error": "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID"})
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": CHAT_ID, "text": text})
    ok = resp.ok
    tg = resp.json() if resp.content else {}
    push_event("outgoing", {"text": text, "ok": ok, "tg": tg})

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
