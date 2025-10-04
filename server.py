# server.py
import os
import time
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

# ----------------------------------------------------
# App & CORS
# ----------------------------------------------------
app = Flask(__name__)

# Cho phép web của bạn gọi sang (thêm origin bạn cần)
ALLOWED_ORIGINS = {
    "https://raidenx8.pages.dev",
    "https://raidenx8-api.onrender.com",
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
    "*"  # nếu muốn mở hết (không khuyến nghị cho production)
}
CORS(app, resources={r"/*": {"origins": list(ALLOWED_ORIGINS)}}, supports_credentials=False)

@app.after_request
def add_cors_headers(resp):
    # Bổ sung vài header hay dùng khi gọi fetch từ browser
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return resp

# ----------------------------------------------------
# Health check
# ----------------------------------------------------
@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "service": "raidenx8-api",
        "time": int(time.time())
    })

# ----------------------------------------------------
# Notify Telegram: POST /notify  { "text": "..." }
# Cần env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
# ----------------------------------------------------
@app.route("/notify", methods=["POST", "OPTIONS"])
def notify():
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()

    if not text:
        return jsonify({"error": "Missing 'text'"}), 400

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return jsonify({
            "error": "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in environment"
        }), 500

    try:
        tg = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        if tg.status_code >= 400:
            return jsonify({
                "ok": False,
                "telegram_status": tg.status_code,
                "detail": tg.text
            }), 502

        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ----------------------------------------------------
# Ask Gemini: POST /ask { "prompt": "..." }
# Env cần: GEMINI_API_KEY
# Tùy chọn: GEMINI_MODEL (mặc định gemini-1.5-flash), GEMINI_SYSTEM (lời nhắc hệ thống)
# ----------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()
GEMINI_SYSTEM = os.getenv("GEMINI_SYSTEM", "").strip()

def _gemini_endpoint(model: str) -> str:
    return (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{model}:generateContent?key={GEMINI_API_KEY}"
    )

@app.route("/ask", methods=["POST", "OPTIONS"])
def ask():
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    model = (data.get("model") or GEMINI_MODEL).strip() or GEMINI_MODEL

    if not prompt:
        return jsonify({"error": "Missing 'prompt'"}), 400
    if not GEMINI_API_KEY:
        return jsonify({"error": "Server missing GEMINI_API_KEY"}), 500

    # Build payload theo REST của Gemini
    parts = []
    if GEMINI_SYSTEM:
        parts.append({"text": f"System instruction: {GEMINI_SYSTEM}"})
    parts.append({"text": prompt})

    payload = {
        "contents": [
            {"role": "user", "parts": parts}
        ],
        "generationConfig": {
            "temperature": 0.7,
            "topK": 40,
            "topP": 0.95,
            "maxOutputTokens": 1024
        }
    }

    try:
        r = requests.post(
            _gemini_endpoint(model),
            json=payload,
            timeout=60,
        )
        if r.status_code >= 400:
            return jsonify({
                "ok": False,
                "status": r.status_code,
                "detail": r.text
            }), 502

        data = r.json()
        # Trích text gọn gàng
        text = ""
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            text = str(data)

        return jsonify({
            "ok": True,
            "model": model,
            "answer": text
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ----------------------------------------------------
# Run local (Render sẽ dùng gunicorn, phần dưới dành cho dev)
# ----------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)
