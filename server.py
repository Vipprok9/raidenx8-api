# server.py — RaidenX8 (Google AI Studio v1beta + Gemini 1.5 Flash)

from flask import Flask, request, jsonify
from flask_cors import CORS
import os, requests

app = Flask(__name__)
CORS(app)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")   # key từ studio.google.com
MODEL = "gemini-1.5-flash"                     # miễn phí, nhanh
BASE_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GEMINI_API_KEY}"

@app.get("/")
def root():
    return "RaidenX8 API online ✅", 200

@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200

@app.post("/ai/chat")
def ai_chat():
    try:
        data = request.get_json(force=True) or {}
        msg = (data.get("message") or "").strip()
        if not msg:
            return jsonify({"reply": "Thiếu nội dung"}), 400

        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": msg}]}
            ]
        }
        r = requests.post(BASE_URL, json=payload, timeout=25)
        res = r.json()

        if r.ok and "candidates" in res and res["candidates"]:
            parts = res["candidates"][0].get("content", {}).get("parts", [])
            text = parts[0].get("text", "") if parts else ""
            return jsonify({"reply": text or "[empty]"})
        else:
            # Trả nguyên lỗi để debug phía FE
            return jsonify({"reply": f"Lỗi Gemini: {res}"}), 502

    except Exception as e:
        return jsonify({"reply": f"Lỗi server: {e}"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
