import os, time, threading, requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit

APP_NAME = "raidenx8-api"

# ====== Flask & Socket.IO ======
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",     # tránh eventlet/gevent
    ping_interval=25,
    ping_timeout=60,
)

# ====== ENV ======
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DEFAULT_CHAT_ID    = os.getenv("DEFAULT_CHAT_ID", "6142290415")

OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY", "")

COINGECKO_IDS = os.getenv(
    "COINGECKO_IDS",
    "bitcoin,ethereum,tether,binancecoin,solana,toncoin"
)
CG_INTERVAL = int(os.getenv("CG_INTERVAL_SECONDS", "30"))

# ====== STATE ======
prices_cache = {}     # {symbol: {price, change_24h}}
last_fetch_ts = 0

# ====== HELPERS ======
def fetch_coingecko(ids: str):
    url = (
        "https://api.coingecko.com/api/v3/coins/markets"
        f"?vs_currency=usd&ids={ids}&price_change_percentage=24h"
    )
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    out = {}
    for it in r.json():
        sym = it.get("symbol","").upper()
        out[sym] = {
            "name": it.get("name"),
            "price": it.get("current_price"),
            "change_24h": it.get("price_change_percentage_24h_in_currency"),
        }
    return out

def broadcast_prices(src="poll"):
    socketio.emit("prices", {"prices": prices_cache, "source": src})

def coingecko_loop():
    global prices_cache, last_fetch_ts
    while True:
        try:
            data = fetch_coingecko(COINGECKO_IDS)
            prices_cache = data
            last_fetch_ts = int(time.time())
            broadcast_prices("coingecko")
        except Exception as e:
            print("[coingecko] error:", e)
        time.sleep(CG_INTERVAL)

# ====== ROUTES ======
@app.route("/")
def root():
    return jsonify({"ok": True, "service": APP_NAME})

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": APP_NAME,
        "prices": len(prices_cache),
        "last_fetch_ts": last_fetch_ts
    })

@app.route("/prices")
def get_prices():
    return jsonify({"prices": prices_cache, "ts": last_fetch_ts})

@app.route("/notify", methods=["POST"])
def notify():
    if not TELEGRAM_BOT_TOKEN:
        return jsonify({"ok": False, "error": "TELEGRAM_BOT_TOKEN missing"}), 400
    data = request.get_json(force=True, silent=True) or {}
    chat_id = str(data.get("chat_id") or DEFAULT_CHAT_ID)
    text    = data.get("text") or "Hi from RaidenX8"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    res = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=30)
    return jsonify(res.json()), (200 if res.ok else 500)

@app.route("/notify/test")
def notify_test():
    if not TELEGRAM_BOT_TOKEN:
        return jsonify({"ok": False, "error": "TELEGRAM_BOT_TOKEN missing"}), 400
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    res = requests.post(url, json={"chat_id": DEFAULT_CHAT_ID, "text": "RaidenX8 test ✅"}, timeout=30)
    return jsonify(res.json()), (200 if res.ok else 500)

# ====== AI (mở tuỳ env) ======
@app.route("/ai", methods=["POST"])
def ai_chat():
    data = request.get_json(force=True, silent=True) or {}
    provider = (data.get("provider") or "openai").lower()
    prompt   = data.get("prompt") or ""
    if not prompt.strip():
        return jsonify({"ok": False, "error": "empty prompt"}), 400

    try:
        if provider == "openai":
            if not OPENAI_API_KEY:
                return jsonify({"ok": False, "error": "OPENAI_API_KEY missing"}), 400
            # Minimal OpenAI Responses API (兼容 gpt-4o-mini / o4-mini nếu bật)
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
            payload = {
                "model": "gpt-4o-mini",
                "messages": [{"role":"user", "content": prompt}],
                "temperature": 0.7
            }
            r = requests.post(url, json=payload, headers=headers, timeout=60)
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]["content"]
            return jsonify({"ok": True, "provider": "openai", "text": msg})

        elif provider == "gemini":
            if not GEMINI_API_KEY:
                return jsonify({"ok": False, "error": "GEMINI_API_KEY missing"}), 400
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
            payload = {"contents":[{"parts":[{"text": prompt}]}]}
            r = requests.post(url, json=payload, timeout=60)
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return jsonify({"ok": True, "provider": "gemini", "text": text})

        else:
            return jsonify({"ok": False, "error": "unsupported provider"}), 400

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ====== SOCKET.IO ======
@socketio.on("connect")
def on_connect():
    emit("server", {"ok": True, "msg": "socket connected"})
    emit("prices", {"prices": prices_cache, "source": "init"})

@socketio.on("pingme")
def on_ping(_=None):
    emit("pongme", {"ts": int(time.time())})

def _start_bg():
    t = threading.Thread(target=coingecko_loop, daemon=True)
    t.start()

# ====== ENTRY ======
if __name__ == "__main__":
    _start_bg()
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
