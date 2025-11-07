# server.py
import os
import time
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-preview-05-20").strip()

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

def _bad_config():
    return not bool(GEMINI_API_KEY)

def gemini_generate_content(message: str, system: str = "", history=None):
    """
    Gọi Gemini :generateContent
    message: user text
    system : system prompt (tuỳ chọn)
    history: danh sách [{'role':'user'|'model', 'text':'...'}]
    """
    contents = []

    # convert history -> contents
    if history and isinstance(history, list):
        for turn in history:
            role = turn.get("role", "user")
            text = turn.get("text", "")
            if not text:
                continue
            # Gemini chỉ có 'user' & 'model' (assistant)
            parts = [{"text": text}]
            if role == "model" or role == "assistant":
                contents.append({"role": "model", "parts": parts})
            else:
                contents.append({"role": "user", "parts": parts})

    # add current user message
    contents.append({"role": "user", "parts": [{"text": message}]})

    # system instruction (dùng safety style)
    safety = {}
    if system:
        safety = {"systemInstruction": {"parts": [{"text": system}]}}
    payload = {**safety, "contents": contents}

    url = f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    r = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=60)

    # Trả lỗi thẳng nếu không 200 để dễ debug frontend
    if r.status_code != 200:
        return None, {"status": r.status_code, "body": r.text}

    data = r.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        # khi không có candidate hợp lệ
        text = ""
    return text, None

@app.route("/ai/chat", methods=["POST"])
def ai_chat():
    if _bad_config():
        return jsonify({"error": "Missing GEMINI_API_KEY"}), 500

    data = request.get_json(force=True, silent=True) or {}
    message = (data.get("message") or "").strip()
    system = (data.get("system") or "").strip()
    history = data.get("history") or []

    if not message:
        return jsonify({"error": "message is required"}), 400

    reply, err = gemini_generate_content(message, system, history)
    if err:
        # giữ nguyên mã lỗi phía Google để frontend hiển thị đúng
        return jsonify({"error": f"Gemini error", "detail": err["body"]}), err["status"]

    if not reply:
        reply = "…"  # fallback
    return jsonify({"reply": reply, "model": GEMINI_MODEL})

@app.route("/ai/list-models")
def list_models():
    if _bad_config():
        return jsonify({"error": "Missing GEMINI_API_KEY"}), 500
    url = f"{GEMINI_BASE}/models?key={GEMINI_API_KEY}"
    r = requests.get(url, timeout=30)
    return (r.text, r.status_code, {"Content-Type": "application/json"})

@app.route("/health")
def health():
    ok = bool(GEMINI_API_KEY)
    return jsonify({"ok": ok, "model": GEMINI_MODEL})

# -- Tuỳ chọn: endpoint giữ ấm (Render free sẽ sleep sau 15m)
@app.route("/wake")
def wake():
    return jsonify({"pong": int(time.time())})

if __name__ == "__main__":
    # Chạy local: python server.py
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=True)
