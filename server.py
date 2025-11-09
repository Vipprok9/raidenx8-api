import os, datetime
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Optional keys
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

def rule_based(text):
    t = text.lower()
    if "thời tiết" in t and "huế" in t:
        return "Huế hôm nay: mát, có mưa rào nhẹ (demo)."
    if "btc" in t or "bitcoin" in t:
        return "BTC hiện dao động quanh ~ $70k (demo)."
    return "Xin chào! API đã nhận: " + text

@app.route("/health")
def health():
    return jsonify(ok=True, time=datetime.datetime.utcnow().isoformat()+"Z")

@app.route("/ai/chat", methods=["POST"])
def ai_chat():
    data = request.get_json(force=True) or {}
    provider = data.get("provider") or "demo"
    model = data.get("model") or ""
    message = data.get("message") or ""

    # If no keys configured, fallback to rule-based demo
    if not OPENAI_KEY and not GEMINI_KEY:
        return jsonify(reply=rule_based(message))

    # Minimal provider switch; safe demo content (no external calls here)
    # You can later plug real SDKs: openai / google-genai when keys available on Render.
    return jsonify(reply=f"[{provider}:{model}] Đã nhận: " + message)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
