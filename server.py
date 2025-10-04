import os
import time
from collections import deque
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import requests

# ========== App ==========
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ========== Env ==========
BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")     # dùng nếu có OpenAI
GEMINI_KEY = os.getenv("GEMINI_API_KEY")     # dùng nếu có Gemini

EVENTS = deque(maxlen=200)

def push_event(kind, payload):
    evt = {"ts": int(time.time()), "kind": kind, "data": payload}
    EVENTS.append(evt)
    socketio.emit("message", evt, namespace="/ws")
    return evt

# ========== Routes ==========
@app.route("/")
def root():
    return "RaidenX8 API is up."

@app.route("/health")
def health():
    return "ok", 200

@app.route("/events")
def events():
    return jsonify({"events": list(EVENTS)})

@app.route("/send", methods=["POST"])
def send():
    if not BOT_TOKEN or not CHAT_ID:
        return {"ok": False, "error": "Missing TELEGRAM_BOT_TOKEN/CHAT_ID"}, 400
    text = (request.json or {}).get("text", "")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": CHAT_ID, "text": text})
    push_event("outgoing", {"text": text, "tg": resp.json()})
    return resp.json()

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.json or {}
    msg = update.get("message", {})
    text = msg.get("text", "")
    push_event("incoming", {"text": text, "raw": update})
    return {"ok": True}

# ========== AI Chat ==========
@app.route("/ask", methods=["POST"])
def ask_ai():
    payload = request.json or {}
    query = payload.get("text", "").strip()
    if not query:
        return {"ok": False, "error": "No text"}, 400

    # Ưu tiên Gemini nếu có
    if GEMINI_KEY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_KEY}"
        resp = requests.post(url, json={"contents":[{"parts":[{"text":query}]}]})
        data = resp.json()
        answer = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        push_event("ai_reply", {"q": query, "a": answer})
        return {"ok": True, "answer": answer, "raw": data}

    # Nếu không có Gemini thì fallback qua OpenAI
    if OPENAI_KEY:
        headers = {"Authorization": f"Bearer {OPENAI_KEY}"}
        resp = requests.post("https://api.openai.com/v1/chat/completions",
            headers=headers,
            json={
                "model": "gpt-4o-mini",
                "messages":[{"role":"user","content":query}]
            })
        data = resp.json()
        answer = data["choices"][0]["message"]["content"]
        push_event("ai_reply", {"q": query, "a": answer})
        return {"ok": True, "answer": answer, "raw": data}

    return {"ok": False, "error": "No AI key provided"}, 400

# ========== WS ==========
@socketio.on("connect", namespace="/ws")
def ws_connect():
    emit("ready", {"message": "connected", "ts": int(time.time())})

# ========== Run ==========
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
