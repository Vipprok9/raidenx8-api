# server.py — RaidenX8 API (v36.2) — Flask + Socket.IO + SSE
import os, json, time, datetime as dt
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

# Optional AI providers
USE_GEMINI = bool(os.getenv("GEMINI_API_KEY"))
USE_OPENAI = bool(os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)
CORS(app)

# --- Socket.IO (eventlet friendly) ---
try:
    from flask_socketio import SocketIO, emit
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")
except Exception:
    # SocketIO optional; app vẫn chạy được nếu Render chưa cài eventlet
    socketio = None
    emit = None

# ----------------- Helpers -----------------
def now_ts() -> int:
    return int(time.time())

def nice_time_vn():
    tz_offset = int(os.getenv("TZ_OFFSET", "7"))  # VN default +7
    return (dt.datetime.utcnow() + dt.timedelta(hours=tz_offset)).strftime("%H:%M, %d/%m/%Y")

def rule_based_reply(text: str) -> str:
    """Fallback trả lời mượt khi không có API key."""
    t = text.lower().strip()
    if not t:
        return "Bạn hãy nhập nội dung cần hỏi nhé."
    if "mấy giờ" in t or "thời gian" in t:
        return f"Bây giờ là {nice_time_vn()} (giờ VN)."
    if "thời tiết" in t:
        return "Mình không có API thời tiết ở đây. Bạn có thể hỏi thành phố cụ thể, mình gợi ý cách tra nhanh."
    if "giá btc" in t or "bitcoin" in t:
        return "Bản API free này chưa bật dữ liệu giá. Khi có CoinGecko/Exchange API mình sẽ báo giá realtime kèm % thay đổi."
    if "hello" in t or "xin chào" in t:
        return "Chào bạn! Mình là RX8 Bot. Bạn có thể hỏi về AI/Web3, banner Trinity, hoặc cấu hình deploy Render/CF Pages."
    # default tone “Gemini-like”: rõ ràng, súc tích, nêu bước làm
    return (
        "Mình hiểu câu hỏi của bạn. Với bản demo này mình trả lời ngắn gọn, dễ làm theo. "
        "Nếu bạn bật khóa **Gemini** hay **OpenAI** trong môi trường, mình sẽ trả lời chi tiết hơn."
    )

# --------------- AI backends ----------------
def ai_with_gemini(prompt: str, model: str | None):
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    mdl = model or os.getenv("GEMINI_MODEL", "gemini-1.5-flash-8b")
    resp = genai.GenerativeModel(mdl).generate_content(prompt)
    return resp.text.strip() if hasattr(resp, "text") and resp.text else "Mình chưa nhận được nội dung từ Gemini."

def ai_with_openai(prompt: str, model: str | None):
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    mdl = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    chat = client.chat.completions.create(
        model=mdl,
        messages=[{"role":"system","content":"Bạn là trợ lý ngắn gọn, mạch lạc."},
                  {"role":"user","content":prompt}],
        temperature=0.6,
    )
    return chat.choices[0].message.content.strip()

def smart_answer(prompt: str, model: str | None):
    # ưu tiên Gemini → OpenAI → rule-based
    try:
        if USE_GEMINI:
            return ai_with_gemini(prompt, model)
        if USE_OPENAI:
            return ai_with_openai(prompt, model)
        return rule_based_reply(prompt)
    except Exception as e:
        # nếu provider lỗi thì rơi về rule-based
        return f"(AI lỗi tạm thời: {e})\n" + rule_based_reply(prompt)

# ----------------- Routes -------------------
@app.get("/health")
def health():
    return jsonify(ok=True, ts=now_ts())

@app.get("/")
def root():
    return jsonify(ok=True, name="RaidenX8 API", ts=now_ts())

# SSE: đẩy keep-alive + gói hello mượt
@app.get("/stream")
def stream():
    def event_stream():
        # chào 1 gói lúc mở kết nối
        hello = {"type": "hello", "ts": now_ts()}
        yield f"data: {json.dumps(hello)}\n\n"
        # ping đều mỗi 10s để giữ kết nối
        while True:
            ping = {"type": "ping", "ts": now_ts()}
            yield f"data: {json.dumps(ping)}\n\n"
            time.sleep(10)
    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return Response(event_stream(), headers=headers)

# REST chat
@app.post("/chat")
def chat_rest():
    data = request.get_json(force=True, silent=True) or {}
    prompt = (data.get("message") or data.get("prompt") or "").strip()
    model = data.get("model")
    answer = smart_answer(prompt, model)
    return jsonify(ok=True, model=(model or ("gemini" if USE_GEMINI else "openai" if USE_OPENAI else "rule")),
                   answer=answer)

# (Optional) minimal TTS stub – để frontend biết API sống
@app.post("/api/tts")
def tts_stub():
    # Triển khai thật khi có GOOGLE/AZURE/OPENAI TTS; tạm trả text để frontend Web Speech đọc
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify(ok=False, error="Thiếu text"), 400
    return jsonify(ok=True, voice="vi-VN-demo", url=None, text=text)

# ---------------- WebSocket chat ----------------
if socketio:
    @socketio.on("connect", namespace="/ws")
    def ws_connect():
        emit("info", {"ok": True, "msg": "WS connected", "ts": now_ts()})

    @socketio.on("chat", namespace="/ws")
    def ws_chat(data):
        text = (data or {}).get("message", "")
        model = (data or {}).get("model")
        answer = smart_answer(text, model)
        emit("answer", {"ok": True, "answer": answer, "ts": now_ts()})

# ------------- Gunicorn entry -------------------
# Dùng: gunicorn --worker-class eventlet -w 1 -b 0.0.0.0:$PORT server:app
# Nếu muốn WS: thay bằng server:socketio (nhưng Socket.IO vẫn wrap app)
