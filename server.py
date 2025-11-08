import os, re, time, json
from datetime import datetime, timezone
from typing import List, Dict
import requests

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room

# === Providers ===
import google.generativeai as genai
from openai import OpenAI

# ====== ENV / CONFIG ======
PROVIDER        = os.getenv("PROVIDER", "gemini")   # gemini | openai
GEMINI_MODEL    = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash-preview-05-20")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "https://raidenx8.pages.dev")

# ====== APP ======
app = Flask(__name__)
CORS(app, origins=[FRONTEND_ORIGIN], supports_credentials=True)
socketio = SocketIO(app, cors_allowed_origins=[FRONTEND_ORIGIN], async_mode="eventlet")

# ====== UTIL ======
def clean_tts(text: str) -> str:
    text = re.sub(r"`{1,3}.*?`{1,3}", "", text, flags=re.S)   # bỏ codeblock
    text = re.sub(r"[*_~>#-]+\s?", "", text)                  # bỏ markdown bullet
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text

def split_chunks(text: str, max_len: int = 420) -> List[str]:
    sents = re.split(r"(?<=[\.\!\?…])\s+", text.strip())
    out, buf = [], ""
    for s in sents:
        if not s: 
            continue
        if len(buf) + len(s) + 1 <= max_len:
            buf = f"{buf} {s}".strip()
        else:
            if buf: out.append(buf)
            if len(s) > max_len:
                subs = re.split(r"(?<=,)\s+", s)
                tmp = ""
                for c in subs:
                    if len(tmp) + len(c) + 1 <= max_len:
                        tmp = f"{tmp} {c}".strip()
                    else:
                        if tmp: out.append(tmp)
                        tmp = c
                if tmp: out.append(tmp)
            else:
                out.append(s)
            buf = ""
    if buf: out.append(buf)
    return out

# ====== AI CORE ======
def _gemini_call(prompt: str) -> str:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return "Thiếu GEMINI_API_KEY."
    genai.configure(api_key=key)
    model = genai.GenerativeModel(GEMINI_MODEL)
    r = model.generate_content(prompt)
    return (r.text or "...").strip()

def _openai_call(prompt: str) -> str:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return "Thiếu OPENAI_API_KEY."
    client = OpenAI(api_key=key)
    r = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.6,
    )
    return r.choices[0].message.content.strip()

def ai(prompt: str) -> str:
    return _openai_call(prompt) if PROVIDER == "openai" else _gemini_call(prompt)

# ====== SIMPLE LIVE TOOLS ======
_COINGECKO = "https://api.coingecko.com/api/v3/simple/price"
_IDS = {
    "btc":"bitcoin","eth":"ethereum","bnb":"binancecoin",
    "sol":"solana","ton":"the-open-network","usdt":"tether"
}
def get_prices(symbols=("btc","eth","bnb","sol","ton","usdt")) -> Dict[str, float]:
    qs = ",".join(_IDS[s] for s in symbols if s in _IDS)
    try:
        j = requests.get(f"{_COINGECKO}?ids={qs}&vs_currencies=usd", timeout=8).json()
        return {s: j.get(_IDS[s],{}).get("usd") for s in symbols if s in _IDS}
    except Exception:
        return {}

# ====== HTTP ROUTES ======
@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "provider": PROVIDER,
        "model": GEMINI_MODEL if PROVIDER=="gemini" else OPENAI_MODEL
    })

@app.get("/time")
def now():
    return jsonify({"ok": True, "now": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")})

@app.get("/prices")
def prices():
    syms = request.args.get("symbols","btc,eth,bnb,sol,ton,usdt").lower().split(",")
    return jsonify({"ok": True, "prices": get_prices(tuple(syms)), "ts": int(time.time())})

# ==== GEN-Z STUDIO (REST) ====
@app.post("/genz/caption")
def genz_caption():
    data = request.get_json(silent=True) or {}
    topic = data.get("topic","")
    tone  = data.get("tone","genz quốc tế, chill, ngắn gọn")
    lang  = data.get("lang","vi")
    prompt = f"""
Bạn là biên tập social Gen-Z. Viết 3 phiên bản caption ngắn (<= 140 ký tự),
có hook mạnh, dùng emoji tiết chế, và 3 hashtag phù hợp.
Ngôn ngữ: {lang}. Tông: {tone}. Chủ đề: {topic}.
Chỉ trả JSON: {{"captions": [{{"text":"..." , "hashtags":["#a","#b","#c"]}}, ...]}}
"""
    try:
        text = ai(prompt)
        # nếu model không trả JSON chuẩn -> bọc lại
        return jsonify({"ok": True, "result_raw": text})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.post("/genz/rewrite")
def genz_rewrite():
    data = request.get_json(silent=True) or {}
    src  = data.get("text","")
    style = data.get("style","ngắn gọn, Gen-Z, lịch sự, dễ hiểu, loại bỏ ký hiệu thừa")
    prompt = f"Hãy viết lại nội dung sau theo phong cách {style}. Chỉ trả lời nội dung đã viết lại, không kèm giải thích.\n\n{src}"
    out = ai(prompt)
    return jsonify({"ok": True, "text": out, "tts": clean_tts(out)})

@app.post("/genz/summary")
def genz_summary():
    data = request.get_json(silent=True) or {}
    src  = data.get("text","")
    prompt = ("Tóm tắt nội dung sau dưới dạng bullet ngắn (3–5 gạch đầu dòng), "
              "bỏ markdown, dễ đọc trên điện thoại:\n\n" + src)
    out = ai(prompt)
    return jsonify({"ok": True, "text": out, "tts": clean_tts(out)})

# ====== ROUTER GIỐNG ỨNG DỤNG CHAT ======
def smart_route(text: str) -> str:
    t = text.lower().strip()
    if "giá btc" in t or ("giá" in t and "btc" in t):
        p = get_prices(("btc","eth","bnb","sol","ton","usdt"))
        if not p: return "Chưa lấy được giá (API giới hạn). Thử lại sau nhé."
        return (f"Giá nhanh (USD) • BTC {p.get('btc')} • ETH {p.get('eth')} • "
                f"BNB {p.get('bnb')} • SOL {p.get('sol')} • TON {p.get('ton')} • USDT {p.get('usdt')}.")
    if "mấy giờ" in t or "giờ utc" in t:
        return f"Bây giờ: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}."
    if "thời tiết" in t:
        return "Chưa bật nguồn thời tiết theo vị trí. Cần thì mình tích hợp Open-Meteo."
    # fallback → AI
    return ai(text)

# ====== STORY PLAYER (per-socket) ======
class StoryState:
    def __init__(self):
        self.title = "Truyện không tên"
        self.segments: List[str] = []
        self.idx = 0
        self.playing = False
        self.speed = 1.0
        self.volume = 1.0
        self.voice = "vi-VN-default"

_sessions: Dict[str, StoryState] = {}

def st_of(sid: str) -> StoryState:
    if sid not in _sessions:
        _sessions[sid] = StoryState()
    return _sessions[sid]

# ====== WEBSOCKET EVENTS ======
@socketio.on("connect")
def on_connect():
    sid = request.sid
    join_room(sid)
    emit("server_status", {"ok": True, "sid": sid, "ts": int(time.time())})

@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    leave_room(sid)
    _sessions.pop(sid, None)

@socketio.on("user_message")
def on_user_message(data):
    text = (data or {}).get("text","").strip()
    if not text:
        emit("bot_message", {"text": "Bạn thử gõ câu hỏi nhé."})
        return
    reply = smart_route(text)
    emit("bot_message", {"text": reply, "tts": clean_tts(reply)})

# ---- Gen-Z Studio qua WS ----
@socketio.on("genz_task")
def on_genz_task(data):
    """
    data = {"action":"caption|rewrite|summary", "payload":{...}}
    """
    act = (data or {}).get("action","")
    payload = (data or {}).get("payload",{}) or {}
    try:
        if act == "caption":
            topic = payload.get("topic","")
            tone  = payload.get("tone","genz quốc tế")
            lang  = payload.get("lang","vi")
            prompt = f"""
Bạn là biên tập social Gen-Z. Viết 3 caption <= 140 ký tự,
hook mạnh, emoji tiết chế, 3 hashtag. Ngôn ngữ {lang}, tông {tone}.
Chủ đề: {topic}. Trả JSON: {{"captions":[{{"text":"...","hashtags":["#a","#b","#c"]}},...]}}
"""
            out = ai(prompt)
            emit("genz_result", {"ok": True, "raw": out})
            return
        if act == "rewrite":
            text = payload.get("text","")
            style = payload.get("style","ngắn gọn, Gen-Z, lịch sự")
            out = ai(f"Viết lại đoạn sau theo phong cách {style}. Chỉ trả nội dung đã viết lại:\n\n{text}")
            emit("genz_result", {"ok": True, "text": out, "tts": clean_tts(out)})
            return
        if act == "summary":
            text = payload.get("text","")
            out = ai("Tóm tắt 3–5 bullet, bỏ markdown, dễ đọc mobile:\n\n" + text)
            emit("genz_result", {"ok": True, "text": out, "tts": clean_tts(out)})
            return
    except Exception as e:
        emit("genz_result", {"ok": False, "error": str(e)})

# ---- Story: set & control ----
@socketio.on("story_set")
def on_story_set(data):
    sid = request.sid
    st = st_of(sid)
    st.title = (data or {}).get("title") or "Truyện không tên"
    chapters = (data or {}).get("chapters")
    text = (data or {}).get("text")
    segments: List[str] = []
    if chapters and isinstance(chapters, list):
        for ch in chapters:
            segments += split_chunks(ch, max_len=420)
    elif text:
        segments = split_chunks(text, max_len=420)
    else:
        emit("bot_message", {"text":"Không có nội dung truyện.", "tts":"Không có nội dung truyện."})
        return
    st.segments, st.idx, st.playing = segments, 0, False
    emit("story_status", {
        "title": st.title, "total": len(st.segments), "idx": st.idx,
        "playing": st.playing, "speed": st.speed, "voice": st.voice, "volume": st.volume
    })
    emit("bot_message", {"text": f"Đã nạp **{st.title}** ({len(st.segments)} đoạn).",
                         "tts": clean_tts(f"Đã nạp {st.title}, {len(st.segments)} đoạn.")})

@socketio.on("story_control")
def on_story_control(data):
    sid = request.sid
    st = st_of(sid)
    action = (data or {}).get("action","").lower()
    value  = (data or {}).get("value")

    # settings
    if action in ("speed","voice","volume"):
        if action == "speed":
            try: st.speed = max(0.5, min(1.5, float(value)))
            except: pass
        elif action == "voice":
            st.voice = str(value or "vi-VN-default")
        elif action == "volume":
            try: st.volume = max(0.0, min(1.0, float(value)))
            except: pass
        emit("story_status", {"title": st.title, "total": len(st.segments), "idx": st.idx,
                              "playing": st.playing, "speed": st.speed, "voice": st.voice, "volume": st.volume})
        return

    if action == "stop":
        st.playing, st.idx = False, 0
        emit("story_status", {"title": st.title, "total": len(st.segments), "idx": st.idx,
                              "playing": st.playing, "speed": st.speed, "voice": st.voice, "volume": st.volume})
        return

    if not st.segments:
        emit("bot_message", {"text":"Chưa có truyện. Gửi `story_set` trước!", "tts":"Chưa có truyện. Gửi story set trước!"})
        return

    if action in ("play","resume"):
        st.playing = True
        emit("story_status", {"title": st.title, "total": len(st.segments), "idx": st.idx,
                              "playing": st.playing, "speed": st.speed, "voice": st.voice, "volume": st.volume})
        seg = st.segments[st.idx]
        emit("story_segment", {"idx": st.idx, "text": seg, "tts": clean_tts(seg),
                               "speed": st.speed, "voice": st.voice, "volume": st.volume})
        return

    if action == "pause":
        st.playing = False
        emit("story_status", {"title": st.title, "total": len(st.segments), "idx": st.idx,
                              "playing": st.playing, "speed": st.speed, "voice": st.voice, "volume": st.volume})
        return

    if action == "next":
        st.idx = min(len(st.segments)-1, st.idx + 1)
    if action == "prev":
        st.idx = max(0, st.idx - 1)
    if action in ("next","prev"):
        seg = st.segments[st.idx]
        emit("story_segment", {"idx": st.idx, "text": seg, "tts": clean_tts(seg),
                               "speed": st.speed, "voice": st.voice, "volume": st.volume})
        return

# ====== ENTRY for gunicorn ======
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
app = app  # for gunicorn -> server:app
