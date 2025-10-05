from gevent import monkey
monkey.patch_all()

import os, time, threading, requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# ===== CONFIG =====
API_BASE = "https://api.coingecko.com/api/v3/simple/price"
SYMS = [
    ("bitcoin","BTC"),
    ("ethereum","ETH"),
    ("binancecoin","BNB"),
    ("solana","SOL"),
    ("ripple","XRP"),
    ("toncoin","TON"),
    ("tether","USDT"),
]
FETCH_INTERVAL = 30

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent")

_prices = {}
_prices_lock = threading.Lock()

# ===== PRICE FETCH =====
def fetch_prices_once():
    ids = ",".join([x[0] for x in SYMS])
    params = {"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true"}
    r = requests.get(API_BASE, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    out = []
    for cg_id, sym in SYMS:
        j = data.get(cg_id, {})
        price = float(j.get("usd", 0.0))
        change = float(j.get("usd_24h_change", 0.0))
        out.append({"symbol": sym, "price": price, "change_24h": change})
    return out

def bg_loop():
    global _prices
    while True:
        try:
            arr = fetch_prices_once()
            with _prices_lock:
                _prices = {i["symbol"]: i for i in arr}
            socketio.emit("prices", {"data": arr})
        except Exception as e:
            print("Ticker error:", e)
        time.sleep(FETCH_INTERVAL)

@app.get("/health")
def health():
    return "ok"

@app.get("/prices")
def prices():
    with _prices_lock:
        arr = list(_prices.values()) if _prices else fetch_prices_once()
    return jsonify({"data": arr})

# ===== AI via REST (fallback) =====
@app.post("/ai/chat")
def ai_chat():
    data = request.get_json(force=True)
    return jsonify({"reply": run_ai(data.get("message",""), data.get("provider","openai"))})

# ===== AI via WebSocket (2‑way) =====
@socketio.on("chat")
def ws_chat(payload):
    msg = (payload or {}).get("message","")
    provider = (payload or {}).get("provider","openai")
    try:
        reply = run_ai(msg, provider)
    except Exception as e:
        reply = f"[AI error] {e}"
    emit("chat_reply", {"reply": reply})

def run_ai(user_msg: str, provider: str = "openai") -> str:
    provider = (provider or "openai").lower()
    if provider == "gemini" and GEMINI_KEY:
        # Gemini 1.5 Pro
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={GEMINI_KEY}"
        payload = {"contents":[{"role":"user","parts":[{"text": user_msg}]}]}
        r = requests.post(url, json=payload, timeout=30)
        j = r.json()
        return j["candidates"][0]["content"]["parts"][0]["text"]
    else:
        # OpenAI GPT‑4o‑mini
        import openai
        openai.api_key = OPENAI_KEY
        # Using legacy-style API for simplicity
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role":"system","content":"Bạn là trợ lý AI thân thiện, trả lời ngắn gọn bằng tiếng Việt."},
                {"role":"user","content":user_msg}
            ]
        )
        return resp["choices"][0]["message"]["content"].strip()

# ===== Telegram Notify =====
@app.post("/notify-telegram")
def notify():
    text = request.json.get("text","")
    if not TELEGRAM_BOT_TOKEN or not (TELEGRAM_CHAT_ID or request.json.get("chat_id")):
        return jsonify({"error":"Missing TELEGRAM_BOT_TOKEN or chat_id"}), 400
    chat_id = request.json.get("chat_id") or TELEGRAM_CHAT_ID
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text}, timeout=8
        )
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def _ensure_bg():
    t = threading.Thread(target=bg_loop, daemon=True)
    t.start()

_ensure_bg()

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT","5000")))
