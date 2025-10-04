import os
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # <-- thêm biến môi trường này trên Render

app = Flask(__name__)
CORS(app)

@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "service": "RaidenX8 API",
        "message": "Use POST /chat with provider=openai|gemini"
    })

@app.route("/health")
def health():
    return jsonify({"ok": True})

def call_openai_chat(user_msg: str, model: str):
    if not OPENAI_API_KEY:
        return None, ("Missing OPENAI_API_KEY env", 500)

    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": model or "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "You are a concise, helpful assistant."},
                {"role": "user", "content": user_msg}
            ],
            "temperature": 0.6,
            "max_tokens": 512,
        },
        timeout=60,
    )
    if resp.status_code >= 400:
        return None, (f"OpenAI upstream error {resp.status_code}: {resp.text}", 502)

    data = resp.json()
    text = data["choices"][0]["message"]["content"]
    return text, None

def call_gemini_chat(user_msg: str, model: str):
    if not GEMINI_API_KEY:
        return None, ("Missing GEMINI_API_KEY env", 500)

    # Mặc định dùng gemini-1.5-flash nếu không chỉ định
    model = model or "gemini-1.5-flash"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{
            "role": "user",
            "parts": [{"text": user_msg}]
        }],
        "generationConfig": {
            "temperature": 0.6,
            "maxOutputTokens": 512
        }
    }
    resp = requests.post(url, json=payload, timeout=60)
    if resp.status_code >= 400:
        return None, (f"Gemini upstream error {resp.status_code}: {resp.text}", 502)

    data = resp.json()
    # Lấy text đầu tiên trong candidate 0
    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts)
    except Exception:
        text = data.get("candidates", [{}])[0].get("output_text") or ""
    if not text:
        text = "(no content)"
    return text, None

@app.route("/chat", methods=["POST"])
def chat():
    """
    Body:
    {
      "message": "Xin chào!",
      "provider": "gemini" | "openai",   # optional (mặc định "openai")
      "model": "gemini-1.5-flash" | "gpt-4o-mini"  # optional
    }
    """
    data = request.get_json(silent=True) or {}
    user_msg = (data.get("message") or "").strip()
    provider = (data.get("provider") or "openai").strip().lower()
    model = (data.get("model") or "").strip()

    if not user_msg:
        return jsonify({"error": "message is required"}), 400

    try:
        if provider == "gemini":
            reply, err = call_gemini_chat(user_msg, model)
        else:  # default openai
            reply, err = call_openai_chat(user_msg, model)

        if err:
            msg, code = err
            return jsonify({"error": msg}), code
        return jsonify({"ok": True, "provider": provider, "model": model or ("gemini-1.5-flash" if provider=="gemini" else "gpt-4o-mini"), "reply": reply})

    except requests.Timeout:
        return jsonify({"error": "upstream_timeout"}), 504
    except Exception as e:
        return jsonify({"error": "server_error", "detail": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
