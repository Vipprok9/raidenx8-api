import os, time, threading, json
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import requests

FRONTEND = os.getenv("FRONTEND_ORIGIN", "https://raidenx8.pages.dev")
API_NAME = "raidenx8-api"

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": [FRONTEND, "*"], "supports_credentials": False}})

socketio = SocketIO(
    app, cors_allowed_origins=[FRONTEND, "*"],
    async_mode="threading", ping_timeout=25, ping_interval=10
)

def ok(**k): return jsonify({"ok": True, **k})
def err(msg, code=400): return jsonify({"ok": False, "error": msg}), code

@app.after_request
def cors_headers(r):
    r.headers["Access-Control-Allow-Origin"]  = FRONTEND
    r.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    r.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return r

@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def health(): return ok(service=API_NAME)

@app.route("/telegram/notify", methods=["POST", "OPTIONS"])
def notify():
    if request.method == "OPTIONS": return make_response("", 204)
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token: return err("Missing TELEGRAM_BOT_TOKEN", 500)
    data = request.get_json(silent=True) or {}
    chat_id = str(data.get("chat_id") or "6142290415").strip()
    text = (data.get("text") or "").strip()
    if not text: return err("text required")
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat_id, "text": text}, timeout=10)
    return ok(sent=True, chat_id=chat_id) if r.ok else err(f"telegram_{r.status_code}", r.status_code)

def fetch_prices():
    ids = "bitcoin,ethereum,binancecoin,solana,tether,usd-coin,toncoin,matic-network"
    url = ("https://api.coingecko.com/api/v3/simple/price"
           f"?ids={ids}&vs_currencies=usd&include_24hr_change=true")
    mapping = {"bitcoin":"BTC","ethereum":"ETH","binancecoin":"BNB","solana":"SOL",
               "tether":"USDT","usd-coin":"USDC","toncoin":"TON","matic-network":"MATIC"}
    r = requests.get(url, timeout=10); r.raise_for_status(); raw = r.json()
    out = []
    for k,sym in mapping.items():
        if k in raw:
            out.append({"symbol": sym, "price": raw[k]["usd"], 
                        "change24h": raw[k].get("usd_24h_change", 0.0)})
    return out

@app.route("/ticker", methods=["GET", "OPTIONS"])
def ticker_http():
    if request.method == "OPTIONS": return make_response("", 204)
    try: return ok(prices=fetch_prices(), ts=int(time.time()))
    except Exception as e: return err(str(e), 502)

def ticker_emitter():
    while True:
        try:
            socketio.emit("ticker", {"prices": fetch_prices(), "ts": int(time.time())})
        except Exception: pass
        time.sleep(30)

@socketio.on("connect")
def on_connect(): emit("hello", {"msg": "socket connected", "service": API_NAME})

# === AI proxy (tối giản, chỉ echo để demo; bật khi có key) ===
@app.route("/ai/ask", methods=["POST", "OPTIONS"])
def ai_ask():
    if request.method == "OPTIONS": return make_response("", 204)
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text: return err("text required")
    # TODO: gọi OpenAI/Gemini nếu muốn; hiện tại echo để UI hoạt động
    return ok(reply=f"Echo: {text}")

def boot():
    threading.Thread(target=ticker_emitter, daemon=True).start()

if __name__ == "__main__":
    boot()
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
