import os, io, hashlib, time
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS

# ====== Config ======
CACHE_DIR = os.getenv("CACHE_DIR", "/tmp/tts_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

USE_GOOGLE = False
GOOGLE_ERR = None
try:
    # Chỉ dùng Google Cloud TTS nếu đã set GOOGLE_APPLICATION_CREDENTIALS
    # (file JSON service account) và lib import OK
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        from google.cloud import texttospeech as gtts_google
        USE_GOOGLE = True
except Exception as e:
    GOOGLE_ERR = str(e)
    USE_GOOGLE = False

# Fallback miễn phí
try:
    from gtts import gTTS
except Exception as e:
    gTTS = None

app = Flask(__name__)
CORS(app)


# ====== Helpers ======
def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _voice_to_lang(voice: str) -> str:
    """
    'vi-VN-Wavenet-D' -> 'vi-VN'
    'en-US-Neural2-F' -> 'en-US'
    'vi' -> 'vi'
    """
    if not voice:
        return "vi-VN"
    if "-" in voice:
        parts = voice.split("-")
        if len(parts) >= 2:
            return f"{parts[0]}-{parts[1]}"
    return voice


def synth_google(text: str, voice_name: str) -> bytes:
    """Google Cloud Text-to-Speech -> MP3 bytes"""
    client = gtts_google.TextToSpeechClient()

    # Voice + language
    language_code = _voice_to_lang(voice_name)
    voice_params = gtts_google.VoiceSelectionParams(
        language_code=language_code,
        name=voice_name or "vi-VN-Wavenet-D",
    )

    audio_config = gtts_google.AudioConfig(
        audio_encoding=gtts_google.AudioEncoding.MP3,
        speaking_rate=1.0,
        pitch=0.0,
    )

    synthesis_input = gtts_google.SynthesisInput(text=text)
    resp = client.synthesize_speech(
        input=synthesis_input, voice=voice_params, audio_config=audio_config
    )
    return resp.audio_content


def synth_gtts(text: str, voice_name: str) -> bytes:
    """gTTS (miễn phí) -> MP3 bytes"""
    if gTTS is None:
        raise RuntimeError("gTTS library not available.")
    lang = _voice_to_lang(voice_name)
    # gTTS dùng 'vi', 'en'… nên rút về 2 ký tự đầu
    lang2 = lang.split("-")[0]
    mp3_bytes_io = io.BytesIO()
    gTTS(text=text, lang=lang2).write_to_fp(mp3_bytes_io)
    mp3_bytes_io.seek(0)
    return mp3_bytes_io.read()


def synth_tts(text: str, voice: str) -> bytes:
    if USE_GOOGLE:
        try:
            return synth_google(text, voice)
        except Exception as e:
            # fallback sang gTTS nếu Google lỗi
            if gTTS is None:
                raise
            return synth_gtts(text, voice)
    else:
        return synth_gtts(text, voice)


def cache_path(text: str, voice: str) -> str:
    key = _sha1(f"{voice}::{text}")
    return os.path.join(CACHE_DIR, f"{key}.mp3")


# ====== Routes ======
@app.get("/health")
def health():
    return jsonify(
        ok=True,
        google_ready=USE_GOOGLE,
        google_error=GOOGLE_ERR,
        cache_dir=CACHE_DIR,
    )


@app.get("/api/tts")
def api_tts():
    text = request.args.get("text", "").strip()
    voice = request.args.get("voice", "vi-VN-Wavenet-D")
    if not text:
        return jsonify(ok=False, error="Missing text"), 400

    cp = cache_path(text, voice)
    if os.path.exists(cp):
        # Cache hit
        return send_file(cp, mimetype="audio/mpeg", as_attachment=False)

    try:
        audio = synth_tts(text, voice)
        with open(cp, "wb") as f:
            f.write(audio)
        return send_file(io.BytesIO(audio), mimetype="audio/mpeg", as_attachment=False)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500


# Trang chủ đơn giản (tuỳ ý)
@app.get("/")
def root():
    return "RaidenX8 TTS API is running. Use /api/tts?text=...&voice=vi-VN-Wavenet-D"

# ====== Local run ======
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, threaded=True)
