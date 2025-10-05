# ============================================================
# RaidenX8 API — Flask-SocketIO (gevent-websocket)
# - /prices: giá crypto có cache + backoff (giảm rate-limit)
# - WS 'prices': đẩy realtime
# - WS 'chat'  : AI 2 chiều (OpenAI/Gemini) + rate-limit
# - /ai/chat   : REST fallback
# ============================================================

from gevent import monkey
monkey.patch_all()

import os, time, threading, requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# ---------- Config ----------
API_BASE = "https://api.coingecko.com/api/v3/simple/price"
SYMS = [
    ("bitcoin","BTC"), ("ethereum","ETH"), ("binancecoin","BNB"),
    ("solana","SOL"), ("ripple","XRP"), ("toncoin","TON"), ("tether","USDT")
]
FETCH_INTERVAL = int(os.getenv("FETCH_INTERVAL", "45"))   # giãn nhịp để đỡ limit
OPENAI_KEY     = os.getenv("OPENAI_API_KEY", "")
GEMINI_KEY     = os.getenv("GEMINI_API_KEY", "")
CHAT_MIN_INTERVAL = float(os.getenv("CHAT_MIN_INTERVAL", "1.2"))  # giây / IP

# ---------- App ----------
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

_prices_cache = {"data": [], "ts": 0}
_cache_lock   = threading.Lock()

# nhớ thời điểm chat cuối theo IP (rate-limit đơn giản)
_client_last  = {}
_rl_lock      = threading.Lock()

# ---------- Price fetch ----------
def fetch_prices_once():
    ids = ",".join(i[0] for i in SYMS)
    p = {"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true"}
    r = requests.get(API_BASE, params=p, timeout=12)
    r.raise_for_status()
    data = r.json()
    out = []
    for cg, sym in SYMS:
        j = data.get(cg, {})
        out.append({
            "symbol": sym,
            "price":  float(j.get("usd", 0.0)),
            "change": float(j.get("usd_24h_change", 0.0)),
        })
    return out

def ticker_loop():
    """vòng lặp nền: lấy giá, cache, emit WS; có backoff khi lỗi"""
    global _prices_cache
    backoff = 0
    while True:
        try:
            arr = fetch_prices_once()
            with _cache_lock:
                _prices_cache = {"data": arr, "ts": time.time()}
            socketio.emit("prices", {"data": arr})
            backoff = 0
        except Exception as e:
            print("Ticker error:", e)
            backoff = min(backoff + 10, 120)  # tăng dần khi lỗi
        time.sleep(max(FETCH_INTERVAL, backoff))

# ---------- Routes ----------
@app.get("/health")
def health():
    return "ok"

@app.get("/prices")
def prices():
    """trả cache ngay lập tức; nếu stale >5 phút sẽ cố refresh 1 lần"""
    with _cache_lock:
        data = _prices_cache["data"]
        ts   = _prices_cache["ts"]
    if time.time() - ts > 300:
        try:
            fresh = fetch_prices_once()
            with _cache_lock:
                _prices_cache["data"] = fresh
                _prices_cache["ts"]   = time.time()
            data = fresh
        except Exception:
            pass
    return jsonify({"data": data})

@app.post("/ai/chat")
def ai_chat():
    d = request.get_json(force=True) or {}
    ip = request.headers.get("x-forwarded-for", request.remote_addr) or "na"
    if not allow_chat(ip):
        return jsonify({"reply": "[rate-limit] vui lòng thử lại sau"}), 429
    return jsonify({"reply": run_ai(d.get("message",""), d.get("provider","openai"))})

# ---------- WebSocket ----------
@socketio.on("chat")
def ws_chat(payload):
    msg = (payload or {}).get("message","")
    provider = (payload or {}).get("provider","openai")
    ip = request.headers.get("x-forwarded-for", request.remote_addr) or "na"
    if not allow_chat(ip):
        emit("chat_reply", {"reply":"[rate-limit] thử lại sau giây lát"}); return
    try:
        reply = run_ai(msg, provider)
    except Exception as e:
        reply = f"[AI error] {e}"
    emit("chat_reply", {"reply": reply})

# ---------- Helpers ----------
def allow_chat(ip: str) -> bool:
    now = time.time()
    with _rl_lock:
        last = _client_last.get(ip, 0)
        if now - last < CHAT_MIN_INTERVAL:
            return False
        _client_last[ip] = now
    return True

def run_ai(text: str, provider: str) -> str:
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
                {"role":"system","content":"You are RaidenX8 assistant. Be concise and friendly."},
                {"role":"user","content": text},
            ],
            timeout=30
        )
        return resp["choices"][0]["message"]["content"]

# ---------- Boot ----------
def _start_bg():
    threading.Thread(target=ticker_loop, daemon=True).start()
_start_bg()

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT","10000")))
