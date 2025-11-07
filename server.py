import os, json, time
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from requests.adapters import HTTPAdapter, Retry

app = Flask(__name__)
CORS(app)

# ====== Config ======
API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
# Dùng đúng endpoint v1beta + model alias -latest
MODEL_ID = os.getenv("GEMINI_MODEL", "gemini-1.5-flash-latest")
BASE_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_ID}:generateContent"

# Tạo session có retry để đỡ 502/429
session = requests.Session()
retries = Retry(
    total=4,
    backoff_factor=0.6,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["POST", "GET"],
)
adapter = HTTPAdapter(max_retries=retries)
session.mount("http://", adapter)
session.mount("https://", adapter)
TIMEOUT = (5, 20)  # (connect, read)

def gemini_generate(text):
    if not API_KEY:
        return None, "Thiếu GEMINI_API_KEY trên Render"

    url = f"{BASE_URL}?key={API_KEY}"
    payload = {
        "contents": [
            {
                "parts": [{"text": text}]
            }
        ]
    }
    headers = {"Content-Type": "application/json"}
    r = session.post(url, headers=headers, data=json.dumps(payload), timeout=TIMEOUT)
    if r.status_code != 200:
        try:
            err = r.json()
        except Exception:
            err = {"error": {"code": r.status_code, "message": r.text[:200]}}
        # Trả lỗi gọn để frontend hiện đúng
        return None, f"Gemini lỗi {err.get('error', {}).get('code')}: {err.get('error', {}).get('message')}"
    data = r.json()
    # Parse text (v1beta)
    try:
        candidates = data["candidates"]
        parts = candidates[0]["content"]["parts"]
        text_out = "".join(p.get("text", "") for p in parts)
        return text_out.strip(), None
    except Exception as e:
        return None, f"Lỗi parse response: {e}"

@app.route("/health")
def health():
    return {"ok": True, "model": MODEL_ID}, 200

@app.route("/ai/chat", methods=["POST"])
def ai_chat():
    try:
        body = request.get_json(force=True, silent=True) or {}
        text = (body.get("message") or "").strip()
        if not text:
            return jsonify({"error": "Thiếu 'message'"}), 400

        # Gọi Gemini qua proxy này
        reply, err = gemini_generate(text)
        if err:
            return jsonify({"error": err}), 502
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": f"Server exception: {e}"}), 500

if __name__ == "__main__":
    # Local run: python server.py
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
