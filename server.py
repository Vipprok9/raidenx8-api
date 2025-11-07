import os, json
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from requests.adapters import HTTPAdapter, Retry

app = Flask(__name__)
CORS(app)

# ====== ENV ======
API_KEY   = os.getenv("GEMINI_API_KEY", "")
MODEL_ID  = os.getenv("GEMINI_MODEL", "gemini-1.5-flash-latest").strip()
BASE_URL  = f"https://generativelanguage.googleapis.com/v1/models/{MODEL_ID}:generateContent"

# HTTP session với retry & timeout
session = requests.Session()
retries = Retry(total=3, backoff_factor=0.6, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["POST", "GET"])
adapter = HTTPAdapter(max_retries=retries)
session.mount("http://", adapter)
session.mount("https://", adapter)
TIMEOUT = (5, 25)  # (connect, read)

def gemini_generate(text: str):
    if not API_KEY:
        return None, "Thiếu GEMINI_API_KEY"
    url = f"{BASE_URL}?key={API_KEY}"

    payload = {
        "contents": [
            {"parts": [{"text": text[:6000]}]}  # cắt bớt để tránh quá giới hạn
        ]
    }
    headers = {"Content-Type": "application/json"}

    r = None
    try:
        r = session.post(url, headers=headers, data=json.dumps(payload), timeout=TIMEOUT)
    except Exception as e:
        return None, f"Lỗi gọi API: {e}"

    # Nếu Google trả không phải 200, trả luôn thân lỗi để nhìn rõ
    if r.status_code != 200:
        body = r.text
        return None, f"Gemini HTTP {r.status_code}: {body}"

    data = r.json()

    # v1: parse từ candidates → content → parts[].text
    try:
        cands = data.get("candidates") or []
        parts = (cands[0].get("content") or {}).get("parts") or []
        out = "".join([p.get("text","") for p in parts]).strip()
        if not out:
            return None, f"Parse rỗng: {json.dumps(data)[:400]}"
        return out, None
    except Exception as e:
        return None, f"Lỗi parse: {e} | raw={json.dumps(data)[:400]}"

@app.route("/health")
def health():
    return {"ok": True, "model": MODEL_ID}

# Gọi ListModels để kiểm tra key/model khi cần
@app.route("/debug/models")
def debug_models():
    try:
        url = f"https://generativelanguage.googleapis.com/v1/models?key={API_KEY}"
        r = session.get(url, timeout=TIMEOUT)
        return jsonify({"code": r.status_code, "body": r.json() if r.headers.get("content-type","").startswith("application/json") else r.text})
    except Exception as e:
        return jsonify({"error": str(e)}), 200

@app.route("/ai/chat", methods=["POST"])
def ai_chat():
    try:
        body = request.get_json(force=True, silent=True) or {}
        text = (body.get("message") or "").strip()
        if not text:
            return jsonify({"error": "Thiếu 'message'"}), 200

        reply, err = gemini_generate(text)
        if err:
            # Trả về 200 để frontend hiển thị chi tiết thay vì chỉ thấy 502
            return jsonify({"error": err}), 200
        return jsonify({"reply": reply}), 200
    except Exception as e:
        return jsonify({"error": f"Server exception: {e}"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
