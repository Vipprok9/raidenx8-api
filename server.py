import os, time, threading
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import requests

# ====== Config ======
API_NAME = "raidenx8-api"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://raidenx8.pages.dev").split(",")

# CoinGecko
CG_IDS = os.getenv(
    "COINGECKO_IDS",
    "bitcoin,ethereum,tether,binancecoin,solana"
)  # có thể thêm: "ripple,cardano,toncoin,polygon,tron"
CG_INTERVAL = int(os.getenv("CG_INTERVAL_SECONDS", "30"))
VS = os.getenv("CG_VS", "usd")

# Map id -> symbol hiển thị
SYMBOL_MAP = {
    "bitcoin":"BTC","ethereum":"ETH","tether":"USDT","binancecoin":"BNB","solana":"SOL",
    "ripple":"XRP","cardano":"ADA","toncoin":"TON","polygon":"MATIC","tron":"TRX"
}

# Flask + CORS + SocketIO
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": [o.strip() for o in ALLOWED_ORIGINS]}})
socketio = SocketIO(app, cors_allowed_origins=ALLOWED_ORIGINS, async_mode="threading")

# Cache giá mới nhất
latest_prices = {"prices": [], "updated_at": None, "source": "coingecko"}

# ====== Health ======
@app.get("/")
def root():
    return jsonify(ok=True, service=API_NAME)

@app.get("/health")
def health():
    return jsonify(status="ok", updated_at=latest_prices["updated_at"])

# ====== Public APIs ======
@app.get("/prices")
def get_prices():
    return jsonify(latest_prices)

@app.post("/prices/push")
def push_prices():
    data = request.get_json(silent=True) or {}
    prices = data.get("prices", [])
    latest_prices["prices"] = prices
    latest_prices["updated_at"] = datetime.now(timezone.utc).isoformat()
    latest_prices["source"] = "push"
    socketio.emit("prices", latest_prices, namespace="/")
    return jsonify(ok=True, count=len(prices))

# ====== AI Chat (OpenAI/Gemini) ======
@app.post("/ai")
def ai_chat():
    data = request.get_json(silent=True) or {}
    message  = (data.get("message") or "").strip()
    provider = (data.get("provider") or "openai").lower()
    if not message:
        return jsonify(error="message required"), 400

    try:
        if provider == "openai":
            if not OPENAI_API_KEY:
                return jsonify(error="OPENAI_API_KEY not set"), 400
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role":"system","content":"You are RaidenX8 AI."},
                          {"role":"user","content":message}],
                temperature=0.7,
            )
            return jsonify(reply=resp.choices[0].message.content.strip(), provider="openai")

        if provider == "gemini":
            if not GEMINI_API_KEY:
                return jsonify(error="GEMINI_API_KEY not set"), 400
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-1.5-flash")
            out = model.generate_content(message)
            return jsonify(reply=(out.text or "").strip(), provider="gemini")

        return jsonify(error="Unknown provider"), 400
    except Exception as e:
        return jsonify(error=f"AI error: {e}"), 500

# ====== Telegram Notify ======
@app.post("/notify")
def notify():
    if not TELEGRAM_BOT_TOKEN:
        return jsonify(error="TELEGRAM_BOT_TOKEN not set"), 400
    data = request.get_json(silent=True) or {}
    chat_id = str(data.get("chat_id") or "").strip()
    text    = (data.get("text") or "").strip()
    if not chat_id or not text:
        return jsonify(error="chat_id and text required"), 400

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=15)
        if r.ok and r.json().get("ok"):
            return jsonify(ok=True)
        return jsonify(error="telegram api error", detail=r.text), 502
    except Exception as e:
        return jsonify(error=str(e)), 500

# ====== Socket events ======
@socketio.on("connect")
def on_connect():
    emit("server_info", {"ok": True, "service": API_NAME})
    # gửi cache ngay khi client vừa connect
    if latest_prices["prices"]:
        emit("prices", latest_prices)

# ====== CoinGecko background job ======
def fetch_coingecko_loop():
    """
    Gọi CoinGecko mỗi CG_INTERVAL giây, ưu tiên BTC/ETH trước để 'global trend' đúng cảm giác.
    """
    url = ("https://api.coingecko.com/api/v3/simple/price"
           f"?ids={CG_IDS}&vs_currencies={VS}&include_24hr_change=true")

    headers = {
        "Accept": "application/json",
        "User-Agent": "RaidenX8/1.0 (Render) - contact: dev@raidenx8"
    }

    while True:
        try:
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code == 200:
                data = r.json()  # {id: {usd: x, usd_24h_change: y}}
                prices = []
                for cid, obj in data.items():
                    price = obj.get(VS)
                    change = obj.get(f"{VS}_24h_change")
                    symbol = SYMBOL_MAP.get(cid, cid.upper())
                    if price is None:
                        continue
                    prices.append({
                        "symbol": symbol,
                        "price": float(price),
                        "change24h": float(change) if change is not None else None
                    })

                # Sắp xếp ưu tiên BTC, ETH trước
                order = {"BTC":0, "ETH":1}
                prices.sort(key=lambda x: order.get(x["symbol"], 100))

                latest_prices["prices"] = prices
                latest_prices["updated_at"] = datetime.now(timezone.utc).isoformat()
                latest_prices["source"] = "coingecko"

                socketio.emit("prices", latest_prices, namespace="/")
            else:
                # rate limit hoặc lỗi: không phát rỗng để tránh giật
                pass

        except Exception:
            # nuốt lỗi mạng, sẽ thử lại lượt sau
            pass

        time.sleep(CG_INTERVAL)

# ====== Main ======
if __name__ == "__main__":
    # chạy job CoinGecko thật
    threading.Thread(target=fetch_coingecko_loop, daemon=True).start()
    port = int(os.getenv("PORT", "8000"))
    socketio.run(app, host="0.0.0.0", port=port, debug=False)
