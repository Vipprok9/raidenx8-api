import os
import time
import json
from collections import deque

import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# ========= App & realtime =========
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ========= ENV =========
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")

# ========= Event buffer for UI log =========
EVENTS = deque(maxlen=200)

def push_event(kind: str, data):
    evt = {"ts": int(time.time()), "kind": kind, "data": data}
    EVENTS.append(evt)
    # broadcast to WS clients
    socketio.emit("message", evt, namespace="/ws")
    return evt

# ========= Routes =========
@app.route("/", methods=["GET"])
def root():
    return "RaidenX8 API is up."

@app.route("/health", methods=["GET"])
def health():
    return "ok", 200

@app.route("/events", methods=["GET"])
def events():
    """Polling fallback for the front-end."""
    try:
        since = int(request.args.get("since", "0"))
    except ValueError:
        since = 0
    data = [e for e in list(EVENTS) if e["ts"] >= since]
    # chỉ trả JSON đơn giản -> tránh recursion
    return jsonify({"events": data})

@app.route("/send", methods=["POST"])
def send():
    """
    Front-end gọi để gửi msg lên Telegram.
    Body JSON: { "text": "hello" }
    """
    if not BOT_TOKEN or not CHAT_ID:
        push_event("error", {"where": "/send", "msg": "Missing TELEGRAM_* env"})
        return jsonify({"ok": False, "error": "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID"}), 500

    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "text is empty"}), 400

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=15)
        ok = resp.ok
        # parse JSON an toàn
        try:
            tg = resp.json()
        except Exception:
            tg = {"raw": resp.text}
        push_event("outgoing", {"text": text, "ok": ok})
        return jsonify({"ok": ok, "tg": tg})
    except Exception as e:
        push_event("error", {"where": "/send", "msg": str(e)})
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Telegram sẽ POST update vào đây.
    Nhớ set webhook: https://api.telegram.org/bot<token>/setWebhook?url=https://<render-app>/webhook
    """
    update = request.get_json(silent=True) or {}
    # rút gọn thông tin để log
    msg = (update.get("message") or update.get("edited_message") or {})
    chat = msg.get("chat") or {}
    text = msg.get("text", "")

    info = {
        "from_chat_id": chat.get("id"),
        "from_title": chat.get("title") or chat.get("username") or chat.get("first_name"),
        "text": text,
        "raw": {"update_id": update.get("update_id")}
    }
    push_event("incoming", info)
    return jsonify({"ok": True})

# ========= WebSocket =========
@socketio.on("connect", namespace="/ws")
def ws_connect():
    emit("ready", {"message": "connected", "ts": int(time.time())})

@socketio.on("send", namespace="/ws")
def ws_send(data):
    """
    Front-end có thể emit 'send' qua WS: { "text": "..." }
    Mình forward giống như /send nhưng KHÔNG gọi chính ws_send nữa -> tránh recursion.
    """
    text = (data or {}).get("text", "").strip()
    if not text:
        emit("error", {"error": "text is empty"})
        return

    if not BOT_TOKEN or not CHAT_ID:
        emit("error", {"error": "Missing TELEGRAM_* env"})
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=15)
        ok = resp.ok
        try:
            tg = resp.json()
        except Exception:
            tg = {"raw": resp.text}
        push_event("outgoing", {"text": text, "ok": ok})
        emit("sent", {"ok": ok, "tg": tg})
    except Exception as e:
        push_event("error", {"where": "ws_send", "msg": str(e)})
        emit("error", {"error": str(e)})

# ========= Optional: simple AI echo for demo =========
@app.route("/api/chat", methods=["POST"])
def api_chat():
    body = request.get_json(silent=True) or {}
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "prompt is empty"}), 400

    # Chưa nối OpenAI thì trả lời stub
    reply = f"[AI stub] Bạn hỏi: {prompt}"
    push_event("ai_reply", {"prompt": prompt, "reply": reply})
    return jsonify({"reply": reply})

# ========= Entrypoint =========
if __name__ == "__main__":
    # Render cung cấp PORT env
    port = int(os.getenv("PORT", "8000"))
    socketio.run(app, host="0.0.0.0", port=port)
