import os, time, json
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import requests

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")  # dùng gevent websocket ở Procfile

APP_NAME = "RaidenX8 API"
SYSTEM_HINT = (
    "Bạn là trợ lý RaidenX8, trả lời ngắn gọn, thân thiện (tiếng Việt), "
    "tránh lặp lại câu hỏi. Nếu người dùng hỏi thời tiết/giá coin hãy giải thích "
    "bạn không có quyền truy cập dữ liệu thời gian thực trừ khi backend đã được nối."
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# ===== Helpers =====
def call_gemini(prompt: str) -> str:
    """
    Gọi REST Gemini 1.5-flash (v1beta) qua Google AI Studio API.
    Trả về text hoặc raise Exception.
    """
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [
            {"parts": [{"text": f"{SYSTEM_HINT}\n\nNgười dùng: {prompt}"}]}
        ]
    }
    params = {"key": GEMINI_API_KEY}
    r = requests.post(url, headers=headers, params=params, data=json.dumps(payload), timeout=30)
    if r.status_code != 200:
        raise Exception(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    # bóc text
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        raise Exception(f"Gemini response unexpected: {json.dumps(data)[:300]}")

def call_openai(prompt: str) -> str:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_HINT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.6
    }
    r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
    if r.status_code != 200:
        raise Exception(f"OpenAI HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        raise Exception(f"OpenAI response unexpected: {json.dumps(data)[:300]}")

# ===== Endpoints =====
@app.get("/health")
def health():
    return jsonify(status="ok", app=APP_NAME, ts=int(time.time()))

@app.post("/ai/chat")
def ai_chat():
    data = request.get_json(silent=True) or {}
    user_msg = (data.get("message") or "").strip()
    if not user_msg:
        return jsonify(error="empty_message"), 400

    # 1) Gemini -> 2) OpenAI -> 3) Echo
    try:
        if GEMINI_API_KEY:
            reply = call_gemini(user_msg)
        elif OPENAI_API_KEY:
            reply = call_openai(user_msg)
        else:
            reply = f"[echo] {user_msg}"
    except Exception as e:
        reply = f"(Gemini/OpenAI lỗi: {str(e)[:160]})\n[echo] {user_msg}"

    # bắn realtime cho web (nếu có kết nối socket)
    socketio.emit("server_message", {"msg": reply})
    return jsonify(reply=reply)

# ===== Socket.IO (optional realtime) =====
@socketio.on("connect")
def on_connect():
    emit("server_message", {"msg": "🔌 Socket.IO connected."})

@socketio.on("client_message")
def on_client_message(data):
    emit("server_message", {"msg": data.get("msg", "")}, broadcast=True)

# ===== Main (local test) =====
if __name__ == "__main__":
    # Chạy local: python server.py
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
