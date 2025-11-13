import os
import json

import eventlet
eventlet.monkey_patch()  # Quan trọng cho eventlet + WebSocket

from flask import Flask, jsonify
from flask_cors import CORS
from flask_sock import Sock
from openai import OpenAI
import requests

# ================== ENV & CLIENTS ==================

app = Flask(__name__)
CORS(app)
sock = Sock(app)

# Khóa OpenAI (nếu sau này anh dùng)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Khóa Gemini (hiện tại anh đang dùng)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Tên model Gemini (anh có thể set GEMINI_MODEL trên Render,
# ví dụ: gemini-2.0-flash-exp, gemini-2.5-pro-preview-0519, v.v.)
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")

openai_client = None
if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)


# ================== SYSTEM PROMPT: ƯU TIÊN CHÍNH XÁC ==================

SYSTEM_PROMPT = (
    "Bạn là RX8 – AI dựa trên tư duy của Gemini 2.5.\n"
    "Mục tiêu số 1: TRẢ LỜI CHÍNH XÁC.\n"
    "Quy tắc:\n"
    "1) Trả lời đúng trọng tâm câu hỏi, ngắn gọn, dễ hiểu.\n"
    "2) Không bịa. Khi không chắc, hãy nói rõ: 'Mình không chắc' hoặc giải thích giới hạn.\n"
    "3) Ưu tiên sự thật, dữ liệu và lập luận logic.\n"
    "4) Có thể thêm một chút phong cách Web3 / tu tiên cho vui, "
    "nhưng không được làm mờ nội dung chính.\n"
    "5) Nếu câu hỏi liên quan đến dữ liệu realtime (giá coin, thời tiết, sự kiện đang diễn ra), "
    "hãy nói rõ rằng bạn không có dữ liệu trực tiếp, rồi trả lời theo kiến thức nền.\n"
)


def current_provider() -> str:
    """Xác định đang dùng provider nào."""
    if OPENAI_API_KEY:
        return "openai"
    if GEMINI_API_KEY:
        return "gemini"
    return "none"


@app.route("/health")
def health():
    """Endpoint check server còn sống + provider đang dùng."""
    return jsonify(
        {
            "status": "ok",
            "service": "rx8-backend-gemini-v1",
            "provider": current_provider(),
            "has_openai": bool(OPENAI_API_KEY),
            "has_gemini": bool(GEMINI_API_KEY),
            "gemini_model": GEMINI_MODEL,
        }
    )


# ================== HÀM GỌI GEMINI & OPENAI ==================


def call_gemini(user_text: str) -> str:
    """
    Gọi Google Gemini (generateContent).
    Trả về full text 1 lần, tí nữa mình tự stream ra WebSocket.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY chưa được cấu hình trên Render."
        )

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": SYSTEM_PROMPT},
                    {"text": user_text},
                ]
            }
        ]
    }

    resp = requests.post(url, json=payload, timeout=40)
    resp.raise_for_status()
    data = resp.json()

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        raise RuntimeError(f"Không đọc được phản hồi Gemini: {data}")

    return text.strip()


def stream_openai(ws, user_text: str):
    """
    Gọi OpenAI (nếu có key) và stream token-by-token ra WebSocket.
    """
    if not openai_client:
        raise RuntimeError("OPENAI_API_KEY chưa được cấu hình trên Render.")

    stream = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
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


def stream_text_manual(ws, full_text: str):
    """
    Stream thủ công 1 đoạn text dài ra WebSocket theo từng ký tự.
    Dùng cho Gemini (vì mình gọi generateContent 1 lần).
    """
    for ch in full_text:
        ws.send(json.dumps({"type": "chunk", "text": ch}))


# ================== WEBSOCKET CHO RX8 ==================


@sock.route("/ws/rx8")
def rx8_ws(ws):
    """
    WebSocket endpoint cho frontend RX8 WOW-TV v12.6 Orbit.

    Client gửi:
        { "type": "hello", "client": "rx8-wow-tv-v12.6" }
        { "type": "chat",  "text": "..." }

    Server gửi:
        { "type": "chat",   "text": "..." }
        { "type": "typing" }
        { "type": "chunk",  "text": "..." }
        { "type": "done" }
    """

    while True:
        msg = ws.receive()
        if msg is None:
            # Client đóng kết nối
            break

        try:
            data = json.loads(msg)
        except Exception:
            # Không phải JSON thì bỏ qua
            continue

        msg_type = data.get("type")

        # Lần connect đầu tiên
        if msg_type == "hello":
            ws.send(
                json.dumps(
                    {
                        "type": "chat",
                        "text": (
                            "RX8 realtime backend Gemini v1 đã kết nối ✅ "
                            f"(provider: {current_provider()})."
                        ),
                    }
                )
            )
            continue

        if msg_type != "chat":
            continue

        user_text = (data.get("text") or "").strip()
        if not user_text:
            continue

        provider = current_provider()
        if provider == "none":
            # Không có cả OpenAI lẫn Gemini
            ws.send(json.dumps({"type": "typing"}))
            ws.send(
                json.dumps(
                    {
                        "type": "chat",
                        "text": (
                            "⚠️ Backend RX8 chưa có GEMINI_API_KEY hoặc OPENAI_API_KEY.\n"
                            "Hãy set ít nhất một biến môi trường trên Render để bật AI."
                        ),
                    }
                )
            )
            ws.send(json.dumps({"type": "done"}))
            continue

        # Bật trạng thái typing
        ws.send(json.dumps({"type": "typing"}))

        try:
            if provider == "openai":
                # Stream trực tiếp từ OpenAI
                stream_openai(ws, user_text)
            else:
                # Dùng Gemini: gọi 1 phát rồi stream thủ công cho mượt
                full_text = call_gemini(user_text)
                stream_text_manual(ws, full_text)

            # Kết thúc
            ws.send(json.dumps({"type": "done"}))

        except Exception as e:
            # Báo lỗi ngắn gọn, không làm rơi kết nối
            ws.send(
                json.dumps(
                    {
                        "type": "chat",
                        "text": f"⚠️ Lỗi backend RX8 ({provider}): {str(e)[:200]}",
                    }
                )
            )
            ws.send(json.dumps({"type": "done"}))


# ================== CHẠY LOCAL (DEV) ==================

if __name__ == "__main__":
    # Chạy local để test; Render sẽ dùng gunicorn trong Procfile
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
