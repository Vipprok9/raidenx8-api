# server.py — RaidenX8 API v6.6 (Socket.IO + Gemini + Telegram + Optional TTS)
# Start: gunicorn -k eventlet -w 1 -b 0.0.0.0:$PORT server:app
import os, base64, requests, json
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import google.generativeai as genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")          # optional for TTS
GOOGLE_TTS_JSON = os.getenv("GOOGLE_TTS_JSON")        # optional service account JSON (base64 or plain)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_SECRET = os.getenv("TELEGRAM_SECRET", "RAIDENX_SECRET_123")

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(GEMINI_MODEL)

@app.get("/health")
def health(): return "ok", 200

@socketio.on("connect")
def on_connect(): emit("chat", "RaidenX8 đã kết nối. Hỏi mình bất cứ điều gì!")

def ai_reply(user_text: str) -> str:
    prompt = f"Bạn là Avatar AI của RaidenX8. Trả lời ngắn gọn, thân thiện, tiếng Việt. User: {user_text}"
    try:
        r = model.generate_content(prompt)
        return (r.text or '').strip() or "Mình đang suy nghĩ…"
    except Exception as e:
        return f"Lỗi tạm thời: {e}"

@socketio.on("chat")
def on_chat(msg):
    reply = ai_reply(str(msg))
    emit("chat", reply)

# ------- Optional TTS endpoint (auto-detect provider) -------
@app.post("/tts")
def tts():
    data = request.get_json(force=True)
    text = (data.get("text") or "")[:1000]
    lang = (data.get("voice") or "vi-VN")
    # Try OpenAI first if available
    if OPENAI_API_KEY:
        try:
            # Use OpenAI TTS (voice alloy)
            url = "https://api.openai.com/v1/audio/speech"
            headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
            payload = {"model": "gpt-4o-mini-tts", "voice": "alloy", "input": text}
            r = requests.post(url, headers=headers, json=payload)
            r.raise_for_status()
            audio_b = base64.b64encode(r.content).decode("ascii")
            return jsonify({"provider":"openai","audio_base64":audio_b})
        except Exception as e:
            pass
    # Try Google Cloud TTS if creds provided
    if GOOGLE_TTS_JSON:
        try:
            # write credentials to tmp file
            try:
                content = base64.b64decode(GOOGLE_TTS_JSON).decode("utf-8")
            except Exception:
                content = GOOGLE_TTS_JSON
            cred_path = "/tmp/google_tts.json"
            with open(cred_path, "w") as f: f.write(content)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path
            from google.cloud import texttospeech
            client = texttospeech.TextToSpeechClient()
            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice = texttospeech.VoiceSelectionParams(language_code="vi-VN", name="vi-VN-Neural2-C")
            audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
            response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
            audio_b = base64.b64encode(response.audio_content).decode("ascii")
            return jsonify({"provider":"google","audio_base64":audio_b})
        except Exception as e:
            pass
    return jsonify({"provider":"webspeech","audio_base64":None}), 200

# Telegram webhook (optional)
@app.post("/webhook")
def telegram_webhook():
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != TELEGRAM_SECRET:
        return "forbidden", 403
    update = request.get_json(silent=True) or {}
    msg = update.get("message") or {}
    if msg.get("text"):
        chat_id = str(msg["chat"]["id"])
        text = msg["text"]
        reply = ai_reply(text)
        if TELEGRAM_BOT_TOKEN:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                          json={"chat_id": chat_id, "text": reply})
        socketio.emit("chat", f"Telegram: {text}")
        socketio.emit("chat", f"AI: {reply}")
    return jsonify({"ok": True})
