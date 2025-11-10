import os, time, json, requests
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from queue import Queue

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def ai_answer(prompt, model="auto"):
    if not prompt or not str(prompt).strip():
        return "Bạn hãy nhập nội dung cần hỏi nhé.", "Demo"

    provider = "Demo"

    if OPENAI_API_KEY and model.lower() in ["auto","openai","gpt"]:
        try:
            r = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role":"system","content":"Bạn là trợ lý thân thiện, tiếng Việt ngắn gọn."},
                        {"role":"user","content": prompt}
                    ],
                    "temperature": 0.6
                },
                timeout=30
            )
            r.raise_for_status()
            txt = r.json()["choices"][0]["message"]["content"].strip()
            return txt, "OpenAI"
        except Exception as e:
            return f"(OpenAI lỗi) {e}", "OpenAI"

    if GEMINI_API_KEY and model.lower() in ["auto","gemini","google"]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={GEMINI_API_KEY}"
            body = {"contents":[{"parts":[{"text": prompt}]}]}
            r = requests.post(url, json=body, timeout=30)
            r.raise_for_status()
            data = r.json()
            txt = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            return txt, "Gemini"
        except Exception as e:
            return f"(Gemini lỗi) {e}", "Gemini"

    if "btc" in prompt.lower():
        return "Dùng /prices?ids=bitcoin để xem giá BTC (CoinGecko).", provider
    return "Mình đang ở chế độ demo. Thêm OPENAI_API_KEY hoặc GEMINI_API_KEY để trả lời thật nhé.", provider

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

sse_clients = set()

def push_sse(msg: dict):
    data = "data: " + json.dumps(msg, ensure_ascii=False) + "\\n\\n"
    for q in list(sse_clients):
        try: q.put_nowait(data)
        except Exception: pass

@app.get("/health")
def health():
    return jsonify(ok=True, ts=int(time.time()))

@app.post("/ai/chat")
def chat():
    body = request.get_json(silent=True) or {}
    prompt = body.get("prompt","")
    model = (body.get("model") or "auto")
    txt, provider = ai_answer(prompt, model)
    push_sse({"type":"chat","a":txt,"q":prompt,"provider":provider,"ts":int(time.time())})
    return jsonify(ok=True, model=provider, answer=txt)

@socketio.on("connect")
def on_connect():
    emit("status", {"ok": True, "msg": "WS connected"})

@socketio.on("chat")
def on_chat(data):
    prompt = (data or {}).get("prompt","")
    model = (data or {}).get("model","auto")
    txt, provider = ai_answer(prompt, model)
    emit("reply", {"answer": txt, "provider": provider, "ts": int(time.time())})
    push_sse({"type":"chat_ws","a":txt,"q":prompt,"provider":provider,"ts":int(time.time())})

@app.get("/stream")
def stream():
    from queue import Queue
    q = Queue()
    sse_clients.add(q)
    def gen():
        try:
            yield f"data: {{\\"type\\":\\"hello\\",\\"ts\\":{int(time.time())}}}\\n\\n"
            while True:
                yield q.get()
        except GeneratorExit:
            pass
        finally:
            sse_clients.discard(q)
    return Response(gen(), mimetype="text/event-stream")

@app.get("/prices")
def prices():
    ids = request.args.get("ids","bitcoin,ethereum,binancecoin,solana,toncoin,tether")
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                         params={"ids": ids, "vs_currencies":"usd"}, timeout=15)
        return jsonify(ok=True, data=r.json(), ts=int(time.time()))
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))