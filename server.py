import os, json, asyncio
from typing import Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
import httpx
from gtts import gTTS

# ==== AI SDKs (tuỳ chọn: dùng gì thì đặt KEY đó) ====
import google.generativeai as genai  # GEMINI_API_KEY
import openai                         # OPENAI_API_KEY

app = FastAPI()

# ===== CORS =====
CORS_ALLOW_ORIGINS = os.getenv("CORS_ALLOW_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in CORS_ALLOW_ORIGINS.split(",")] if CORS_ALLOW_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== Keys / config =====
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
FETCH_INTERVAL = int(os.getenv("FETCH_INTERVAL", "12"))  # giây

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
if OPENAI_KEY:
    openai.api_key = OPENAI_KEY

# ====== Realtime prices (cache tại server) ======
prices: Dict[str, Any] = {}

async def fetch_prices_loop():
    coins = ["bitcoin", "ethereum", "toncoin", "binancecoin", "arbitrum"]
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": ",".join(coins), "vs_currencies": "usd", "include_24hr_change": "true"}
    async with httpx.AsyncClient(timeout=15) as client:
        while True:
            try:
                r = await client.get(url, params=params)
                data = r.json()
                # Chuẩn hoá khoá theo ký hiệu
                mapping = {
                    "bitcoin": "BTC",
                    "ethereum": "ETH",
                    "toncoin": "TON",
                    "binancecoin": "BNB",
                    "arbitrum": "ARB",
                }
                for k, v in data.items():
                    sym = mapping.get(k, k.upper())
                    prices[sym] = {
                        "usd": v.get("usd"),
                        "change_24h": v.get("usd_24h_change")
                    }
            except Exception as e:
                print("Price fetch error:", e)
            await asyncio.sleep(FETCH_INTERVAL)

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(fetch_prices_loop())

@app.get("/prices")
async def get_prices():
    return prices

# ====== AI Chat logic ======
async def ai_reply(text: str) -> str:
    """Trả lời bằng Gemini trước; nếu không có thì dùng OpenAI; nếu đều trống → trả câu mặc định."""
    try:
        if GEMINI_KEY:
            model = genai.GenerativeModel("gemini-1.5-flash")
            resp = model.generate_content(text)
            return (resp.text or "").strip() or "Mình đang nghe bạn đây!"
        elif OPENAI_KEY:
            r = await openai.ChatCompletion.acreate(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": text}],
                temperature=0.6,
            )
            return r.choices[0].message["content"].strip()
        else:
            return "🚧 Chưa cấu hình API key (GEMINI_API_KEY hoặc OPENAI_API_KEY)."
    except Exception as e:
        return f"Lỗi AI: {e}"

# ====== WebSocket 2 chiều ======
@app.websocket("/ws")
async def ws_chat(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw) if raw and raw[0] in "{[" else {"text": raw}
            user_text = data.get("text", "")
            # echo user bubble (tuỳ frontend hiển thị)
            await ws.send_json({"from": "user", "text": user_text})
            # AI trả lời
            answer = await ai_reply(user_text)
            await ws.send_json({"from": "ai", "text": answer})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print("WS error:", e)

# ====== TTS (giọng nữ Việt bằng gTTS) ======
@app.post("/api/tts")
async def tts(request: Request):
    data = await request.json()
    text = (data.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "missing text"}, status_code=400)
    path = "tts.mp3"
    try:
        gTTS(text=text, lang="vi").save(path)
        return {"audio_url": f"/{path}"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/tts.mp3")
async def get_audio():
    return FileResponse("tts.mp3", media_type="audio/mpeg")

# ====== Health ======
@app.get("/health")
async def health():
    return {"status": "ok", "prices": bool(prices)}
