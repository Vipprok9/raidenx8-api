import os
import json
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==== Đọc biến môi trường ====
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

# ==== Debug log khi khởi động ====
print("=== ENV CHECK (Render) ===")
print("BOT_TOKEN:", "✅ SET" if BOT_TOKEN else "❌ NOT SET")
print("CHAT_ID  :", "✅ SET" if CHAT_ID else "❌ NOT SET")
print("OPENAI_KEY:", "✅ SET" if OPENAI_KEY else "❌ NOT SET")
print("==========================")

# ==== Endpoint test health ====
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

# ==== Endpoint check env trực tiếp ====
@app.route("/envcheck", methods=["GET"])
def envcheck():
    return jsonify({
        "BOT_TOKEN": "✅ SET" if BOT_TOKEN else "❌ NOT SET",
        "CHAT_ID": "✅ SET" if CHAT_ID else "❌ NOT SET",
        "OPENAI_KEY": "✅ SET" if OPENAI_KEY else "❌ NOT SET"
    })

# ==== Endpoint gửi tin nhắn thủ công ====
@app.route("/send", methods=["POST"])
def send_message():
    try:
        data = request.get_json(force=True)
        text = data.get("text", "Hello from Render 🚀")

        if not BOT_TOKEN or not CHAT_ID:
            return jsonify({"ok": False, "error": "Missing BOT_TOKEN or CHAT_ID"}), 500

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        resp = requests.post(url, json={"chat_id": CHAT_ID, "text": text})

        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ==== Webhook nhận tin nhắn từ Telegram ====
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        update = request.get_json()
        print("Incoming update:", json.dumps(update, indent=2, ensure_ascii=False))

        if "message" in update:
            chat_id = update["message"]["chat"]["id"]
            text = update["message"].get("text", "")

            # Trả lời đơn giản
            reply = f"Echo: {text}"
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": reply})

        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ==== Start server ====
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
