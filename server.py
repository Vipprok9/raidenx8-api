# server.py
import os, time, threading, json
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import requests

API_NAME = "raidenx8-api"
FRONTEND = "https://raidenx8.pages.dev"

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

# CORS mở đủ method + headers + credentials (nếu cần)
CORS(
    app,
    resources={r"/*": {
        "origins": [FRONTEND, "*"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": False
    }},
)

# SocketIO: cho phép CORS từ Pages + fallback polling (Render free)
socketio = SocketIO(
    app,
    cors_allowed_origins=[FRONTEND, "*"],
    async_mode="gevent",   # hoặc "threading" nếu bạn không cài gevent
    ping_timeout=25,
    ping_interval=10
)

# === Helpers ===
def _ok(data=None, **kw):
    base = {"ok": True}
    if data and isinstance(data, dict):
        base.update(data)
    base.update(kw)
    return jsonify(base)

def _err(msg, code=400):
    return jsonify({"ok": False, "error": msg}), code

@app.after_request
def add_csp_headers(resp):
    # đảm bảo preflight không bị chặn (nếu CF Pages strict)
    resp.headers["Access-Control-Allow-Origin"] = FRONTEND
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp

@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def health():
    return _ok(service=API_NAME)

@app.route("/telegram/notify", methods=["POST", "OPTIONS"])
def telegram_notify():
    if request.method == "OPTIONS":
        return make_response("", 204)

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return _err("Missing TELEGRAM_BOT_TOKEN", 500)

    data = request.get_json(silent=True) or {}
    chat_id = str(data.get("chat_id") or "6142290415").strip()
    text = str(data.get("text") or "").strip()
    if not text:
        return _err("text required")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
    if r.ok:
        return _ok(sent=True, chat_id=chat_id)
    return _err(f"telegram_http_{r.status_code}", r.status_code)

# ---- Ticker ----
def get_prices():
    # Demo: lấy top BTC/ETH/BNB/SOL từ CoinGecko (đơn giản, không API key)
    ids = "bitcoin,ethereum,binancecoin,solana,tether,usd-coin,toncoin,matic-network"
    vs = "usd"
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies={vs}&include_24hr_change=true"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        raw = r.json()
        # đổi sang array cho frontend
        out = []
        mapping = {
            "bitcoin":"BTC","ethereum":"ETH","binancecoin":"BNB","solana":"SOL",
            "tether":"USDT","usd-coin":"USDC","toncoin":"TON","matic-network":"MATIC"
        }
        for k,v in mapping.items():
            if k in raw:
                out.append({
                    "symbol": v,
                    "price": raw[k]["usd"],
                    "change24h": raw[k].get("usd_24h_change", 0.0)
                })
        return out
    except Exception as e:
        return {"error": str(e)}

@app.route("/ticker", methods=["GET", "OPTIONS"])
def ticker_http():
    if request.method == "OPTIONS":
        return make_response("", 204)
    data = get_prices()
    if isinstance(data, dict) and "error" in data:
        return _err(data["error"], 502)
    return _ok(prices=data, ts=int(time.time()))

# Emit qua socket mỗi 30s
def ticker_loop():
    while True:
        data = get_prices()
        if not (isinstance(data, dict) and "error" in data):
            socketio.emit("ticker", {"prices": data, "ts": int(time.time())})
        time.sleep(30)

@socketio.on("connect")
def on_connect():
    emit("hello", {"msg": "socket connected", "service": API_NAME})

def ensure_bg():
    t = threading.Thread(target=ticker_loop, daemon=True)
    t.start()

if __name__ == "__main__":
    ensure_bg()
    # local run
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
