from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import os, re

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

@app.get("/health")
def health():
    return {"ok": True, "ver": "v33.1"}

def clean_text(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"(\s*[,.!?]){2,}", ". ", s)
    return s

def gemini_reply(prompt: str) -> str:
    if os.getenv("GEMINI_API_KEY"):
        return f"(Gemini 2.5) {prompt}"
    else:
        return f"Bạn nói: “{prompt}” (demo)"

@socketio.on("connect")
def ws_connect():
    emit("message", {"type": "status", "text": "connected"})

@socketio.on("message")
def ws_message(data):
    import json
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except:
            data = {"type": "chat", "text": data}
    if data.get("type") == "chat":
        user = clean_text(data.get("text", ""))
        bot = clean_text(gemini_reply(user))
        emit("message", {"type": "reply", "text": bot})

@app.post("/api/chat")
def http_chat():
    text = clean_text(request.json.get("text", ""))
    return jsonify({"reply": clean_text(gemini_reply(text))})

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
