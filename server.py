# server.py — AI Singing backend proxy (Flask)
# Routes:
#  POST /ai/sing  {lyrics, style} → returns {"audio_url": "<mp3>"}
# Environment:
#  PROVIDER (none|goapi|custom), PROVIDER_URL, PROVIDER_KEY
from flask import Flask, request, jsonify
from flask_cors import CORS
import os, requests

app = Flask(__name__)
CORS(app)

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/ai/sing")
def ai_sing():
    data = request.get_json(force=True)
    lyrics = data.get("lyrics","").strip()
    style = data.get("style","edm_remix_bass")
    if not lyrics:
        return jsonify({"error":"missing lyrics"}), 400

    provider = os.getenv("PROVIDER","none").lower()
    if provider == "goapi":
        # Example schema for a third-party Suno wrapper (adjust per provider docs)
        url = os.getenv("PROVIDER_URL", "https://api.goapi.ai/suno/create")
        key = os.getenv("PROVIDER_KEY","")
        payload = {
            "prompt": lyrics,
            "style": style,
            "title": "AI Song",
        }
        headers = {"Authorization": f"Bearer {key}","Content-Type":"application/json"}
        r = requests.post(url, json=payload, headers=headers, timeout=120)
        try:
            j = r.json()
        except Exception:
            return jsonify({"error":"provider_bad_json","text":r.text}), 502
        audio_url = j.get("audio_url") or j.get("data",{}).get("audio_url")
        if not audio_url:
            return jsonify({"error":"provider_no_audio_url","resp":j}), 502
        return jsonify({"audio_url": audio_url, "provider":"goapi"})
    elif provider == "custom":
        # Generic passthrough to your own webhook. It must return {"audio_url": "..."}.
        url = os.getenv("PROVIDER_URL")
        key = os.getenv("PROVIDER_KEY","")
        if not url:
            return jsonify({"error":"missing PROVIDER_URL"}), 500
        headers = {"Authorization": f"Bearer {key}","Content-Type":"application/json"} if key else {"Content-Type":"application/json"}
        r = requests.post(url, json={"lyrics":lyrics,"style":style}, headers=headers, timeout=120)
        try:
            j = r.json()
        except Exception:
            return jsonify({"error":"custom_bad_json","text":r.text}), 502
        if "audio_url" not in j:
            return jsonify({"error":"custom_no_audio_url","resp":j}), 502
        return jsonify({"audio_url": j["audio_url"], "provider":"custom"})
    else:
        # Demo mode
        demo_audio = "https://filesamples.com/samples/audio/mp3/sample3.mp3"
        return jsonify({"audio_url": demo_audio, "provider":"demo"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
