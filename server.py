
import os
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import requests

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-preview-05-20")

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

def simple_rules(user_text: str) -> str:
    t = user_text.lower()
    if "giá btc" in t or "btc" in t:
        try:
            r = requests.get("https://api.coingecko.com/api/v3/simple/price", params={"ids":"bitcoin","vs_currencies":"usd"} , timeout=8)
            data = r.json()
            usd = data.get("bitcoin",{}).get("usd")
            if usd:
                return f"BTC hiện tại ≈ ${usd:,}."
        except Exception as e:
            return f"Lỗi lấy giá BTC: {e}"
        return "Chưa đọc được giá BTC."
    if "thời tiết" in t:
        return "Demo thời tiết: Huế có mây nhẹ, 27–30°C."
    if "bật đọc truyện" in t:
        return "Đã bật chế độ đọc truyện demo (giọng: vi_VN)."
    return ""

def gemini_answer(prompt: str) -> str:
    if not GEMINI_KEY:
        return "Lỗi Gemini: thiếu GEMINI_API_KEY."
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_KEY)
        model = genai.GenerativeModel(MODEL_NAME)
        resp = model.generate_content(prompt)
        text = getattr(resp, "text", None) or (resp.candidates[0].content.parts[0].text if getattr(resp,"candidates",None) else "")
        return text.strip() if text else "Xin lỗi, Gemini không trả về nội dung."
    except Exception as e:
        return f"Lỗi gọi Gemini: {e}"

def answer(user_text: str) -> str:
    rule = simple_rules(user_text)
    if rule:
        return rule
    return gemini_answer(user_text)

@app.route("/health")
def health():
    return jsonify({"ok": True, "provider": ("gemini" if GEMINI_KEY else "none"), "model": MODEL_NAME})

@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(silent=True) or {}
    msg = str(data.get("message","")).strip()
    if not msg:
        return jsonify({"error":"missing message"}), 400
    return jsonify({"answer": answer(msg)})

@socketio.on("connect")
def on_connect():
    emit("bot", {"message": "Kết nối WS ok!"})

@socketio.on("chat")
def on_chat(data):
    try:
        msg = str(data.get("message",""))
    except Exception:
        msg = str(data)
    reply = answer(msg)
    emit("bot", {"message": reply})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    socketio.run(app, host="0.0.0.0", port=port)
