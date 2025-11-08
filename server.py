import os, time, json, requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# ====== ENV ======
PROVIDER        = os.getenv("PROVIDER", "gemini")          # "gemini" | "openai"
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "*")

# Gemini
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL    = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash-preview-05-20")

# OpenAI
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

SYSTEM_PROMPT = (
    "Bạn là RaidenX8 — trợ lý kiểu Gemini Studio: trả lời ngắn gọn, mạch lạc, có lý do; "
    "ưu tiên tiếng Việt tự nhiên; khi có thể hãy đưa gợi ý tiếp theo. "
    "Nếu câu hỏi cần dữ liệu thời gian thực (giờ hiện tại, giá crypto…) và hệ thống đã có công cụ, "
    "hãy dùng công cụ trước, chỉ gọi AI khi cần suy luận bổ sung. "
    "Khi thiếu dữ liệu thời gian thực (thời tiết, giao thông…), hãy nói thẳng là không có nguồn trực tiếp "
    "và đề xuất cách kiểm tra nhanh."
)

# ====== APP ======
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": FRONTEND_ORIGIN}})
socketio = SocketIO(app, cors_allowed_origins=FRONTEND_ORIGIN, async_mode="eventlet")

# ====== SIMPLE LIVE TOOLS ======
COINGECKO_API = "https://api.coingecko.com/api/v3/simple/price"

SYMBOL_MAP = {
    "btc": "bitcoin",
    "eth": "ethereum",
    "bnb": "binancecoin",
    "sol": "solana",
    "ton": "the-open-network",
    "usdt": "tether",
}

def detect_intent(msg: str):
    m = (msg or "").lower()
    if any(k in m for k in ["mấy giờ", "bây giờ mấy giờ", "giờ hiện tại", "time now"]):
        return ("time", None)
    if any(k in m for k in ["giá", "price", "bao nhiêu"]) and any(s in m for s in SYMBOL_MAP.keys()):
        syms = [s for s in SYMBOL_MAP.keys() if s in m]
        return ("price", syms or ["btc","eth","bnb","sol","ton","usdt"])
    return ("ai", None)

def live_time_reply():
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    return f"Bây giờ (UTC) là {ts}. Nếu bạn ở Việt Nam, cộng thêm +7 giờ."

def live_price_reply(symbols):
    ids = ",".join(SYMBOL_MAP[s] for s in symbols if s in SYMBOL_MAP)
    if not ids:
        ids = ",".join(SYMBOL_MAP.values())
    vs = "usd"
    try:
        r = requests.get(COINGECKO_API, params={"ids": ids, "vs_currencies": vs}, timeout=20)
        j = r.json()
        parts = []
        for s in symbols:
            cid = SYMBOL_MAP.get(s)
            if cid and cid in j:
                v = j[cid].get(vs)
                parts.append(f"{s.upper()}: {v} USD")
        if not parts:
            return "Không lấy được giá lúc này. Thử lại sau nhé."
        return "Giá hiện tại: " + " • ".join(parts)
    except Exception:
        return "Không truy xuất được giá ngay lúc này."

# ====== AI HELPERS ======
def call_gemini(text: str):
    if not GEMINI_API_KEY:
        return type("Resp", (), {"status_code": 400, "json": lambda: {"error":"Missing GEMINI_API_KEY"}})()
    url = f"https://generativelanguage.googleapis.com/v1beta/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": f"{SYSTEM_PROMPT}\n\nUser: {text}"}]}
        ]
    }
    try:
        resp = requests.post(url, json=payload, timeout=60)
    except Exception as e:
        return type("Resp", (), {"status_code": 500, "json": lambda: {"error": str(e)}})()
    return resp

def parse_gemini_text(j: dict) -> str:
    try:
        parts = j["candidates"][0]["content"]["parts"]
        return "".join(p.get("text","") for p in parts).strip()
    except Exception:
        return json.dumps(j)[:800]

def call_openai(text: str):
    if not OPENAI_API_KEY:
        return type("Resp", (), {"status_code": 400, "json": lambda: {"error":"Missing OPENAI_API_KEY"}})()
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": OPENAI_MODEL,
        "temperature": 0.7,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text}
        ]
    }
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
    except Exception as e:
        return type("Resp", (), {"status_code": 500, "json": lambda: {"error": str(e)}})()
    return resp

def ai_answer(text: str) -> str:
    if PROVIDER == "openai":
        r = call_openai(text)
        j = r.json()
        if r.status_code >= 400:
            return f"[OpenAI error {r.status_code}] {j}"
        try:
            return j["choices"][0]["message"]["content"].strip()
        except Exception:
            return json.dumps(j)[:800]
    else:
        r = call_gemini(text)
        j = r.json()
        if r.status_code >= 400:
            return f"[Gemini error {r.status_code}] {j}"
        return parse_gemini_text(j)

# ====== HTTP ROUTES ======
@app.get("/")
def root():
    return {"ok": True, "service": "raidenx8-api"}

@app.get("/health")
def health():
    return {
        "ok": True,
        "provider": PROVIDER,
        "model": GEMINI_MODEL if PROVIDER == "gemini" else OPENAI_MODEL
    }

@app.post("/ai/chat")
def http_chat():
    data = request.get_json(force=True, silent=True) or {}
    msg = (data.get("msg") or "").strip()
    if not msg:
        return {"error": "Empty message"}, 400

    intent, payload = detect_intent(msg)
    if intent == "time":
        reply = live_time_reply()
    elif intent == "price":
        reply = live_price_reply(payload or [])
    else:
        reply = ai_answer(msg)

    return {"reply": reply}

# (Alias tương thích frontend cũ nếu lỡ gọi /ai/chat_sync)
@app.route("/ai/chat_sync", methods=["OPTIONS"])
def chat_sync_options():
    return ("", 204)

@app.post("/ai/chat_sync")
def chat_sync():
    return http_chat()

# ====== SOCKET.IO (2 chiều) ======
@socketio.on("connect")
def ws_connect():
    emit("system", {"text": "✅ Connected RaidenX8 WS"})

@socketio.on("disconnect")
def ws_disconnect():
    pass

@socketio.on("chat")
def ws_chat(data):
    text = (data or {}).get("text", "").strip()
    if not text:
        emit("reply", {"text": "❗️Tin nhắn trống."})
        return

    emit("typing", {"on": True})

    intent, payload = detect_intent(text)
    if intent == "time":
        reply = live_time_reply()
    elif intent == "price":
        reply = live_price_reply(payload or [])
    else:
        reply = ai_answer(text)

    emit("typing", {"on": False})

    chunk_size = 48
    for i in range(0, len(reply), chunk_size):
        emit("reply_chunk", {"text": reply[i:i+chunk_size]})
        socketio.sleep(0.02)
    emit("reply", {"done": True})

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
