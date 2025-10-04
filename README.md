# RaidenX8 API (Flask + Socket.IO)

## Env cần có (Render → Environment)
- TELEGRAM_BOT_TOKEN=xxxxx
- TELEGRAM_CHAT_ID=6142290415
- (tuỳ chọn) OPENAI_API_KEY=sk-...

## Start command (Procfile)
web: gunicorn server:app --preload --workers 1 --threads 4 --bind 0.0.0.0:$PORT

## Endpoints
- GET /           → "RaidenX8 API is up."
- GET /health     → "ok"
- GET /events     → {"events":[...]}
- POST /send      → body {"text":"hello"}
- POST /webhook   → Telegram POST vào đây

## Set Telegram webhook
https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://<your-app>.onrender.com/webhook
