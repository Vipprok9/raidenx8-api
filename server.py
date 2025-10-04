import os
import time
import logging
from typing import Any, Dict

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

# ---------- App & CORS ----------
app = Flask(__name__)
# Cho phép mọi origin (đơn giản nhất). Nếu muốn chỉ cho pages.dev:
# CORS(app, resources={r"/api/*": {"origins": "https://raidenx8.pages.dev"}})
CORS(app)

# ---------- Config qua ENV ----------
SERVICE_NAME = os.getenv("SERVICE_NAME", "raidenx8-api")

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "").strip()
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "").strip()

# Optional: Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("raidenx8-api")


# ---------- Helpers ----------
def _json_ok(**extra: Dict[str, Any]):
    base = {"ok": True, "service": SERVICE_NAME, "time": int(time.time())}
    base.update(extra)
    return jsonify(base)


def _json_error(message: str, http_code: int = 400, **extra: Dict[str, Any]):
    base = {"ok": False, "service": SERVICE_NAME, "time": int(time.time()), "error": message}
    base.update(extra)
    return jsonify(base), http_code


# ---------- Routes ----------
@app.get("/")
def root():
    return _json_ok(msg="alive")


@app.get("/health")
def health():
    return _json_ok()


@app.post("/api/notify")
def api_notify():
    """
    Body JSON:
      { "text": "nội dung" }
    Env cần có: TG_BOT_TOKEN, TG_CHAT_ID
    """
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return _json_error("Missing TG_BOT_TOKEN or TG_CHAT_ID in environment.", 500)

    data = request.get_json(silent=True) or {}
    text = (data.get("text") or data.get("message") or "").strip()
    if not text:
        return _json_error("Missing 'text' in JSON body.", 422)

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        ok = resp.ok
        body = {}
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}

        if not ok:
            logger.error("Telegram error %s: %s", resp.status_code, body)
            return _json_error("Telegram sendMessage failed.", 502, telegram=body)

        return _json_ok(sent=True, telegram=body)
    except requests.Timeout:
        return _json_error("Telegram request timeout.", 504)
    except Exception as e:
        logger.exception("Notify error")
        return _json_error(f"Notify exception: {e}", 500)


@app.post("/api/chat")
def api_chat():
    """
    Body JSON:
      { "prompt": "câu hỏi" }

    - Nếu có GEMINI_API_KEY: gọi Gemini REST (v1beta).
    - Nếu không có: trả lời echo để test UI.
    """
    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or data.get("message") or "").strip()
    if not prompt:
        return _json_error("Missing 'prompt' in JSON body.", 422)

    # Không có key -> echo để an toàn deploy
    if not GEMINI_API_KEY:
        return _json_ok(reply=f"Bạn vừa nói: {prompt}", model="echo")

    # Gọi Gemini qua REST (không cần cài thêm thư viện)
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    body = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ]
    }
    try:
        resp = requests.post(url, json=body, timeout=15)
        jr = resp.json()
        if not resp.ok:
            logger.error("Gemini error %s: %s", resp.status_code, jr)
            return _json_error("Gemini API error.", 502, gemini=jr)

        # Lấy text từ candidates
        text = ""
        try:
            text = jr["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            text = ""

        if not text:
            text = "(Không nhận được nội dung trả về từ Gemini.)"

        return _json_ok(reply=text, model=GEMINI_MODEL)
    except requests.Timeout:
        return _json_error("Gemini request timeout.", 504)
    except Exception as e:
        logger.exception("Gemini exception")
        return _json_error(f"Gemini exception: {e}", 500)


# ---------- Main (local run) ----------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False)
