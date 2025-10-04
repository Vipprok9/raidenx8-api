# RaidenX8 API (Render + Socket.IO) — v8.2-patch.1

Endpoints:
- `GET /` health JSON
- `POST /notify` {chat_id,text} → Telegram
- `POST /ai` {provider:'openai'|'gemini', message}

Realtime (Socket.IO events):
- `ai_reply` {answer}
- `tg_message` {chat_id, text}

## Deploy (Render)
- Create Web Service (Python 3).
- Build Command: `pip install -r requirements.txt`
- Start Command: `python server.py`
- Set env vars: `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`, `GEMINI_API_KEY`.
- After live, configure frontend RX_API_BASE to `https://<service>.onrender.com`.
