import os
import json
import eventlet
eventlet.monkey_patch()

from flask import Flask, jsonify
from flask_cors import CORS
from flask_sock import Sock
from openai import OpenAI

# ===== CẤU HÌNH CƠ BẢN =====
app = Flask(__name__)
CORS(app)
sock = Sock(app)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

client = None
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)


@app.route("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "service": "rx8-backend-ws-v1.1",
            "openai": bool(OPENAI_API_KEY),
        }
    )


# ===== WEBSOCKET CHO RX8 WOW-TV v12.5 =====
@sock.route("/ws/rx8")
def rx8_ws(ws):
    """WebSocket endpoint cho frontend RX8 WOW-TV v12.5.

    Giao thức:
    - Client gửi:
        { "type": "hello", "client": "rx8-wow-tv-v12.5" }
        { "type": "chat",  "text": "..." }

    - Server gửi:
        { "type": "chat",   "text": "..." }        # tin nhắn đơn
        { "type": "typing" }                      # bật bong bóng typing
        { "type": "chunk",  "text": "..." }       # stream token-by-token
        { "type": "done" }                        # tắt typing
    """


    while True:
        msg = ws.receive()
        if msg is None:
            break

        try:
            data = json.loads(msg)
        except Exception:
            # Nếu không phải JSON thì bỏ qua
            continue

        msg_type = data.get("type")

        if msg_type == "hello":
            ws.send(
                json.dumps(
                    {
                        "type": "chat",
                        "text": "RX8 realtime backend v1.1 (eventlet) đã kết nối ✅",
                    }
                )
            )
            continue

        if msg_type != "chat":
            continue

        user_text = (data.get("text") or "").strip()
        if not user_text:
            continue

        # Nếu chưa cấu hình OPENAI_API_KEY -> trả lời demo ngắn
        if not client:
            ws.send(json.dumps({"type": "typing"}))
            ws.send(
                json.dumps(
                    {
                        "type": "chat",
                        "text": "⚠️ Backend RX8 đã chạy nhưng chưa có OPENAI_API_KEY. "
                        "Hãy set biến môi trường OPENAI_API_KEY trên Render để bật AI.",
                    }
                )
            )
            ws.send(json.dumps({"type": "done"}))
            continue

        # Bật trạng thái typing trên frontend
        ws.send(json.dumps({"type": "typing"}))

        try:
            # Gọi OpenAI dạng stream
            stream = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Bạn là RX8 – trợ lý AI phong cách Web3 + tu tiên, "
                            "trả lời ngắn gọn, rõ ràng, dùng tiếng Việt, "
                            "vừa chill vừa ngầu, phù hợp banner trình chiếu sự kiện."
                        ),
                    },
                    {"role": "user", "content": user_text},
                ],
                stream=True,
            )

            for chunk in stream:
                choice = chunk.choices[0]
                delta = getattr(choice, "delta", None)
                if not delta or not getattr(delta, "content", None):
                    continue
                text_piece = delta.content
                ws.send(json.dumps({"type": "chunk", "text": text_piece}))

            # Thông báo hoàn tất
            ws.send(json.dumps({"type": "done"}))

        except Exception as e:
            # Nếu có lỗi, báo ngắn gọn và không làm rớt kết nối
            ws.send(
                json.dumps(
                    {
                        "type": "chat",
                        "text": "⚠️ Lỗi backend RX8: {}"
                        .format(str(e)[:200]),
                    }
                )
            )
            ws.send(json.dumps({"type": "done"}))


if __name__ == "__main__":
    # Chạy local để test, Render sẽ dùng gunicorn trong Procfile
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
