import os
import time
from collections import deque

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import requests

# ---------- App ----------
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# ---------- Env ----------
BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")  # (optional)

# ---------- Events buffer ----------
EVENTS = deque(maxlen=200)

def push_event(kind, payload):
    """Chỉ đẩy dữ liệu dạng dict đơn giản, KHÔNG đẩy objects lạ."""
    evt = {
        "ts": int(time.time()),
        "kind": kind,
        "data": payload,
    }
    EVENTS.append(evt)
    socketio.emit("message", evt, namespace="/ws")
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
    # có thể lọc theo ?since=<unix_ts>
    since = request.args.get("since", type=int)
    if since:
        data = [e for e in list(EVENTS) if e["ts"] >= since]
    else:
        data = list(EVENTS)
    return jsonify({"events": data})

@app.route("/send", methods=["POST"])
def send():
    """
    Gửi tin nhắn đến Telegram.
    Body JSON: { "text": "hello" }
    """
    if not BOT_TOKEN or not CHAT_ID:
        return jsonify({"ok": False, "error": "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID"}), 400

    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "text is empty"}), 400

    # gọi Telegram
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=10)
        ok = r.ok
        # chỉ lấy json gọn, tránh objects/phức tạp
        tg = {}
        try:
            tg = r.json()
        except Exception:
            tg = {"note": "non-json response"}

        # log event gọn
        push_event("outgoing", {"text": text, "ok": ok, "status": r.status_code})
        return jsonify({"ok": ok, "status": r.status_code, "tg_ok": tg.get("ok")})
    except Exception as e:
        push_event("error", {"where": "/send", "msg": str(e)})
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Telegram POST update vào đây (nếu bạn dùng webhook).
    Lưu ý: chỉ log phần gọn để tránh đệ quy/too deep.
    """
    upd = request.get_json(silent=True) or {}
    msg = (upd.get("message") or {})
    chat = msg.get("chat") or {}
    preview = {
        "from_chat_id": chat.get("id"),
        "from_title": chat.get("title") or chat.get("username") or chat.get("first_name"),
        "text": msg.get("text", ""),
    }
    push_event("incoming", preview)

    # Optional: auto-echo
    try:
        if BOT_TOKEN and preview["from_chat_id"] and preview["text"]:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            requests.post(url, json={
                "chat_id": preview["from_chat_id"],
                "text": f"Echo: {preview['text']}"
            }, timeout=10)
    except Exception as e:
        push_event("error", {"where": "webhook-echo", "msg": str(e)})

    return jsonify({"ok": True})

# ---------- WebSocket ----------
@socketio.on("connect", namespace="/ws")
def ws_connect():
    emit("ready", {"message": "connected", "ts": int(time.time())})

@socketio.on("send", namespace="/ws")
def ws_send(data):
    """
    Client gửi qua WS: { "text": "..." } -> forward như /send
    """
    text = (data or {}).get("text", "").strip()
    if not text:
        emit("error", {"error": "text is empty"})
        return

    if not BOT_TOKEN or not CHAT_ID:
        emit("error", {"error": "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID"})
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=10)
        push_event("outgoing", {"text": text, "ok": r.ok, "status": r.status_code})
    except Exception as e:
        push_event("error", {"where": "ws_send", "msg": str(e)})

# ---------- Main (local only) ----------
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=8000)
