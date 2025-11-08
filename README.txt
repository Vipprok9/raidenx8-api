RaidenX8 Backend (Dual Gemini/OpenAI) – WebSocket + SSE + TTS

ENV (Render):
- PROVIDER=gemini | openai
- GEMINI_API_KEY=AIza...
- GEMINI_MODEL=models/gemini-2.5-pro-preview-03-25
- (optional) OPENAI_API_KEY=sk-... ; OPENAI_MODEL=gpt-4o-mini
- FRONTEND_ORIGIN=https://<your-pages>.pages.dev

Start:
  web: gunicorn --worker-class eventlet -w 1 -b 0.0.0.0:$PORT server:app

Test:
  curl -s https://<service>.onrender.com/health
  curl -s -X POST https://<service>.onrender.com/ai/chat -H "Content-Type: application/json" -d '{"message":"Xin chào"}'
