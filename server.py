import os
import time
import logging
from typing import Dict, Any
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

# ----------------------------
# Config
# ----------------------------
SERVICE_NAME = "raidenx8-api"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")  # optional

# CORS: chỉ cho phép Pages.dev của bạn + localhost để dev
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "https://raidenx8.pages.dev,http://localhost:8788,http://localhost:5173"
).split(",")

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGINS}}, supports_credentials=True)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("raidenx8")

# ----------------------------
# Helpers
# ----------------------------
def ok(data: Dict[str, Any] = None, status: int = 200):
    payload = {"ok": True, "service": SERVICE_NAME, "time": int(time.time())}
    if data:
        payload.update(data)
    return jsonify(payload), status

def fail(message: str, status: int = 400, extra: Dict[str, Any] = None):
    payload = {"ok": False, "service": SERVICE_NAME, "time": int(time.time()), "error": message}
    if extra:
        payload.update(extra)
    return jsonify(payload), status

# ----------------------------
# Routes
# ----------------------------
@app.get("/health")
def health():
    return ok()

@app.post("/notify-telegram")
def notify_telegram():
    """
    Body JSON: { "text": "Hello from RaidenX8!" }
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return fail("Telegram env not set (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID).", 500)

    try:
        data = request.get_json(force=True, silent=True) or {}
        text = str(data.get("text", "")).strip()
        if not text:
            return fail("Missing 'text'.", 422)

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=15)
        if resp.status_code != 200:
            log.error("Telegram response: %s - %s", resp.status_code, resp.text)
            return fail("Telegram API error.", 502, {"telegram_status": resp.status_code})

        return ok({"sent": True})
    except Exception as e:
        log.exception("notify-telegram error")
        return fail(f"Exception: {e}", 500)

@app.post("/ask")
def ask():
    """
    Body JSON: { "question": "..." }
    - Nếu có GEMINI_API_KEY: gọi Gemini 1.5-pro (REST simple).
    - Nếu không có API: trả lời mock để UI vẫn chạy.
    """
    data = request.get_json(force=True, silent=True) or {}
    question = str(data.get("question", "")).strip()
    if not question:
        return fail("Missing 'question'.", 422)

    if not GEMINI_API_KEY:
        # Không có API key vẫn trả về cho UI hiển thị được
        reply = f"[Mock AI] Bạn hỏi: “{question}”. Hãy cấu hình GEMINI_API_KEY để nhận câu trả lời thật."
        return ok({"answer": reply, "provider": "mock"})

    try:
        # Gọi Gemini (REST)
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": question}]}]
        }
        params = {"key": GEMINI_API_KEY}

        r = requests.post(url, headers=headers, json=payload, params=params, timeout=30)
        if r.status_code != 200:
            log.error("Gemini error %s: %s", r.status_code, r.text)
            return fail("Gemini API error.", 502, {"gemini_status": r.status_code})

        data = r.json()
        # Lấy text đầu tiên
        answer = (
            data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
        ) or "(Empty)"
        return ok({"answer": answer, "provider": "gemini"})
    except Exception as e:
        log.exception("ask error")
        return fail(f"Exception: {e}", 500)

# ----------------------------
# Main
# ----------------------------
if __name__ == "__main__":
    # Dev run (trên Render sẽ dùng gunicorn)
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
