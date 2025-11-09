# ==== MUST BE FIRST (Socket.IO + Gunicorn) ====
import eventlet
eventlet.monkey_patch()
# ==============================================

import os, time, re, requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import google.generativeai as genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEFAULT_MODEL  = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-preview-0520")

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet", ping_timeout=25, ping_interval=20)

SYS_STYLE = (
  "Bạn là trợ lý nói chuyện tự nhiên bằng tiếng Việt, trả lời ngắn gọn, "
  "không dùng markdown (không **đậm**, không bullet *), không chèn ngoặc vuông. "
  "Viết câu mạch lạc như hội thoại đời thường."
)

def strip_markdown(t: str) -> str:
  if not t: return t
  t = re.sub(r'\*\*(.*?)\*\*', r'\1', t)
  t = re.sub(r'__(.*?)__', r'\1', t)
  t = re.sub(r'`{1,3}([^`]+)`{1,3}', r'\1', t)
  t = re.sub(r'^\s*[\*\-\+]\s+', '', t, flags=re.MULTILINE)
  t = re.sub(r'\s+\n', '\n', t)
  t = re.sub(r'\n{3,}', '\n\n', t)
  return t.strip()

def call_gemini_25_rest(model: str, msg: str) -> str:
  url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
  payload = {
    "system_instruction": {"role": "system", "parts": [{"text": SYS_STYLE}]},
    "contents": [{"role": "user", "parts": [{"text": msg}]}],
    "generationConfig": {"responseMimeType": "text/plain"}
  }
  r = requests.post(url, json=payload, timeout=60)
  r.raise_for_status()
  data = r.json()
  text = data["candidates"][0]["content"]["parts"][0].get("text", "")
  return strip_markdown(text)

def call_gemini_sdk(model: str, msg: str) -> str:
  genai.configure(api_key=GEMINI_API_KEY)
  m = genai.GenerativeModel(
    model,
    system_instruction=SYS_STYLE,
    generation_config={"response_mime_type":"text/plain"},
  )
  res = m.generate_content(msg)
  text = getattr(res, "text", "") or ""
  return strip_markdown(text)

def smart_call(model: str, msg: str) -> str:
  mdl = (model or DEFAULT_MODEL).strip()
  if not GEMINI_API_KEY:
    return "Xin chào! Đây là chế độ demo. Thêm GEMINI_API_KEY trên server để bật trả lời thời gian thực."
  m = mdl.lower()
  try:
    if "2.5" in m or "preview-0520" in m:
      return call_gemini_25_rest(mdl, msg)
    else:
      return call_gemini_sdk(mdl, msg)
  except Exception as e:
    return f"Lỗi: {e}"

@app.get("/health")
def health():
  return jsonify({"ok": True, "model": DEFAULT_MODEL, "has_key": bool(GEMINI_API_KEY)})

@app.post("/ai/chat")
def ai_chat():
  data = request.get_json(force=True, silent=True) or {}
  msg = (data.get("message") or "").strip()
  mdl = (data.get("model") or DEFAULT_MODEL).strip()
  if not msg:
    return jsonify({"reply": ""})
  text = smart_call(mdl, msg)
  return jsonify({"reply": text, "model": mdl})

@socketio.on("connect")
def on_connect():
  emit("bot_message", "WS connected 🎧")

@socketio.on("chat")
def on_chat(data):
  msg = (data or {}).get("message", "").strip()
  mdl = (data or {}).get("model", DEFAULT_MODEL)
  emit("bot_typing")
  time.sleep(0.12)
  if not msg:
    emit("bot_message", "")
    return
  text = smart_call(mdl, msg)
  emit("bot_message", text)

if __name__ == "__main__":
  port = int(os.getenv("PORT", "8000"))
  socketio.run(app, host="0.0.0.0", port=port)
