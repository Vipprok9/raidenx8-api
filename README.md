# RaidenX8 API — Backend (Flask + Socket.IO + Gemini/OpenAI)
Deploy on Render:

1) Add a new Web Service from this repo/zip.
2) Build Command: `pip install -r requirements.txt`
3) Start Command: `gunicorn --worker-class eventlet -w 1 -b 0.0.0.0:$PORT server:app`
4) Env Vars:
   - PROVIDER = gemini  (or openai)
   - GEMINI_API_KEY (if using Gemini)
   - OPENAI_API_KEY (optional fallback)
   - FRONTEND_ORIGIN = https://raidenx8.pages.dev
   - GEMINI_MODEL = models/gemini-2.5-flash-preview-05-20
   - OPENAI_MODEL = gpt-4o-mini

Test: open `/` to see JSON model, `/health` for health.
WebSocket event names: `user_msg` -> `bot_msg`.
