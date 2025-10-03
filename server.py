import os, time, json, requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}, r"/socket.io/*": {"origins": "*"}})

# WebSocket (Socket.IO)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet", logger=False, engineio_logger=False)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DEFAULT_TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

CACHE_SECONDS = 20
_cache = {"ts": 0, "data": None}

def err(msg, code=400): return jsonify({"ok": False, "error": msg}), code

@app.get("/health")
def health(): return jsonify({"ok": True, "ts": int(time.time())})

# ---------- Prices (CoinGecko) ----------
@app.get("/api/prices")
def prices():
    ids = request.args.get("ids", "bitcoin,ethereum,bnb,toncoin,tether")
    vs  = request.args.get("vs",  "usd")
    now = time.time()
    if _cache["data"] and (now - _cache["ts"] < CACHE_SECONDS):
        return jsonify({"ok": True, "cached": True, "data": _cache["data"]})
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        r = requests.get(url, params={"ids": ids, "vs_currencies": vs, "include_24hr_change": "true"}, timeout=8)
        r.raise_for_status()
        data = r.json()
        _cache["ts"], _cache["data"] = now, data
        socketio.emit("prices", {"at": int(now), "source": "live"})
        return jsonify({"ok": True, "cached": False, "data": data})
    except Exception:
        demo = {
            "bitcoin":  {"usd": 120334, "usd_24h_change": 1.17},
            "ethereum": {"usd": 4477.91, "usd_24h_change": 2.02},
            "bnb":      {"usd": 1109.20, "usd_24h_change": 5.16},
            "toncoin":  {"usd": None,   "usd_24h_change": None},
            "tether":   {"usd": 1,      "usd_24h_change": 0.0},
        }
        socketio.emit("prices", {"at": int(now), "source": "demo"})
        return jsonify({"ok": True, "cached": True, "source": "fallback-demo", "data": demo})

# ---------- Telegram Notify ----------
@app.post("/api/notify")
def notify():
    if not TELEGRAM_BOT_TOKEN: return err("Missing TELEGRAM_BOT_TOKEN.")
    body = request.get_json(silent=True) or {}
    message = (body.get("message") or body.get("text") or "").strip()
    chat_id = str(body.get("chat_id") or DEFAULT_TELEGRAM_CHAT_ID).strip()
    if not message: return err("Message is required.")
    if not chat_id: return err("chat_id required (or set TELEGRAM_CHAT_ID env).")
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        r = requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
        r.raise_for_status()
        socketio.emit("notify", {"ok": True, "chat_id": chat_id})
        return jsonify({"ok": True, "result": r.json()})
    except Exception as e:
        socketio.emit("notify", {"ok": False, "error": str(e)})
        return err(f"Telegram error: {e}", 502)

# ---------- AI Chat Proxy ----------
@app.post("/api/chat")
def chat():
    body = request.get_json(silent=True) or {}
    provider = (body.get("provider") or "openai").lower()
    prompt   = (body.get("prompt") or body.get("message") or "").strip()
    system   = body.get("system") or "You are a helpful assistant for Web3/Airdrop/DeFi."
    if not prompt: return err("prompt is required.")
    try:
        if provider == "gemini":
            if not GEMINI_API_KEY: return err("Missing GEMINI_API_KEY.")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={GEMINI_API_KEY}"
            payload = {"contents":[{"parts":[{"text": f"{system}\n\nUser: {prompt}"}]}]}
            r = requests.post(url, json=payload, timeout=25); r.raise_for_status()
            data = r.json()
            text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            socketio.emit("ai", {"provider": "gemini", "ok": True})
            return jsonify({"ok": True, "provider": "gemini", "text": text})
        # OpenAI
        if not OPENAI_API_KEY: return err("Missing OPENAI_API_KEY.")
        url = "https://api.openai.com/v1/responses"
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type":"application/json"}
        payload = {"model":"gpt-4o-mini","input":[{"role":"system","content":system},{"role":"user","content":prompt}]}
        r = requests.post(url, headers=headers, json=payload, timeout=25); r.raise_for_status()
        data = r.json()
        text = data.get("output_text") if isinstance(data.get("output_text"), str) else json.dumps(data)[:1200]
        socketio.emit("ai", {"provider": "openai", "ok": True})
        return jsonify({"ok": True, "provider": "openai", "text": text})
    except Exception as e:
        socketio.emit("ai", {"ok": False, "error": str(e)})
        return err(f"AI error: {e}", 502)

# ---------- WS Handlers ----------
@socketio.on("connect")
def on_connect(): emit("system", {"hello": "connected to RaidenX8 WS 👋"})

@socketio.on("ping")
def on_ping(_): emit("pong", {"ts": int(time.time())})

@socketio.on("chat")
def on_chat(data):
    msg = (data or {}).get("text", "")
    emit("chat", {"from": "server", "reply": f"got: {msg}"}, broadcast=True)

@app.get("/")
def index(): return jsonify({"ok": True, "service": "RaidenX8 API (WS+REST)"})


if __name__ == "__main__":
    # eventlet để WS mượt trên Render
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
