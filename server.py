# server.py
import os, json
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

app = Flask(__name__)
CORS(app)

# ====== ENV ======
API_KEY   = os.getenv("GEMINI_API_KEY", "")
MODEL_ID  = os.getenv("GEMINI_MODEL", "gemini-1.5-flash-latest").strip()
BASE_URL  = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_ID}:generateContent"

# ====== HTTP client (retry + timeout) ======
session = requests.Session()
retries = Retry(
    total=6,
    backoff_factor=0.8,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["POST", "GET"]
)
adapter = HTTPAdapter(max_retries=retries)
session.mount("http://", adapter)
session.mount("https://", adapter)

# tăng timeout: (connect, read)
TIMEOUT = (10, 60)

def gemini_generate(text: str):
    if not API_KEY:
        return None, "Thiếu GEMINI_API_KEY"
    if not MODEL_ID:
        return None, "Thiếu GEMINI_MODEL"

    url = f"{BASE_URL}?key={API_KEY}"
    payload = {
        "contents": [
            {"parts": [{"text": text[:4000]}]} # cắt bớt để tránh 413
        ]
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "RaidenX8-Backend/1.0"
    }

    try:
        r = session.post(url, headers=headers, data=json.dumps(payload), timeout=TIMEOUT)
    except requests.exceptions.RequestException as e:
        return None, f"Lỗi mạng: {e}"

    # Non-200: trả gọn lỗi để frontend hiểu
    if r.status_code != 200:
        try:
            err = r.json()
        except Exception:
            err = {"error": {"code": r.status_code, "message": r.text[:200]}}
        return None, f"Gemini lỗi {err.get('error', {}).get('code', r.status_code)}: {err.get('error', {}).get('message', 'Unknown')}"

    # Parse v1beta
    try:
        data = r.json()
        cands = data.get("candidates", [])
        parts = cands[0].get("content", {}).get("parts", []) if cands else []
        out = "".join(p.get("text", "") for p in parts).strip()
        return out or "(không có nội dung)", None
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

        reply, err = gemini_generate(text)
        if err:
            # 502 khi upstream lỗi/timeout để frontend hiển thị “API lỗi”
            return jsonify({"error": err}), 502
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": f"Server exception: {e}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
