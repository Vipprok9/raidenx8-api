import os, time, threading, io, requests
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from flask_socketio import SocketIO

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY", "")
AZURE_REGION = os.getenv("AZURE_REGION", "")

app = Flask(__name__)
CORS(app, resources={r"/*":{"origins":"*"}})
socketio = SocketIO(app, cors_allowed_origins="*")

PRICES = []
SYMS = [("bitcoin","BTC"),("ethereum","ETH"),("binancecoin","BNB"),("solana","SOL"),("tether","USDT"),("toncoin","TON")]

def fetch_prices():
    global PRICES
    ids = ",".join([x[0] for x in SYMS])
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                         params={"ids":ids,"vs_currencies":"usd","include_24hr_change":"true"}, timeout=12)
        j = r.json()
        rows = []
        for cg_id, sym in SYMS:
            if cg_id in j:
                price = float(j[cg_id]["usd"]); change = float(j[cg_id].get("usd_24h_change", 0.0))
                rows.append({"symbol":sym,"price":price,"change":change})
        PRICES = rows
    except Exception as e:
        print("price fetch error:", e)

def loop():
    while True:
        fetch_prices()
        if PRICES: socketio.emit("prices", PRICES, broadcast=True)
        time.sleep(30)

@app.get("/")
def health(): return jsonify(ok=True, service="raidenx8-api v9.1")

@app.get("/prices")
def prices():
    if not PRICES: fetch_prices()
    return jsonify(PRICES)

@app.post("/notify-telegram")
def notify_telegram():
    data = request.get_json(silent=True) or {}
    chat_id = str(data.get("chatId","")).strip(); text = str(data.get("text","")).strip()
    if not TELEGRAM_BOT_TOKEN or not chat_id or not text: return jsonify(ok=False, error="missing")
    try:
        tg_url=f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        resp=requests.post(tg_url,json={"chat_id":chat_id,"text":text,"parse_mode":"HTML"},timeout=10)
        return jsonify(ok=resp.ok)
    except Exception as e:
        return jsonify(ok=False, error=str(e))

@app.post("/ai/chat")
def ai_chat():
    data = request.get_json(silent=True) or {}
    provider=(data.get("provider") or "openai").lower(); message=(data.get("message") or "")[:4000]
    if provider.startswith("openai") and OPENAI_API_KEY:
        try:
            from openai import OpenAI
            client=OpenAI(api_key=OPENAI_API_KEY)
            r=client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user","content":message}])
            return jsonify(reply=r.choices[0].message.content)
        except Exception as e: return jsonify(reply=f"(OpenAI lỗi) {e}")
    if provider.startswith("gemini") and GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            model=genai.GenerativeModel("gemini-1.5-pro"); r=model.generate_content(message)
            return jsonify(reply=r.text)
        except Exception as e: return jsonify(reply=f"(Gemini lỗi) {e}")
    return jsonify(reply=f"(demo) Bạn hỏi: {message}")

@app.post("/api/tts")
def api_tts():
    data = request.get_json(force=True)
    text=(data.get("text") or "").strip(); provider=(data.get("provider") or "google").lower()
    voice=(data.get("voice") or "").strip(); lang=(data.get("lang") or "vi-VN").strip()
    if not text: return jsonify(ok=False, error="empty text"), 400

    if provider=="openai" and OPENAI_API_KEY:
        try:
            from openai import OpenAI
            client=OpenAI(api_key=OPENAI_API_KEY)
            speech=client.audio.speech.with_streaming_response.create(model="gpt-4o-mini-tts", voice=voice or "alloy", input=text)
            buf=io.BytesIO(speech.read()); buf.seek(0)
            return send_file(buf, mimetype="audio/mpeg", download_name="speech.mp3")
        except Exception as e: return jsonify(ok=False, error=f"openai: {e}"), 500

    if provider=="google":
        if voice.lower()=="vi-vn-namminhneural": voice="vi-VN-Neural2-D"
        try:
            from google.cloud import texttospeech
            client=texttospeech.TextToSpeechClient()
            synthesis_input=texttospeech.SynthesisInput(text=text)
            voice_sel=texttospeech.VoiceSelectionParams(language_code=lang, name=voice or "vi-VN-Neural2-D")
            audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3, speaking_rate=1.0, pitch=0.0)
            audio=client.synthesize_speech(input=synthesis_input, voice=voice_sel, audio_config=audio_config)
            return send_file(io.BytesIO(audio.audio_content), mimetype="audio/mpeg", download_name="speech.mp3")
        except Exception as e: return jsonify(ok=False, error=f"google: {e}"), 500

    if provider=="azure":
        if not (AZURE_SPEECH_KEY and AZURE_REGION): return jsonify(ok=False, error="missing AZURE_*"), 400
        try:
            import azure.cognitiveservices.speech as speechsdk
            speech_config=speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_REGION)
            speech_config.speech_synthesis_voice_name = voice or "vi-VN-NamMinhNeural"
            synthesizer=speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
            result=synthesizer.speak_text_async(text).get()
            if result.reason==speechsdk.ResultReason.SynthesizingAudioCompleted:
                return send_file(io.BytesIO(result.audio_data), mimetype="audio/wav", download_name="speech.wav")
            return jsonify(ok=False, error=str(result.reason)), 500
        except Exception as e: return jsonify(ok=False, error=f"azure: {e}"), 500

    return jsonify(ok=False, error="unknown provider"), 400

def main():
    t=threading.Thread(target=loop, daemon=True); t.start()
    from flask_socketio import SocketIO
    port=int(os.getenv("PORT","5000"))
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)

if __name__=="__main__":
    main()
