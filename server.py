from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# Env vars
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --------- ROUTES ---------

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

# Send Telegram message
@app.route("/send", methods=["POST"])
def send_message():
    data = request.json
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "missing text"}), 400

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    res = requests.post(url, json=payload)
    return jsonify(res.json())

# Telegram webhook
@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    update = request.json
    if not update:
        return jsonify({"error": "no update"}), 400

    if "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "")
        reply = f"You said: {text}"

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": reply})

    return jsonify({"ok": True})

# AI Chat Proxy
@app.route("/api/chat", methods=["POST"])
def chat_proxy():
    data = request.json
    text = data.get("text", "")
    provider = data.get("provider", "openai")  # "openai" hoặc "gemini"

    if provider == "openai":
        if not OPENAI_API_KEY:
            return jsonify({"error": "OPENAI_API_KEY not set"}), 400
        # gọi OpenAI API
        import openai
        openai.api_key = OPENAI_API_KEY
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": text}]
        )
        reply = response["choices"][0]["message"]["content"]

    elif provider == "gemini":
        if not GEMINI_API_KEY:
            return jsonify({"error": "GEMINI_API_KEY not set"}), 400
        # demo giả sử (thực tế gọi API Google AI Studio)
        reply = f"[Gemini demo] Bạn hỏi: {text}"

    else:
        reply = "Unknown provider"

    return jsonify({"reply": reply})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
