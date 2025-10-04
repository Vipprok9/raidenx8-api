# RaidenX8 API (Render + Socket.IO + SSE) — v8.2-patch.2

Production-ready API for RaidenX8:
- Flask + Flask-SocketIO (eventlet worker)
- SSE stream (`/stream`) for lightweight subscriptions
- Telegram notify (`POST /notify`)
- AI passthrough: `POST /ai/openai`, `POST /ai/gemini`
- Health check: `GET /health`

## Deploy (Render.com)
1. Push this repo to GitHub.
2. On Render, create a Web Service from this repo.
3. Render will auto-detect `render.yaml`.
4. Set env vars on Render Dashboard:
   - `TELEGRAM_BOT_TOKEN`
   - `OPENAI_API_KEY` (optional)
   - `GEMINI_API_KEY` (optional)
5. Deploy.

## Socket.IO (client)
```html
<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
<script>
  const socket = io("YOUR_RENDER_BASE_URL", { transports: ["websocket", "polling"] });
  socket.on("connect", () => console.log("socket connected", socket.id));
  socket.on("hello", (msg) => console.log("hello", msg));
  socket.on("chat",  (msg) => console.log("chat", msg));
  socket.on("telegram_ack", (msg) => console.log("telegram", msg));

  function sendChat(text){
    socket.emit("chat", {role:"user", content:text});
  }
</script>
```

## SSE (client)
```js
const es = new EventSource("YOUR_RENDER_BASE_URL/stream");
es.onmessage = (e) => console.log("sse:", e.data);
```

## Telegram notify
```bash
curl -X POST https://YOUR_RENDER_BASE_URL/notify   -H "Content-Type: application/json"   -d '{"chat_id":"123456789","text":"Hello from RaidenX8"}'
```

## Start locally
```bash
pip install -r requirements.txt
python server.py
# open http://localhost:5000/health
```
