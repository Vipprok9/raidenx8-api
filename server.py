# server.py — RaidenX8 v18 backend full WS + AI + prices + TTS
import os, io, time, hashlib, requests
from datetime import datetime, timezone
from threading import Thread
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from gtts import gTTS
import openai, google.generativeai as genai

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# --- Config ---
COINGECKO = "https://api.coingecko.com/api/v3"
COINS = [
    {"id": "bitcoin", "sym": "BTC"},
    {"id": "ethereum", "sym": "ETH"},
    {"id": "binancecoin", "sym": "BNB"},
    {"id": "solana", "sym": "SOL"},
    {"id": "ripple", "sym": "XRP"},
    {"id": "toncoin", "sym": "TON"},
]
FETCH_INTERVAL = int(os.getenv("FETCH_INTERVAL", "25"))
PRICE_CACHE_TTL = int(os.getenv("PRICE_CACHE_TTL", "15"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY","").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY","").strip()
if OPENAI_API_KEY: openai.api_key = OPENAI_API_KEY
if GEMINI_API_KEY: genai.configure(api_key=GEMINI_API_KEY)

# --- Caches ---
PRICE_CACHE = {"ts": 0, "data": {}}
TTS_DIR = os.getenv("CACHE_DIR", "/tmp/tts_cache"); os.makedirs(TTS_DIR, exist_ok=True)

def now_ts(): return int(time.time())
def merge_ids(): return ",".join({c["id"] for c in COINS} | {"the-open-network"})

def fetch_prices():
    if now_ts() - PRICE_CACHE["ts"] <= PRICE_CACHE_TTL and PRICE_CACHE["data"]:
        return PRICE_CACHE["data"]
    url = f"{COINGECKO}/simple/price?ids={merge_ids()}&vs_currencies=usd&include_24hr_change=true"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    raw = r.json()
    ton = raw.get("toncoin") or raw.get("the-open-network")
    if ton: raw["toncoin"] = ton
    out = {c["id"]: raw.get(c["id"], {}) for c in COINS}
    PRICE_CACHE["ts"] = now_ts(); PRICE_CACHE["data"] = out
    return out

@app.get("/prices")
def prices():
    return jsonify({"ok": True, "ts": datetime.now(timezone.utc).isoformat(), "data": fetch_prices()})

def ws_prices_loop():
    while True:
        try:
            socketio.emit("prices", {"ok": True, "ts": now_ts(), "data": fetch_prices()}, broadcast=True)
        except Exception as e:
            print("WS prices error:", e)
        time.sleep(FETCH_INTERVAL)
Thread(target=ws_prices_loop, daemon=True).start()

# --- TTS ---
def sha1(s): return hashlib.sha1(s.encode()).hexdigest()
@app.get("/tts")
def tts():
    text = (request.args.get("text") or "").strip()
    lang = (request.args.get("lang") or "vi").strip()
    if not text: return ("missing text", 400)
    fp = os.path.join(TTS_DIR, sha1(f"{lang}|{text}") + ".mp3")
    if os.path.exists(fp): return send_file(fp, mimetype="audio/mpeg")
    gTTS(text=text, lang=lang).save(fp)
    return send_file(fp, mimetype="audio/mpeg")

# --- AI Chat (HTTP) ---
@app.post("/ai/chat")
def ai_chat():
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    provider = (data.get("provider") or "auto").lower()
    if not text: return jsonify({"ok": False, "error": "no text"})
    try:
        if provider == "gemini" or (provider == "auto" and GEMINI_API_KEY):
            model = genai.GenerativeModel("gemini-1.5-pro-latest")
            r = model.generate_content(text)
            reply = r.text.strip()
        else:
            client = openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
            if not client: raise RuntimeError("OpenAI key missing")
            r = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user","content":text}])
            reply = r.choices[0].message.content.strip()
        return jsonify({"ok": True, "reply": reply})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

# --- AI Chat (WebSocket 2-way) ---
@socketio.on("chat")
def on_chat(data):
    text = (data or {}).get("text","").strip()
    if not text:
        emit("chat_reply", {"ok": False, "error": "no text"}); return
    try:
        if GEMINI_API_KEY:
            model = genai.GenerativeModel("gemini-1.5-pro-latest")
            r = model.generate_content(text)
            reply = r.text.strip()
        elif OPENAI_API_KEY:
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            r = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user","content":text}])
            reply = r.choices[0].message.content.strip()
        else:
            reply = f"Echo: {text}"
        emit("chat_reply", {"ok": True, "reply": reply})
    except Exception as e:
        emit("chat_reply", {"ok": False, "error": str(e)})

@app.get("/")
@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "coins": [c["sym"] for c in COINS],
        "ai": bool(OPENAI_API_KEY or GEMINI_API_KEY),
        "ts": datetime.now(timezone.utc).isoformat()
    })

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
