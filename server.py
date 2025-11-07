import os
import uuid
import tempfile
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import requests
from gtts import gTTS

# ====== Config ======
API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
# Model bạn đã list ra trong curl: dùng bản pro preview ổn định
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-2.5-pro-preview-03-25")
# Cho phép CORS từ Cloudflare Pages
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "*")  # ví dụ: https://raidenx8.pages.dev

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": [FRONTEND_ORIGIN, "*"]}})

GLM_URL = "https://generativelanguage.googleapis.com/v1beta"

# ====== Helpers ======
def gemini_generate_content(message, system=None, model=DEFAULT_MODEL, temperature=0.7, top_p=0.95, top_k=40, candidate_count=1):
    if not API_KEY:
        return {"error": "Missing GEMINI_API_KEY"}, 500

    url = f"{GLM_URL}/{model}:generateContent?key={API_KEY}"

    # Gemini v1beta schema
    contents = []
    if system:
        contents.append({
            "role": "user",
            "parts": [{"text": f"[SYSTEM]\n{system}"}]
        })
    contents.append({"role": "user", "parts": [{"text": message}]})

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "topP": top_p,
            "topK": top_k,
            "candidateCount": candidate_count,
        }
    }

    try:
        r = requests.post(url, json=payload, timeout=45)
        if r.status_code != 200:
            return {"error": r.text}, r.status_code
        data = r.json()
        # Lấy text đầu tiên
        text = ""
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            text = ""
        return {"text": text, "raw": data}, 200
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}, 500


# ====== Routes ======
@app.route("/health")
def health():
    return jsonify(ok=True, model=DEFAULT_MODEL)

@app.route("/ai/chat", methods=["POST"])
def ai_chat():
    """
    Body JSON:
    { "message": "...", "system": "optional system prompt", "model": "optional" }
    """
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    system = (data.get("system") or "Bạn là RaidenX8. Trả lời ngắn gọn, rõ ràng, có ví dụ khi cần.").strip()
    model = (data.get("model") or DEFAULT_MODEL).strip()

    if not message:
        return jsonify(error="message is required"), 400

    out, code = gemini_generate_content(message, system=system, model=model)
    return jsonify(out), code

# Vì frontend cũ có thể gọi /ai/chat_sync nên map cùng logic
@app.route("/ai/chat_sync", methods=["POST"])
def ai_chat_sync():
    return ai_chat()

@app.route("/api/tts", methods=["POST"])
def api_tts():
    """
    Body JSON:
    { "text": "Xin chào", "lang": "vi" }
    Trả về file MP3.
    """
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    lang = (data.get("lang") or "vi").strip()

    if not text:
        return jsonify(error="text is required"), 400

    try:
        # Tạo file tạm mp3
        tmp_dir = tempfile.gettempdir()
        fname = f"tts-{uuid.uuid4().hex}.mp3"
        fpath = os.path.join(tmp_dir, fname)

        tts = gTTS(text=text, lang=lang)
        tts.save(fpath)

        # Gửi file rồi xóa sau
        return send_file(fpath, as_attachment=True, download_name="voice.mp3", mimetype="audio/mpeg")
    except Exception as e:
        return jsonify(error=f"TTS failed: {e}"), 500

# ====== Main (local) ======
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
