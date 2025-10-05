from gevent import monkey
monkey.patch_all()

import os, time, threading, requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# ===== Config =====
API_BASE = "https://api.coingecko.com/api/v3/simple/price"
SYMS = [
    ("bitcoin","BTC"),("ethereum","ETH"),("binancecoin","BNB"),
    ("solana","SOL"),("ripple","XRP"),("toncoin","TON"),("tether","USDT")
]
FETCH_INTERVAL = int(os.getenv("FETCH_INTERVAL", "30"))
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_KEY  = os.getenv("GEMINI_API_KEY", "")

# ===== App =====
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")  # WebSocket 2 chiều

_prices = {}
_lock = threading.Lock()

def fetch_once():
    ids = ",".join([i[0] for i in SYMS])
    p = {"ids": ids, "vs_currencies":"usd", "include_24hr_change":"true"}
    r = requests.get(API_BASE, params=p, timeout=12)
    r.raise_for_status()
    data = r.json()
    out = []
    for cg, sym in SYMS:
        j = data.get(cg, {})
        out.append({
            "symbol": sym,
            "price": float(j.get("usd", 0.0)),
            "change": float(j.get("usd_24h_change", 0.0)),
        })
    return out

def bg_loop():
    global _prices
    while True:
        try:
            arr = fetch_once()
            with _lock:
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
    with _lock:
        arr = list(_prices.values())
    return jsonify({"data": arr})

# REST fallback cho AI (phòng khi không dùng WS)
@app.post("/ai/chat")
def ai_chat():
    d = request.get_json(force=True) or {}
    return jsonify({"reply": run_ai(d.get("message",""), d.get("provider","openai"))})

# WebSocket 2 chiều cho AI
@socketio.on("chat")
def ws_chat(payload):
    msg = (payload or {}).get("message","")
    provider = (payload or {}).get("provider","openai")
    try:
        reply = run_ai(msg, provider)
    except Exception as e:
        reply = f"[AI error] {e}"
    emit("chat_reply", {"reply": reply})

def run_ai(text: str, provider: str):
    text = (text or "").strip() or "Xin chào từ RaidenX8!"
    if provider == "gemini" and GEMINI_KEY:
        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               "gemini-1.5-flash:generateContent?key=" + GEMINI_KEY)
        payload = {"contents":[{"parts":[{"text": text}]}]}
        r = requests.post(url, json=payload, timeout=30)
        j = r.json()
        try:
            return j["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            return str(j)[:800]
    else:
        import openai
        openai.api_key = OPENAI_KEY
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role":"system","content":"You are RaidenX8 assistant."},
                {"role":"user","content": text},
            ]
        )
        return resp["choices"][0]["message"]["content"]

# Khởi động ticker nền
def _start():
    threading.Thread(target=bg_loop, daemon=True).start()
_start()

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT","10000")))
