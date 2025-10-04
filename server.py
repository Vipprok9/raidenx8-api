import os
import json
import requests
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from collections import deque
from datetime import datetime

app = Flask(__name__)

# Bật CORS đầy đủ
CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    supports_credentials=False,
    methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# === ENV VARS ===
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

# === EVENT BUFFER ===
events = deque(maxlen=50)

def push_event(kind, data):
    events.append({
        "kind": kind,
        "data": data,
        "ts": int(datetime.utcnow().timestamp())
    })

# === HEALTH CHECK ===
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

# === EVENTS ===
@app.route("/events", methods=["GET"])
def get_events():
    return jsonify({"events": list(events)})

# === SEND (POST) ===
@app.route("/send", methods=["OPTIONS"])
def send_options():
    return make_response("", 204)

@app.route("/send", methods=["POST"])
def send():
    if not BOT_TOKEN or not CHAT_ID:
        return jsonify({"ok": False, "error": "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID"}), 400

    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "text is empty"}), 400

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=20)
        ok = resp.ok
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text}
        push_event("outgoing", {"text": text, "ok": ok, "status": resp.status_code, "tg": data})
        return jsonify({"ok": ok, "status": resp.status_code, "tg": data}), (200 if ok else resp.status_code)
    except Exception as e:
        push_event("outgoing_error", {"text": text, "error": str(e)})
        return jsonify({"ok": False, "error": str(e)}), 500

# === WEBHOOK TELEGRAM ===
@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(force=True, silent=True) or {}
    push_event("incoming", update)
    try:
        message = update.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "")

        if chat_id and text:
            reply = f"Echo: {text}"
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": reply})
    except Exception as e:
        push_event("incoming_error", {"error": str(e)})

    return jsonify({"ok": True})

# === ROOT (tránh 404) ===
@app.route("/", methods=["GET"])
def root():
    return "RaidenX8 backend running. Try /health or /events"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
