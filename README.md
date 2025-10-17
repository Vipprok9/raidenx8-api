# AI Singing Backend Proxy

## Endpoints
- `POST /ai/sing` → Body `{ "lyrics": "...", "style": "edm_remix_bass" }` → Returns `{ "audio_url": "<mp3>" }`

## Quick Deploy on Render
1. New Web Service → upload `server.py`, `requirements.txt`.
2. Start command:
   ```
   gunicorn -w 1 -b 0.0.0.0:$PORT server:app
   ```
3. (Optional) Set ENV:
   - `PROVIDER=goapi` (hoặc `custom` hoặc để trống để chạy demo)
   - `PROVIDER_URL` = endpoint provider (ví dụ cho `custom`)
   - `PROVIDER_KEY` = API key của provider

## Test
```
curl -X POST https://<service>.onrender.com/ai/sing   -H "Content-Type: application/json"   -d '{"lyrics":"La la la~ love remix","style":"edm_remix_bass"}'
```

Nếu `PROVIDER=none` (mặc định), API trả về mp3 demo để frontend phát thử.
