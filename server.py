import os, time, requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# ---------- App ----------
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY","")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY","")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN","")

# ---------- Health ----------
@app.route("/", methods=["GET"])
def health():
    return jsonify({"ok": True, "name": "raidenx8-api", "socket": True})

# ---------- Telegram Notify ----------
@app.route("/notify", methods=["POST"])
def notify():
    data = request.get_json(silent=True) or {}
    chat_id = str(data.get("chat_id","")).strip()
    text = str(data.get("text","")).strip()
    if not chat_id or not text:
        return jsonify({"ok": False, "error": "chat_id and text are required"}), 400
    if not TELEGRAM_BOT_TOKEN:
        return jsonify({"ok": False, "error": "Missing TELEGRAM_BOT_TOKEN"}), 500
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": chat_id, "text": text})
    try:
        j = r.json()
    except Exception:
        return jsonify({"ok": False, "error": f"Telegram non-JSON: {r.text[:120]}"}), 502
    if not j.get("ok", False):
        return jsonify({"ok": False, "error": j.get("description","telegram error")}), 400
    # push to socket listeners
    socketio.emit("tg_message", {"chat_id": chat_id, "text": text})
    return jsonify({"ok": True, "result": j})

# ---------- AI Endpoint ----------
def call_openai(prompt: str) -> str:
    if not OPENAI_API_KEY: return "(OpenAI key missing)"
    try:
        # Minimal example using the responses API
        import openai
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"system","content":"You are RaidenX8 AI assistant."},
                      {"role":"user","content": prompt}],
            temperature=0.4,
        )
        return res.choices[0].message.content.strip()
    except Exception as e:
        return f"(OpenAI error: {e})"

def call_gemini(prompt: str) -> str:
    if not GEMINI_API_KEY: return "(Gemini key missing)"
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
        out = model.generate_content(prompt)
        return out.text.strip()
    except Exception as e:
        return f"(Gemini error: {e})"

@app.route("/ai", methods=["POST"])
def ai():
    data = request.get_json(silent=True) or {}
    message = str(data.get("message","")).strip()
    provider = (data.get("provider") or "openai").lower()
    if not message:
        return jsonify({"ok": False, "error": "message required"}), 400
    if provider == "gemini":
        answer = call_gemini(message)
    else:
        answer = call_openai(message)
    # push to socket listeners
    socketio.emit("ai_reply", {"answer": answer})
    return jsonify({"ok": True, "answer": answer})

# ---------- Optional: simple Telegram inbound poller ----------
def poll_telegram():
    if not TELEGRAM_BOT_TOKEN: 
        return
    offset = None
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
                params={"timeout": 25, "offset": offset})
            j = r.json()
            for u in j.get("result", []):
                offset = u["update_id"] + 1
                if "message" in u and "text" in u["message"]:
                    m = u["message"]
                    socketio.emit("tg_message", {
                        "chat_id": m["chat"]["id"],
                        "text": m["text"]
                    })
        except Exception:
            time.sleep(2)

import threading
threading.Thread(target=poll_telegram, daemon=True).start()

if __name__ == "__main__":
    # eventlet is auto-chosen by SocketIO if installed
    port = int(os.getenv("PORT", "10000"))
    socketio.run(app, host="0.0.0.0", port=port)
