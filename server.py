from flask import Flask, request, jsonify
from flask_cors import CORS
import os, requests

app = Flask(__name__)
CORS(app)

# === ENV VAR ===
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-1.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

# === ROUTES ===
@app.route("/")
def home():
    return "RaidenX8 API online ✅", 200

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/ai/chat", methods=["POST"])
def ai_chat():
    try:
        data = request.get_json(force=True)
        message = data.get("message", "")
        if not message:
            return jsonify({"reply": "Thiếu nội dung"}), 400

        # Gửi request đến Google Gemini API
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": message}]
                }
            ]
        }
        r = requests.post(GEMINI_URL, json=payload, timeout=25)
        result = r.json()

        # Parse phản hồi
        if "candidates" in result:
            reply = result["candidates"][0]["content"]["parts"][0]["text"]
        else:
            reply = f"Lỗi Gemini: {result}"

        return jsonify({"reply": reply})

    except Exception as e:
        return jsonify({"reply": f"Lỗi server: {e}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
