# server.py — RaidenX8_Final_Plus (Backend Render)
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO
import os, requests, threading, time, random

# ==== CẤU HÌNH CƠ BẢN ====
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
COINGECKO_IDS = os.getenv("COINGECKO_IDS", "bitcoin,ethereum,tether,binancecoin,solana,toncoin").split(",")
CG_INTERVAL = int(os.getenv("CG_INTERVAL_SECONDS", "30"))

prices_cache = []

# ==== FETCH GIÁ COINGECKO ====
def fetch_prices_loop():
    global prices_cache
    while True:
        try:
            ids = ",".join(COINGECKO_IDS)
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true"
            res = requests.get(url, timeout=10)
            data = res.json()
            prices_cache = []
            for k, v in data.items():
                prices_cache.append({
                    "symbol": k.upper(),
                    "price": v["usd"],
                    "change24h": v.get("usd_24h_change", 0)
                })
            socketio.emit("prices", {"prices": prices_cache, "source": "coingecko"})
        except Exception as e:
            print("Fetch error:", e)
        time.sleep(CG_INTERVAL)

threading.Thread(target=fetch_prices_loop, daemon=True).start()

# ==== ROUTES ====
@app.route("/health")
def health():
    return jsonify({"status": "ok", "prices": len(prices_cache)})

@app.route("/prices")
def get_prices():
    return jsonify({"prices": prices_cache, "source": "coingecko"})

@app.route("/notify", methods=["POST"])
def notify():
    data = request.get_json(force=True)
    msg = data.get("text", "")
    chat_id = data.get("chat_id", "")
    if not TELEGRAM_BOT_TOKEN or not chat_id or not msg:
        return jsonify({"error": "missing fields"}), 400
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    res = requests.post(url, json={"chat_id": chat_id, "text": msg})
    return jsonify(res.json())

@app.route("/ai", methods=["POST"])
def ai_reply():
    data = request.get_json(force=True)
    prompt = data.get("message", "")
    provider = data.get("provider", "openai").lower()
    if not prompt:
        return jsonify({"error": "no message"}), 400

    try:
        if provider == "gemini" and GEMINI_API_KEY:
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}",
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=15
            ).json()
            text = resp["candidates"][0]["content"]["parts"][0]["text"]
            return jsonify({"reply": text, "provider": "gemini"})

        elif provider == "openai" and OPENAI_API_KEY:
            headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                },
                timeout=15
            ).json()
            text = resp["choices"][0]["message"]["content"]
            return jsonify({"reply": text, "provider": "openai"})
        else:
            # Fallback mini-AI rule
            basic = ["Xin chào!", "Mình là AI của RaidenX8 ⚡", "Trend hôm nay là Web3 & AI!", "Giá đang biến động mạnh nha!"]
            return jsonify({"reply": random.choice(basic), "provider": "local"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==== SOCKET.IO ====
@socketio.on("connect")
def handle_connect():
    socketio.emit("prices", {"prices": prices_cache, "source": "init"})

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
