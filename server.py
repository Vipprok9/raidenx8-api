# server.py  — RaidenX8 API (Render + Socket.IO, gthread)
# ------------------------------------------------------
# Features:
#  - /health
#  - /notify  -> Telegram sendMessage
#  - /prices  -> Proxy CoinGecko (BTC, ETH, BNB, USDT, SOL, TON)
#  - Socket.IO:
#       * 'ticker:subscribe'  -> server đẩy giá định kỳ
#       * 'ai:message'        -> gọi OpenAI/Gemini rồi bắn 'ai:chunk' / 'ai:done'
#
# Env vars cần có (Render dashboard):
#   TELEGRAM_BOT_TOKEN, OPENAI_API_KEY (tuỳ chọn), GEMINI_API_KEY (tuỳ chọn)

import os, time, threading, json, requests
from typing import Dict, Any, List
from flask import Flask, jsonify, request
from flask_socketio import SocketIO, emit

# ------------------- App & Socket.IO -------------------
app = Flask(__name__)
socketio = SocketIO(
    app,
    async_mode="threading",           # dùng gthread bên gunicorn
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False
)

# ------------------- Config -------------------
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TICKER_INTERVAL  = int(os.getenv("TICKER_INTERVAL", "30"))

COINS = [
    # (coingecko id, symbol hiển thị)
    ("bitcoin",      "BTC"),
    ("ethereum",     "ETH"),
    ("binancecoin",  "BNB"),
    ("tether",       "USDT"),
    ("solana",       "SOL"),
    ("the-open-network", "TON"),
]

CG_ENDPOINT = "https://api.coingecko.com/api/v3/simple/price"

# cache giá để tránh gọi quá nhiều
_prices_cache: Dict[str, Any] = {"ts": 0, "data": []}
_prices_lock = threading.Lock()

# ------------------- Helpers -------------------
def cg_fetch_prices() -> List[Dict[str, Any]]:
    ids = ",".join([c[0] for c in COINS])
    params = {"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true"}
    r = requests.get(CG_ENDPOINT, params=params, timeout=20)
    r.raise_for_status()
    j = r.json()

    out = []
    for cid, sym in COINS:
        item = j.get(cid) or {}
        price = item.get("usd")
        chg   = item.get("usd_24h_change")
        if price is None:
            continue
        # làm tròn nhẹ cho UI
        try:
            p = float(price)
            c = float(chg) if chg is not None else 0.0
        except Exception:
            p, c = price, chg or 0
        out.append({"symbol": sym, "price": p, "change24h": c})
    return out

def get_prices_cached(force=False) -> List[Dict[str, Any]]:
    now = time.time()
    with _prices_lock:
        if force or now - _prices_cache["ts"] > 25:
            try:
                _prices_cache["data"] = cg_fetch_prices()
                _prices_cache["ts"] = now
            except Exception as e:
                # nếu lỗi, giữ cache cũ
                print("[prices] fetch error:", e)
        return _prices_cache["data"]

def chunk_emit(text: str, mid: str):
    """Bắn text theo từng khối nhỏ để UI thấy 'stream'."""
    CHUNK = 200
    for i in range(0, len(text), CHUNK):
        emit("ai:chunk", {"id": mid, "content": text[i:i+CHUNK]})
        socketio.sleep(0.03)

# ------------------- HTTP endpoints -------------------
@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "raidenx8-api"})

@app.get("/prices")
def prices_endpoint():
    force = request.args.get("force") == "1"
    data = get_prices_cached(force=force)
    return jsonify({"ok": True, "data": data})

@app.post("/notify")
def notify():
    if not TELEGRAM_BOT_TOKEN:
        return jsonify({"ok": False, "error": "TELEGRAM_BOT_TOKEN missing"}), 400
    payload = request.get_json(force=True, silent=True) or {}
    chat_id = payload.get("chat_id")
    text    = payload.get("text")
    if not chat_id or not text:
        return jsonify({"ok": False, "error": "chat_id and text required"}), 400

    tg = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    r = requests.post(tg, json={"chat_id": chat_id, "text": text}, timeout=20)
    try:
        j = r.json()
    except Exception:
        j = {"ok": False, "error": r.text}
    return jsonify(j), (200 if j.get("ok") else 400)

# ------------------- Socket events -------------------
@socketio.on("connect")
def on_connect():
    emit("server:hello", {"ok": True, "msg": "WS connected"})

@socketio.on("disconnect")
def on_disconnect():
    print("[ws] client disconnected")

# Ticker: client gửi 'ticker:subscribe' -> server bắt đầu bắn giá định kỳ
_ticker_thread = None
_ticker_thread_lock = threading.Lock()
_active_subscribers = 0

def _ticker_loop():
    while True:
        data = get_prices_cached()
        socketio.emit("ticker:update", {"data": data})
        socketio.sleep(TICKER_INTERVAL)

@socketio.on("ticker:subscribe")
def on_ticker_sub(_data=None):
    global _ticker_thread, _active_subscribers
    with _ticker_thread_lock:
        _active_subscribers += 1
        if _ticker_thread is None:
            _ticker_thread = socketio.start_background_task(_ticker_loop)
    emit("ticker:ack", {"ok": True})

@socketio.on("ticker:unsubscribe")
def on_ticker_unsub(_data=None):
    # để đơn giản free plan: không tắt thread, chỉ giảm đếm
    global _active_subscribers
    with _ticker_thread_lock:
        _active_subscribers = max(0, _active_subscribers - 1)
    emit("ticker:ack", {"ok": True})

# ------------------- AI over WebSocket -------------------
def call_openai(prompt: str) -> str:
    if not OPENAI_API_KEY:
        return "⚠️ OPENAI_API_KEY chưa cấu hình — trả lời mẫu.\n" + f"Bạn hỏi: {prompt}"
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Bạn là trợ lý của RaidenX8, trả lời ngắn gọn, rõ, hữu ích."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "stream": False
    }
    r = requests.post(url, headers=headers, data=json.dumps(body), timeout=60)
    r.raise_for_status()
    j = r.json()
    return j["choices"][0]["message"]["content"].strip()

def call_gemini(prompt: str) -> str:
    if not GEMINI_API_KEY:
        return "⚠️ GEMINI_API_KEY chưa cấu hình — trả lời mẫu.\n" + f"Bạn hỏi: {prompt}"
    # REST v1beta generateContent
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    r = requests.post(url, json=body, timeout=60)
    r.raise_for_status()
    j = r.json()
    try:
        return j["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return f"(Gemini) Unexpected response: {j}"

@socketio.on("ai:message")
def on_ai_message(payload):
    """
    payload:
      { id: "msg-uuid", text: "...", provider: "openai"|"gemini" }
    """
    mid   = (payload or {}).get("id") or f"m{int(time.time()*1000)}"
    text  = (payload or {}).get("text", "").strip()
    prov  = ((payload or {}).get("provider") or "openai").lower()

    if not text:
        emit("ai:done", {"id": mid, "content": "Bạn chưa nhập câu hỏi."})
        return

    try:
        if prov == "gemini":
            reply = call_gemini(text)
        else:
            reply = call_openai(text)
    except Exception as e:
        reply = f"Xin lỗi, API hiện lỗi: {e}"

    # chunk giả lập
    chunk_emit(reply, mid)
    emit("ai:done", {"id": mid, "content": ""})

# ------------------- main -------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    # Dev run: python server.py
    socketio.run(app, host="0.0.0.0", port=port)
