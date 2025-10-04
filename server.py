from flask import Flask, request, jsonify
from flask_cors import CORS
import os, requests, time

app = Flask(__name__)
CORS(app)

# Lấy biến môi trường từ Render (hoặc Pydroid3)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # có thể để trống

# ---- ROUTES ----

@app.route("/")
def health():
    return jsonify({"ok": True, "service": "raidenx8-api", "time": int(time.time())})

# --- Gửi Notify Telegram ---
@app.route("/notify", methods=["POST"])
def notify():
    try:
        data = request.get_json(force=True)
        message = data.get("text")
        chat_id = data.get("chat_id") or TELEGRAM_CHAT_ID

        if not TELEGRAM_BOT_TOKEN or not chat_id:
            return jsonify({"ok": False, "error": "Missing Telegram credentials"}), 400

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        res = requests.post(url, json={"chat_id": chat_id, "text": message})
        return jsonify({"ok": res.ok, "status_code": res.status_code})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# --- Chat AI (OpenAI / Gemini hoặc fallback demo) ---
@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json(force=True)
        message = data.get("message", "")
        provider = data.get("provider", "openai").lower()

        # Nếu có key OpenAI thật thì gọi API
        if OPENAI_API_KEY:
            import openai
            openai.api_key = OPENAI_API_KEY
            completion = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": message}]
            )
            reply = completion.choices[0].message["content"]
        else:
            # Fallback demo (tự phản hồi)
            if "price" in message.lower():
                reply = "BTC đang quanh 120k$, ETH 4.4k$. Nguồn CoinGecko 🌐"
            elif "hello" in message.lower() or "hi" in message.lower():
                reply = "Xin chào 👋! Mình là RaidenX8 AI Assistant."
            else:
                reply = f"RaidenX8 (demo): bạn vừa nói “{message}”."
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"reply": f"Lỗi: {str(e)}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
