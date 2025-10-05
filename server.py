import os, io, hashlib, time, base64, json
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from datetime import datetime
from pathlib import Path

# ===== Optional SDKs (tự động bỏ qua nếu không có) =====
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GOOGLE_CRED = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()

# OpenAI (TTS)
try:
    from openai import OpenAI
    _openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
except Exception:
    _openai_client = None

# Google Cloud TTS
_google_tts_client = None
try:
    if GOOGLE_CRED and os.path.isfile(GOOGLE_CRED):
        from google.cloud import texttospeech
        _google_tts_client = texttospeech.TextToSpeechClient()
except Exception:
    _google_tts_client = None

# gTTS fallback (không cần API key)
try:
    from gtts import gTTS
    _has_gtts = True
except Exception:
    _has_gtts = False

# Gemini dùng để sinh text (nếu cần), không dùng TTS (Google TTS đảm nhiệm TTS)
_gemini_available = bool(GEMINI_API_KEY)

# ===== Flask =====
app = Flask(__name__)
CORS(app)

CACHE_DIR = Path(os.getenv("CACHE_DIR", "/tmp/tts_cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# -------- Helpers --------
def _cache_key(text: str, lang: str, voice: str, provider: str) -> Path:
    key_raw = f"{provider}|{lang}|{voice}|{text}".encode("utf-8")
    h = hashlib.sha256(key_raw).hexdigest()
    return CACHE_DIR / f"{h}.mp3"

def _send_mp3(path: Path):
    return send_file(str(path), mimetype="audio/mpeg", as_attachment=False,
                     download_name="tts.mp3")

def _ok():
    return jsonify({"ok": True, "time": datetime.utcnow().isoformat() + "Z"})

# -------- Providers --------
def tts_openai(text, lang="vi", voice="alloy"):
    """
    OpenAI TTS: model 'gpt-4o-mini-tts' (ổn, nhanh).
    voices: alloy, verse, aria, coral, …
    """
    if not _openai_client:
        raise RuntimeError("OPENAI client not available")
    model = "gpt-4o-mini-tts"
    fmt = "mp3"
    resp = _openai_client.audio.speech.create(
        model=model,
        voice=voice or "alloy",
        input=text,
        format=fmt
    )
    # SDK trả về base64 trong 'content' hoặc .to_bytes()
    audio_bytes = resp.read() if hasattr(resp, "read") else resp.content
    return audio_bytes

def tts_google(text, lang="vi-VN", voice="vi-VN-Standard-A"):
    """
    Google Cloud Text-to-Speech (chất lượng cao, nhiều giọng, ổn định).
    Cần GOOGLE_APPLICATION_CREDENTIALS trỏ tới JSON service account.
    """
    if not _google_tts_client:
        raise RuntimeError("Google TTS client not available")
    from google.cloud import texttospeech

    synthesis_input = texttospeech.SynthesisInput(text=text)

    voice_params = texttospeech.VoiceSelectionParams(
        language_code=lang or "vi-VN",
        name=voice or "vi-VN-Standard-A",
        ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=1.0,
        pitch=0.0
    )
    response = _google_tts_client.synthesize_speech(
        input=synthesis_input,
        voice=voice_params,
        audio_config=audio_config
    )
    return response.audio_content

def tts_gtts(text, lang="vi", voice=None):
    """
    gTTS (không cần key) – fallback cuối.
    """
    if not _has_gtts:
        raise RuntimeError("gTTS not available")
    fp = io.BytesIO()
    gTTS(text=text, lang=lang or "vi", slow=False).write_to_fp(fp)
    fp.seek(0)
    return fp.read()

# -------- Routes --------
@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "cache": str(CACHE_DIR),
        "providers": {
            "openai": bool(_openai_client),
            "google": bool(_google_tts_client),
            "gemini_key_loaded": _gemini_available,
            "gtts": _has_gtts,
        }
    })

@app.post("/tts")
def api_tts_post():
    """
    JSON body:
    {
      "text": "Xin chào RaidenX8!",
      "lang": "vi" | "vi-VN" | "en-US",
      "voice": "female" | "alloy" | google_voice_name,
      "provider": "auto" | "openai" | "google" | "gtts"
    }
    -> trả về audio/mpeg
    """
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("text") or "").strip()
    provider = (data.get("provider") or "auto").lower()
    lang = (data.get("lang") or "vi").strip()
    voice = (data.get("voice") or "").strip()

    if not text:
        return jsonify({"ok": False, "error": "text is required"}), 400

    # Chuẩn hoá tham số
    # Mapping nhanh cho Google
    if lang == "vi": lang_google = "vi-VN"
    else: lang_google = lang

    if provider == "auto":
        # Ưu tiên OpenAI -> Google -> gTTS
        order = []
        if _openai_client:     order.append("openai")
        if _google_tts_client: order.append("google")
        if _has_gtts:          order.append("gtts")
        if not order:
            return jsonify({"ok": False, "error": "No TTS provider available"}), 503
    else:
        order = [provider]

    # Cache
    cache_path = _cache_key(text, lang, voice or "auto", "|".join(order))
    if cache_path.exists():
        return _send_mp3(cache_path)

    # Thực thi
    last_error = None
    for p in order:
        try:
            if p == "openai":
                v = voice or "alloy"  # alloy là giọng nữ-trung tính tốt
                audio = tts_openai(text, lang=lang, voice=v)
            elif p == "google":
                v = voice or "vi-VN-Standard-A"
                audio = tts_google(text, lang=lang_google, voice=v)
            elif p == "gtts":
                audio = tts_gtts(text, lang="vi" if lang.startswith("vi") else "en")
            else:
                raise RuntimeError(f"Unknown provider: {p}")

            with open(cache_path, "wb") as f:
                f.write(audio)
            return _send_mp3(cache_path)

        except Exception as e:
            last_error = str(e)
            # thử provider tiếp theo
            continue

    return jsonify({"ok": False, "error": last_error or "TTS failed"}), 500

@app.get("/tts")
def api_tts_get():
    # Hỗ trợ query string nhanh: /tts?text=...&lang=vi&provider=auto
    text = (request.args.get("text") or "").strip()
    lang = (request.args.get("lang") or "vi").strip()
    voice = (request.args.get("voice") or "").strip()
    provider = (request.args.get("provider") or "auto").lower()
    return app.test_client().post(
        "/tts",
        data=json.dumps({"text": text, "lang": lang, "voice": voice, "provider": provider}),
        content_type="application/json"
    )

# (Tuỳ chọn) Ping cho Render khỏi sleep
@app.get("/")
def root():
    return _ok()

if __name__ == "__main__":
    # Local run (Render dùng gunicorn theo render.yaml)
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
