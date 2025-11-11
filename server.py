# server.py — RaidenX8 API (v36.3)
import os, json, time, datetime as dt
from flask import Flask, request, jsonify
from flask_cors import CORS

USE_GEMINI = bool(os.getenv("GEMINI_API_KEY"))
USE_OPENAI = bool(os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)
CORS(app)

# ---- Socket.IO (eventlet) ----
try:
    from flask_socketio import SocketIO, emit
    socketio = SocketIO(app, cors_allowed_origins="*")
except Exception:
    socketio = None
    emit = None

# ---------- Helpers ----------
def now_ts() -> int:
    return int(time.time())

def nice_time_vn():
    tz_offset = int(os.getenv("TZ_OFFSET", "7"))
    return (dt.datetime.utcnow() + dt.timedelta(hours=tz_offset)).strftime("%H:%M %d/%m/%Y")

def rule_based_reply(text: str) -> str:
    t = text.lower().strip()
    if "giá btc" in t or "bitcoin" in t:
        return "Bản demo chưa mở API giá trực tiếp. Bạn dùng nút Ticker ở trên để xem nhanh nhé."
    if "thời tiết" in t or "huế" in t:
        return "Mình chưa bật API thời tiết. Khi có key mình sẽ trả lời theo địa phương."
    if t in {"hi","hello","xin chào","chào"}:
        return "Chào bạn! Mình là RX8 bot. Bạn có thể hỏi giá BTC, Solana, hoặc bất kỳ điều gì."
    return (
        "Mình đã nhận câu hỏi và đang chạy bản demo. "
        "Nếu bạn bật khóa **Gemini** hoặc **OpenAI** ở backend Render, mình sẽ trả lời thông minh hơn."
    )

# ---------- AI backends ----------
def ai_with_gemini(prompt: str, model: str|None) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    # Map tên 'gemini-studio-2.5-preview-05-20' → model hợp lệ bên Gemini (đổi nếu bạn dùng tên khác trong Studio)
    mdl = model or os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
    if mdl.startswith("gemini-studio-2.5") or "05-20" in (model or ""):
        # nếu bạn publish từ Gemini Studio thành "models/xxx", đặt ENV GEMINI_MODEL=models/xxx và bỏ map này
        mdl = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
    resp = genai.GenerativeModel(mdl).generate_content(prompt)
    return (getattr(resp, "text", "") or "").strip() or rule_based_reply(prompt)

def ai_with_openai(prompt: str, model: str|None) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    mdl = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    chat = client.chat.completions.create(
        model=mdl,
        messages=[
            {"role":"system","content":"Bạn là RX8 bot, trả lời ngắn gọn, tự nhiên, tiếng Việt."},
            {"role":"user","content":prompt},
        ],
        temperature=0.6,
    )
    return chat.choices[0].message.content.strip()

def smart_answer(prompt: str, model: str|None) -> str:
    try:
        # Ưu tiên Gemini nếu có key
        if USE_GEMINI:
            return ai_with_gemini(prompt, model)
        if USE_OPENAI:
            return ai_with_openai(prompt, model)
        return rule_based_reply(prompt)
    except Exception as e:
        return f"⚠️ Lỗi AI: {e}\n" + rule_based_reply(prompt)

# ---------- REST ----------
@app.get("/health")
def health():
    return "ok", 200

@app.get("/")
def root():
    return jsonify({"ok": True, "ts": now_ts(), "service": "rx8-api"})

@app.get("/prices")
def prices():
    # symbols=BTC,ETH,SOL...
    import requests
    symbols = request.args.get("symbols","BTC,ETH,SOL,TON,BNB,USDT").upper().split(",")
    # Map đơn giản -> CoinGecko ids
    id_map = {
        "BTC":"bitcoin", "ETH":"ethereum", "SOL":"solana",
        "TON":"the-open-network", "BNB":"binancecoin", "USDT":"tether"
    }
    ids = ",".join([id_map.get(s, s) for s in symbols])
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ids, "vs_currencies": "usd", "include_24hr_change":"true"},
            timeout=10,
        )
        raw = r.json()
        data=[]
        for s in symbols:
            coin = id_map.get(s, s)
            if coin in raw:
                data.append({
                    "symbol": s,
                    "price": raw[coin]["usd"],
                    "change24h": raw[coin].get("usd_24h_change", 0.0),
                })
        return jsonify({"data": data, "ts": now_ts()})
    except Exception as e:
        return jsonify({"error": str(e), "data": [], "ts": now_ts()}), 500

# ---------- Socket.IO ----------
if socketio:
    @socketio.on("connect")
    def on_connect():
        emit("ai:reply", {"text": "WS connected • " + nice_time_vn()})

    @socketio.on("ai:chat")
    def on_ai_chat(payload):
        text = (payload or {}).get("text", "")
        model = (payload or {}).get("model")
        reply = smart_answer(text, model)
        emit("ai:reply", {"text": reply})

# ---------- WSGI ----------
if __name__ == "__main__":
    if socketio:
        socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
    else:
        app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
