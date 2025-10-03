import os
import time
from collections import deque
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import requests

# --- App & Realtime ---
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# --- Env vars ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")  # optional

# --- In-memory event buffer (fallback polling) ---
EVENTS = deque(maxlen=200)

def push_event(kind, payload):
    evt = {
        "ts": int(time.time()),
        "kind": kind,        # "incoming" (from Telegram) | "outgoing" (from web)
        "data": payload
    }
    EVENTS.append(evt)
    # broadcast to all websocket clients
    socketio.emit("message", evt, namespace="/ws", broadcast=True)
    return evt

# ---------- Routes ----------
@app.route("/", methods=["GET"])
def root():
    return "RaidenX8 API is up."

@app.route("/health", methods=["GET"])
def health():
    return "ok", 200

@app.route("/events", methods=["GET"])
def events():
    """
    Polling fallback for clients that can't use WebSocket.
    Optional query: ?since=unix_ts to get only newer items.
    """
    since = int(request.args.get("since", 0))
    data = [e for e in list(EVENTS) if e["ts"] > since]
    return jsonify({"events": data})

@app.route("/send", methods=["POST"])
def send():
    """
    Send a message to Telegram chat.
    Body JSON: { "text": "hello" }
    """
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
    return jsonify({"ok": ok, "tg": data}), (200 if ok else 500)

@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Telegram will POST updates here.
    Set your webhook to: https://<your-service>.onrender.com/webhook
    """
    update = request.get_json(silent=True) or {}
    msg = (update.get("message") or update.get("edited_message") or {})
    chat = msg.get("chat") or {}
    text = msg.get("text", "")

    info = {
        "from_chat_id": chat.get("id"),
        "from_title": chat.get("title") or f'{chat.get("first_name","")} {chat.get("last_name","")}'.strip(),
        "text": text,
        "raw": update
    }
    push_event("incoming", info)
    return jsonify({"ok": True})

# ---------- WebSocket namespace ----------
@socketio.on("connect", namespace="/ws")
def ws_connect():
    emit("ready", {"message": "connected", "ts": int(time.time())})

@socketio.on("send", namespace="/ws")
def ws_send(data):
    """
    Client emits: socket.emit('send', { text: 'hi' })
    We forward to Telegram like /send.
    """
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

# ---------- Optional: simple AI proxy (safe fallback) ----------
@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    Body: { "prompt": "..." }
    If OPENAI_API_KEY is missing, return a friendly canned reply.
    """
    body = request.get_json(silent=True) or {}
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "prompt is required"}), 400

    if not OPENAI_KEY:
        reply = "AI đang ở chế độ demo. Thêm OPENAI_API_KEY vào Render để bật trả lời thông minh."
        push_event("ai_reply", {"prompt": prompt, "reply": reply})
        return jsonify({"reply": reply})

    # (Để tối giản: chưa gọi API thật, tránh lỗi deploy nếu thiếu lib. Bạn muốn mình nối API thật thì mình thêm ngay.)
    reply = f"[AI stub] Bạn hỏi: {prompt}"
    push_event("ai_reply", {"prompt": prompt, "reply": reply})
    return jsonify({"reply": reply})

# ---------- Local run ----------
if __name__ == "__main__":
    # Use socketio runner to support WebSocket locally
    socketio.run(app, host="0.0.0.0", port=5000)
