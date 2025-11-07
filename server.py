import os
import time
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
# Nếu muốn chỉ cho phép từ domain frontend, đổi origins thành ["https://raidenx8.pages.dev"]
CORS(app, resources={r"/*": {"origins": "*"}})

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"

@app.get("/health")
def health():
    return jsonify({"status": "ok", "ts": int(time.time())})

def ask_gemini(prompt: str) -> str:
    """Gọi Gemini 1 lần, KHÔNG đệ quy."""
    if not GEMINI_API_KEY:
        return "Thiếu GEMINI_API_KEY trên server."
    try:
        resp = requests.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30,
        )
        data = resp.json()
        # Trả message rõ ràng nếu API trả lỗi
        if "candidates" not in data:
            return f"Lỗi Gemini: {data}"
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"Lỗi Gemini: {e}"

@app.post("/ai/chat")
def ai_chat():
    body = request.get_json(silent=True) or {}
    msg = (body.get("message") or "").strip()
    if not msg:
        return jsonify({"reply": "Bạn chưa nhập nội dung."}), 400
    reply = ask_gemini(msg)
    return jsonify({"reply": reply})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
