import os, requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# ===== ENV =====
BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TG_API     = f"https://api.telegram.org/bot{BOT_TOKEN}"

ALLOWED_ORIGINS = [
    "https://raidenx8.pages.dev",   # frontend Cloudflare Pages của bạn
    "*"                              # có thể siết lại khi lên prod
]

# ===== App / Socket =====
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGINS}})
socketio = SocketIO(app, cors_allowed_origins=ALLOWED_ORIGINS, async_mode="eventlet")

# ===== Utils =====
def tg_send(text: str, chat_id: str = None):
    """Gửi tin nhắn Telegram; trả về dict JSON từ Telegram API."""
    chat_id = chat_id or TG_CHAT_ID
    if not BOT_TOKEN or not chat_id:
        return {"ok": False, "error": "missing_token_or_chat_id"}
    try:
        r = requests.post(f"{TG_API}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=15)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

def log(msg: str, level="info", payload=None):
    """Phát log về tất cả client qua WS + in server log."""
    data = {"level": level, "msg": msg, "payload": payload or {}}
    try:
        socketio.emit("log", data, broadcast=True)
    except Exception:
        pass
    print(f"[{level}] {msg}", payload or "")

# ===== Routes =====
@app.route("/health")
def health():
    return "ok", 200

@app.route("/send", methods=["POST", "OPTIONS"])
def send_message():
    # Preflight cho CORS
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    chat_id = str(data.get("chat_id") or TG_CHAT_ID)

    if not text:
        return jsonify({"ok": False, "error": "empty_text"}), 400

    tg_res = tg_send(text, chat_id)
    ok = bool(tg_res.get("ok"))
    log("send_from_http", payload={"text": text, "ok": ok, "tg": tg_res})
    return jsonify(tg_res), (200 if ok else 500)

# ===== Socket.IO events =====
@socketio.on("connect")
def on_connect():
    emit("log", {"level": "info", "msg": "client_connected"})
    print("[ws] client connected")

@socketio.on("disconnect")
def on_disconnect():
    print("[ws] client disconnected")

@socketio.on("chat")
def on_chat(data):
    """
    Client gửi: socket.emit('chat', { text: 'hello', chat_id: optional })
    Server forward Telegram + broadcast log.
    """
    text = (data.get("text") if isinstance(data, dict) else "") or ""
    chat_id = str(data.get("chat_id") or TG_CHAT_ID) if isinstance(data, dict) else TG_CHAT_ID
    if not text.strip():
        emit("log", {"level": "warn", "msg": "empty_text_from_ws"})
        return
    tg_res = tg_send(text, chat_id)
    emit("log", {"level": "info", "msg": "send_from_ws", "payload": {"ok": tg_res.get("ok"), "tg": tg_res}}, broadcast=True)

# ===== Main =====
if __name__ == "__main__":
    # eventlet được chọn trong Procfile; cổng Render cung cấp qua PORT
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
