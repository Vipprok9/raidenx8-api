import os, time, json, requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ========= Config =========
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DEFAULT_TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# CoinGecko cache để giảm rate-limit
_cache_prices = {"ts": 0, "data": None}
CACHE_SECONDS = 20

# ========= Helpers =========
def err(msg, code=400):
    return jsonify({"ok": False, "error": msg}), code

# ========= Health =========
@app.get("/health")
def health():
    return jsonify({"ok": True, "ts": int(time.time())})

# ========= Prices (CoinGecko) =========
# GET /api/prices?ids=bitcoin,ethereum,bnb,toncoin&vs=usd
@app.get("/api/prices")
def prices():
    ids = request.args.get("ids", "bitcoin,ethereum,bnb,toncoin")
    vs = request.args.get("vs", "usd")

    # cache đơn giản
    now = time.time()
    if _cache_prices["data"] and (now - _cache_prices["ts"] < CACHE_SECONDS):
        return jsonify({"ok": True, "cached": True, "data": _cache_prices["data"]})

    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        r = requests.get(url, params={"ids": ids, "vs_currencies": vs, "include_24hr_change": "true"}, timeout=8)
        r.raise_for_status()
        data = r.json()
        _cache_prices["ts"] = now
        _cache_prices["data"] = data
        return jsonify({"ok": True, "cached": False, "data": data})
    except Exception as e:
        # Fallback demo nếu lỗi (rate-limit,…)
        demo = {
            "bitcoin":   {"usd": 120334, "usd_24h_change": 1.17},
            "ethereum":  {"usd": 4477.91, "usd_24h_change": 2.02},
            "bnb":       {"usd": 1109.20, "usd_24h_change": 5.16},
            "toncoin":   {"usd": None,   "usd_24h_change": None},
            "tether":    {"usd": 1,      "usd_24h_change": 0.0},
        }
        return jsonify({"ok": True, "cached": True, "source": "fallback-demo", "data": demo})

# ========= Telegram Notify =========
# POST /api/notify {message, chat_id?}
@app.post("/api/notify")
def notify():
    if not TELEGRAM_BOT_TOKEN:
        return err("Missing TELEGRAM_BOT_TOKEN (backend).")

    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    chat_id = str(body.get("chat_id") or DEFAULT_TELEGRAM_CHAT_ID).strip()

    if not message:
        return err("Message is required.")
    if not chat_id:
        return err("chat_id required (or set TELEGRAM_CHAT_ID in env).")

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        r = requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
        r.raise_for_status()
        return jsonify({"ok": True, "result": r.json()})
    except Exception as e:
        return err(f"Telegram error: {e}", 502)

# ========= AI Chat Proxy =========
# POST /api/chat {provider: "openai"|"gemini", prompt, system?}
@app.post("/api/chat")
def chat():
    body = request.get_json(silent=True) or {}
    provider = (body.get("provider") or "openai").lower()
    prompt = (body.get("prompt") or "").strip()
    system = body.get("system") or "You are a helpful assistant for Web3/Airdrop/DeFi."

    if not prompt:
        return err("prompt is required.")

    try:
        if provider == "gemini":
            if not GEMINI_API_KEY:
                return err("Missing GEMINI_API_KEY.")
            # Gemini 1.5 Pro (REST)
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={GEMINI_API_KEY}"
            payload = {
                "contents": [{"parts": [{"text": f"{system}\n\nUser: {prompt}"}]}]
            }
            r = requests.post(url, json=payload, timeout=20)
            r.raise_for_status()
            data = r.json()
            text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            return jsonify({"ok": True, "provider": "gemini", "text": text})

        # Default OpenAI (Responses API)
        if not OPENAI_API_KEY:
            return err("Missing OPENAI_API_KEY.")
        url = "https://api.openai.com/v1/responses"
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "gpt-4o-mini",
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ]
        }
        r = requests.post(url, headers=headers, json=payload, timeout=20)
        r.raise_for_status()
        data = r.json()
        # Lấy text gọn
        text = ""
        if isinstance(data.get("output_text"), str):
            text = data["output_text"]
        else:
            text = json.dumps(data)[:1200]
        return jsonify({"ok": True, "provider": "openai", "text": text})

    except Exception as e:
        return err(f"AI error: {e}", 502)

# ========= Root =========
@app.get("/")
def index():
    return jsonify({"ok": True, "service": "RaidenX8 API", "routes": [
        "GET  /health",
        "GET  /api/prices?ids=bitcoin,ethereum,bnb,toncoin&vs=usd",
        "POST /api/notify {message, chat_id?}",
        "POST /api/chat {provider, prompt, system?}"
    ]})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
