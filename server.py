import os, json, time, hashlib, asyncio
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse
import httpx

# ====== LLM (Gemini hoặc OpenAI) ======
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

use_gemini = bool(GEMINI_API_KEY)
if use_gemini:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel("gemini-1.5-flash")

use_openai = (not use_gemini) and bool(OPENAI_API_KEY)
if use_openai:
    from openai import OpenAI
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

# ====== FastAPI ======
app = FastAPI(title="RaidenX8 API", version="v1")
allow_origins = os.getenv("CORS_ALLOW_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allow_origins.split(",")] if allow_origins else ["*"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

@app.get("/healthz")
async def healthz(): return {"ok": True}

# ----------------------------------------------------------
# ============== WebSocket Chat AI 2 chiều =================
# Frontend gửi: {"type":"user","text":"..."}
# Server stream: {"type":"chunk","text":"..."} ... {"type":"done"}
# ----------------------------------------------------------
@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except Exception:
                data = {"type": "user", "text": raw}
            text = (data.get("text") or "").strip()
            if not text:
                await websocket.send_json({"type":"error","text":"Empty message"})
                continue

            if use_gemini:
                try:
                    stream = gemini_model.generate_content(text, stream=True)
                    for chunk in stream:
                        if hasattr(chunk, "text") and chunk.text:
                            await websocket.send_json({"type":"chunk","text":chunk.text})
                    await websocket.send_json({"type":"done"})
                except Exception as e:
                    await websocket.send_json({"type":"error","text":f"Gemini error: {e}"})
            elif use_openai:
                try:
                    resp = openai_client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role":"user","content":text}],
                        stream=True,
                    )
                    for part in resp:
                        delta = part.choices[0].delta or {}
                        if "content" in delta and delta.content:
                            await websocket.send_json({"type":"chunk","text":delta.content})
                    await websocket.send_json({"type":"done"})
                except Exception as e:
                    await websocket.send_json({"type":"error","text":f"OpenAI error: {e}"})
            else:
                await websocket.send_json({"type":"chunk","text":f"[Echo] {text}"})
                await websocket.send_json({"type":"done"})
    except WebSocketDisconnect:
        return

# ----------------------------------------------------------
# ============== Ticker Realtime qua WebSocket =============
# /ws/ticker: đẩy snapshot + cập nhật định kỳ (FETCH_INTERVAL)
# Client có thể gửi { "type":"set", "symbols":["BTC","ETH","SOL"] }
# ----------------------------------------------------------
FETCH_INTERVAL = float(os.getenv("FETCH_INTERVAL", "8"))
_COINS_DEFAULT = [
    ("bitcoin","BTC"), ("ethereum","ETH"),
    ("binancecoin","BNB"), ("solana","SOL")
]
_last_prices: Dict[str, Any] = {"ts":0, "data":[]}
_symbol_map = {sym: cg for cg, sym in _COINS_DEFAULT}

async def _fetch_prices(symbols: List[str]) -> List[Dict[str, Any]]:
    # Lọc theo symbols
    coins = [(next((cg for cg,s in _COINS_DEFAULT if s==sym), None), sym) for sym in symbols]
    coins = [(cg,sym) for cg,sym in coins if cg]
    if not coins: coins = _COINS_DEFAULT

    ids = ",".join(cg for cg,_ in coins)
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": ids, "vs_currencies":"usd", "include_24hr_change":"true"}

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        raw = r.json()

    out = []
    for cg_id, sym in coins:
        if cg_id in raw:
            usd = raw[cg_id].get("usd", 0.0)
            chg = raw[cg_id].get("usd_24h_change", 0.0)
            out.append({"symbol":sym, "price":usd, "change":chg})
    return out

@app.get("/api/prices")
async def api_prices():
    # REST fallback (mặc định 4 coin)
    try:
        return JSONResponse(await _fetch_prices([sym for _,sym in _COINS_DEFAULT]))
    except Exception as e:
        return JSONResponse({"error":str(e)}, status_code=500)

@app.websocket("/ws/ticker")
async def ws_ticker(websocket: WebSocket):
    await websocket.accept()
    # danh sách coin cho mỗi client (mặc định)
    symbols = [sym for _, sym in _COINS_DEFAULT]
    try:
        # Gửi snapshot ngay:
        snapshot = await _fetch_prices(symbols)
        await websocket.send_json({"type":"snapshot","data":snapshot,"ts":time.time()})

        last_push = 0.0
        while True:
            # Non-blocking receive (để vẫn đẩy đều)
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=FETCH_INTERVAL)
                try: payload = json.loads(msg)
                except Exception: payload = {}
                if payload.get("type") == "set":
                    req_syms = payload.get("symbols") or []
                    # chỉ nhận ký hiệu hợp lệ
                    new_syms = [s for s in req_syms if s in _symbol_map or s in [sym for _,sym in _COINS_DEFAULT]]
                    if new_syms:
                        symbols = new_syms
                        snap = await _fetch_prices(symbols)
                        await websocket.send_json({"type":"snapshot","data":snap,"ts":time.time()})
                # các type khác bỏ qua
            except asyncio.TimeoutError:
                pass

            # gửi update theo nhịp
            now = time.time()
            if now - last_push >= FETCH_INTERVAL:
                try:
                    upd = await _fetch_prices(symbols)
                    await websocket.send_json({"type":"update","data":upd,"ts":now})
                except Exception as e:
                    await websocket.send_json({"type":"error","text":f"Ticker fetch error: {e}"})
                last_push = now
    except WebSocketDisconnect:
        return

# ----------------------------------------------------------
# ================== TTS (gTTS) có cache ===================
from gtts import gTTS
from pydantic import BaseModel
CACHE_DIR = "/tmp/tts_cache"; os.makedirs(CACHE_DIR, exist_ok=True)

class TTSReq(BaseModel):
    text: str
    lang: Optional[str] = "vi"
    slow: Optional[bool] = False

def _cache_name(text: str, lang: str, slow: bool) -> str:
    import hashlib
    h = hashlib.sha256(f"{lang}|{slow}|{text}".encode("utf-8")).hexdigest()[:24]
    return os.path.join(CACHE_DIR, f"{h}.mp3")

@app.post("/api/tts")
async def api_tts(req: TTSReq):
    text = (req.text or "").strip()
    if not text:
        return JSONResponse({"error":"text is empty"}, status_code=400)
    fpath = _cache_name(text, req.lang or "vi", bool(req.slow))
    if not os.path.exists(fpath):
        tts = gTTS(text=text, lang=req.lang or "vi", slow=bool(req.slow))
        tts.save(fpath)
    return FileResponse(fpath, media_type="audio/mpeg")

# ----------------------------------------------------------
@app.get("/")
async def root():
    return PlainTextResponse(
        "RaidenX8 API\n"
        "- WS Chat: /ws/chat\n"
        "- WS Ticker: /ws/ticker (send {type:'set', symbols:['BTC','ETH']})\n"
        "- REST Ticker: GET /api/prices\n"
        "- TTS: POST /api/tts\n"
        "- Health: /healthz\n"
                    )
