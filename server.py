import os
import time
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

# =========================
# App & Config
# =========================
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# Gemini endpoints (Google AI Studio)
GEMINI_CHAT_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"
)

# Optional: simple healthcheck
@app.route("/health")
def health():
    return jsonify({"status": "ok", "ts": int(time.time())})

# =========================
# Helpers
# =========================
def call_gemini(message: str) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("Thiếu GEMINI_API_KEY")

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": message}
                ]
            }
        ]
    }
    resp = requests.post(
        f"{GEMINI_CHAT_URL}?key={GEMINI_API_KEY}",
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    # lấy text an toàn
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini không trả về candidates")

    content = candidates[0].get("content", {})
    parts = content.get("parts", [])
    if not parts or "text" not in parts[0]:
        raise RuntimeError("Gemini không có phần text")

    return parts[0]["text"].strip()


def call_openai(message: str) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("Thiếu OPENAI_API_KEY")

    # dùng Chat Completions (gpt-4o-mini/gpt-4o, tuỳ bạn)
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Bạn là trợ lý hữu ích, trả lời ngắn gọn."},
            {"role": "user", "content": message},
        ],
        "temperature": 0.7,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()

# =========================
# Main API
# =========================
@app.route("/ai/chat", methods=["POST"])
def ai_chat():
    """
    Frontend sẽ gọi POST /ai/chat với JSON:
    {"message": "..."}
    Trả về: {"reply": "..."}
    """
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()

    if not message:
        return jsonify({"reply": "Bạn chưa nhập nội dung."}), 400

    try:
        # Ưu tiên Gemini
        reply = call_gemini(message)
        return jsonify({"reply": reply})
    except Exception as g_err:
        # Fallback OpenAI (nếu có)
        try:
            if OPENAI_API_KEY:
                reply = call_openai(message)
                return jsonify({"reply": reply, "provider": "openai-fallback"})
            # Nếu không có fallback
            return jsonify({"reply": f"AI lỗi (Gemini): {g_err}"}), 500
        except Exception as o_err:
            return jsonify({"reply": f"AI lỗi (Gemini & OpenAI): {o_err}"}), 500


# =========== run local ===========
if __name__ == "__main__":
    # Chạy dev local: python server.py
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
