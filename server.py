import os, json, random, time
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import requests

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

app = Flask(__name__)
CORS(app, resources={r"/*":{"origins":"*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

@app.get("/health")
def health():
    return {"ok": True, "time": time.time()}

@app.get("/prices")
def prices():
    # simple static sample to avoid external calls on free tiers
    data = [
        {"symbol":"BTC","price":"$69,850"},
        {"symbol":"ETH","price":"$3,230"},
        {"symbol":"BNB","price":"$580"},
        {"symbol":"SOL","price":"$165"},
        {"symbol":"TON","price":"$6.1"},
        {"symbol":"USDT","price":"$1.00"},
    ]
    return jsonify({"prices": data})

def local_rules(text:str)->str:
    t=text.lower().strip()
    if "thời tiết" in t and "huế" in t:
        return "Huế hôm nay: mưa rào nhẹ, nhiệt độ 25‑29°C, ẩm 82% (tham khảo)."
    if "giá btc" in t or "bitcoin" in t:
        return "BTC đang dao động quanh $69‑70k (mang tính tham khảo)."
    return ""

@app.post("/api/chat")
def api_chat():
    data = request.get_json(force=True) or {}
    text = data.get("text","")
    model = data.get("model","")
    # Rule first
    rule = local_rules(text)
    if rule:
        return jsonify({"reply": rule})

    # Try OpenAI first
    if OPENAI_API_KEY:
        try:
            import openai  # pip: openai>=1.40
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            rsp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role":"system","content":"Bạn là trợ lý ngắn gọn, mượt, không chèn dấu sao vào câu đọc."},
                          {"role":"user","content":text}],
                temperature=0.6,
            )
            out = rsp.choices[0].message.content
            return jsonify({"reply": out})
        except Exception as e:
            print("OpenAI error:", e)

    # Try Gemini if available
    if GEMINI_API_KEY:
        try:
            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
            payload = {"contents":[{"parts":[{"text":text}]}]}
            r = requests.post(url, params={"key": GEMINI_API_KEY}, json=payload, timeout=20)
            j = r.json()
            out = j.get("candidates",[{}])[0].get("content",{}).get("parts",[{}])[0].get("text","")
            if out:
                return jsonify({"reply": out})
        except Exception as e:
            print("Gemini error:", e)

    # Fallback
    return jsonify({"reply": "Mình đã nhận: " + text})

# ---- WebSocket (Socket.IO) ----
@socketio.on("connect")
def on_connect():
    emit("ai_reply", {"text":"Đã kết nối WS realtime."})

@socketio.on("user_msg")
def on_user_msg(payload):
    text = (payload or {}).get("text","")
    # Reuse /api/chat logic quickly
    with app.test_request_context(json={"text":text}):
        resp = api_chat().get_json()
    emit("ai_reply", {"text": resp.get("reply","")})

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    socketio.run(app, host="0.0.0.0", port=port)
