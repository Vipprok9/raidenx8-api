from fastapi import FastAPI, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
import httpx, asyncio, os, json
from gtts import gTTS
import google.generativeai as genai
import openai

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Config API keys
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
genai.configure(api_key=GEMINI_KEY)
openai.api_key = OPENAI_KEY

# ========== Realtime Ticker ==========
prices = {}

async def fetch_prices():
    coins = ["bitcoin", "ethereum", "bnb", "solana", "toncoin", "tether"]
    url = "https://api.coingecko.com/api/v3/simple/price"
    while True:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(url, params={"ids": ",".join(coins), "vs_currencies": "usd"})
                data = res.json()
                for k, v in data.items():
                    prices[k.upper()] = v["usd"]
        except Exception as e:
            print("Price fetch error:", e)
        await asyncio.sleep(30)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(fetch_prices())

@app.get("/prices")
async def get_prices():
    return prices

# ========== WebSocket 2 chiều ==========
clients = []

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    clients.append(ws)
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            user_text = msg.get("text", "")
            print("User:", user_text)
            
            # AI trả lời
            reply = await ai_reply(user_text)
            await ws.send_json({"from": "ai", "text": reply})
    except Exception as e:
        print("WS closed:", e)
    finally:
        clients.remove(ws)

# ========== AI Chat ==========
async def ai_reply(text):
    try:
        if GEMINI_KEY:
            model = genai.GenerativeModel("gemini-1.5-flash")
            resp = model.generate_content(text)
            return resp.text.strip()
        elif OPENAI_KEY:
            r = await openai.ChatCompletion.acreate(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": text}],
            )
            return r.choices[0].message.content.strip()
        else:
            return "❗ Chưa có API key AI."
    except Exception as e:
        return f"Lỗi AI: {e}"

# ========== TTS (giọng nữ Việt) ==========
@app.post("/api/tts")
async def tts(request: Request):
    data = await request.json()
    text = data.get("text", "")
    tts = gTTS(text=text, lang="vi", tld="com.vn")
    path = "tts.mp3"
    tts.save(path)
    return {"audio_url": f"/{path}"}

@app.get("/tts.mp3")
async def get_audio():
    from fastapi.responses import FileResponse
    return FileResponse("tts.mp3")

# ========== Health ==========
@app.get("/health")
async def health():
    return {"status": "ok", "prices": len(prices)}
