import os, requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ====== ENV ======
BOT_TOKEN       = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
OPENAI_API_KEY  = os.environ.get("OPENAI_API_KEY", "").strip()
GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY", "").strip()

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage" if BOT_TOKEN else None

@app.get("/")
def health():
    return jsonify(ok=True, service="raidenx8-api")

# ====== Telegram notify ======
@app.post("/notify")
def notify():
    data = request.get_json(silent=True) or {}
    chat_id = str(data.get("chat_id", "")).strip()
    text    = str(data.get("text", "")).strip()[:4000]

    if not BOT_TOKEN:
        return jsonify(ok=False, error="Missing TELEGRAM_BOT_TOKEN"), 500
    if not chat_id or not text:
        return jsonify(ok=False, error="chat_id and text are required"), 400

    try:
        r = requests.post(TG_API, json={"chat_id": chat_id, "text": text, "parse_mode":"HTML"}, timeout=12)
        try:
            payload = r.json()
        except Exception:
            payload = {"raw": r.text}
        return jsonify(ok=r.ok, status=r.status_code, telegram=payload), (200 if r.ok else 502)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

# ====== AI chat (OpenAI + Gemini) ======
@app.post("/chat")
def chat():
    data = request.get_json(silent=True) or {}
    provider = (data.get("provider") or "openai").lower()
    user_msg = (data.get("message") or "").strip()
    history  = data.get("history") or []  # optional [{role, content}, ...]

    if not user_msg:
        return jsonify(ok=False, error="message is required"), 400

    try:
        if provider == "openai":
            if not OPENAI_API_KEY:
                return jsonify(ok=False, error="Missing OPENAI_API_KEY"), 500
            # build messages
            msgs = [{"role":"system","content":"You are a helpful assistant for RaidenX8 Gen-Z Trend."}]
            if isinstance(history, list):
                msgs += history
            msgs.append({"role":"user","content":user_msg})

            r = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type":"application/json"},
                json={"model":"gpt-4o-mini", "messages":msgs, "temperature":0.4, "max_tokens":500},
                timeout=20
            )
            j = r.json()
            if r.status_code >= 400:
                return jsonify(ok=False, error=j.get("error", j)), 502
            text = j["choices"][0]["message"]["content"]
            return jsonify(ok=True, provider="openai", text=text)

        elif provider == "gemini":
            if not GEMINI_API_KEY:
                return jsonify(ok=False, error="Missing GEMINI_API_KEY"), 500
            # Gemini 1.5 Flash
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
            parts = []
            if isinstance(history, list):
                for turn in history:
                    if turn.get("role") == "user":
                        parts.append({"role":"user","parts":[{"text":turn.get("content","")}]})
                    else:
                        parts.append({"role":"model","parts":[{"text":turn.get("content","")}]})
            parts.append({"role":"user","parts":[{"text":user_msg}]})
            r = requests.post(endpoint, json={"contents": parts}, timeout=20)
            j = r.json()
            if r.status_code >= 400:
                return jsonify(ok=False, error=j), 502
            text = j["candidates"][0]["content"]["parts"][0]["text"]
            return jsonify(ok=True, provider="gemini", text=text)

        else:
            return jsonify(ok=False, error="Unsupported provider. Use 'openai' or 'gemini'."), 400

    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
