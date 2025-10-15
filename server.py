# --- TTS + Voice Story ---
from flask import Flask, request, jsonify, send_file
from google.cloud import texttospeech as gtts
from bs4 import BeautifulSoup
import re, io, time, requests

TTS_DEFAULT_VOICE = "vi-VN-Neural2-C"     # nữ Việt êm, to, rõ
TTS_DEFAULT_RATE  = 1.0                   # tốc độ
TTS_DEFAULT_PITCH = -1.0                  # trầm nhẹ, đỡ chói

def _html_to_text(html):
    soup = BeautifulSoup(html, "html.parser")
    # Xóa script/style
    for tag in soup(["script", "style", "noscript"]): tag.decompose()
    text = soup.get_text("\n")
    text = re.sub(r"\n{2,}", "\n", text).strip()
    return text

def _fetch_story_text(title_or_url: str) -> str:
    # Nếu là URL: tải và bóc nội dung
    if title_or_url.startswith("http"):
        r = requests.get(title_or_url, timeout=12)
        r.raise_for_status()
        raw = _html_to_text(r.text)
        # Heuristic: chỉ giữ đoạn dài (loại menu/nhận xét)
        parts = [p.strip() for p in raw.split("\n") if len(p.strip()) > 40]
        return "\n".join(parts[:1200])  # giới hạn an toàn ~100k ký tự
    # Nếu là tên: tạo prompt mở đầu (demo, sau nâng cấp sẽ crawl theo tên)
    return f"Truyện: {title_or_url}. Mở đầu: {title_or_url} — đây là phần giới thiệu ngắn để đọc thử. Bạn có thể dán URL chương để đọc toàn văn."

def synth_gcloud(text, voice=TTS_DEFAULT_VOICE, rate=TTS_DEFAULT_RATE, pitch=TTS_DEFAULT_PITCH):
    client = gtts.TextToSpeechClient()
    synthesis_input = gtts.SynthesisInput(text=text)
    voice_sel = gtts.VoiceSelectionParams(
        language_code="vi-VN",
        name=voice
    )
    audio_config = gtts.AudioConfig(
        audio_encoding=gtts.AudioEncoding.MP3,
        speaking_rate=rate,
        pitch=pitch,
        volume_gain_db=6.0  # BOOST to hơn Web Speech
    )
    resp = client.synthesize_speech(
        input=synthesis_input, voice=voice_sel, audio_config=audio_config
    )
    return resp.audio_content

@app.post("/api/tts")
def api_tts():
    """
    Body: { "text": "...", "voice": "vi-VN-Neural2-C", "rate": 1.0, "pitch": -1.0 }
    Trả về: audio/mp3
    """
    data = request.get_json(force=True)
    text  = data.get("text","")[:100000]
    voice = data.get("voice", TTS_DEFAULT_VOICE)
    rate  = float(data.get("rate", TTS_DEFAULT_RATE))
    pitch = float(data.get("pitch", TTS_DEFAULT_PITCH))
    if not text.strip():
        return jsonify({"error":"empty_text"}), 400

    mp3 = synth_gcloud(text, voice, rate, pitch)
    return send_file(io.BytesIO(mp3), mimetype="audio/mpeg",
                     as_attachment=False,
                     download_name=f"tts_{int(time.time())}.mp3")

@app.post("/voice/read")
def voice_read():
    """
    Body: { "query":"<tên truyện hoặc URL>", "provider":"gemini" }
    → Lấy nội dung (nếu URL) + tổng hợp TTS → trả MP3
    """
    data = request.get_json(force=True)
    q = (data.get("query") or "").strip()
    if not q:
        return jsonify({"error":"empty_query"}), 400

    text = _fetch_story_text(q)[:95000]
    mp3 = synth_gcloud(text)
    return send_file(io.BytesIO(mp3), mimetype="audio/mpeg",
                     as_attachment=False,
                     download_name=f"voice_story_{int(time.time())}.mp3")
