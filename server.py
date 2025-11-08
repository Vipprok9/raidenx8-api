import os, time
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

MODEL = "gemini-2.5-flash-preview-05-20"
PROVIDER = "gemini"

@app.get("/health")
def health():
    return jsonify(ok=True, provider=PROVIDER, model=MODEL, ts=time.time())

@app.post("/ai/chat")
def ai_chat():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip().lower()

    # Demo rules (an toàn khi chưa gắn API key)
    if "thời tiết" in text:
        reply = "Demo: Huế hôm nay mát, có mưa rào nhẹ 🌧️."
    elif "btc" in text:
        reply = "Demo: Giá BTC hiển thị mô phỏng. Bật khóa API để lấy giá thật."
    elif not text:
        reply = "Bạn hãy nhập gì đó nhé."
    else:
        reply = f"Bạn nói: “{text}”. Đây là phản hồi demo (chưa dùng API)."

    return jsonify(ok=True, reply=reply)

@app.get("/ws/health")
def ws_health():
    # Placeholder để frontend kiểm tra kênh realtime (không dùng socket thật)
    return jsonify(ok=True, ts=time.time())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
