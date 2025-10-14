# RaidenX8 — Zing MP3 Proxy (Node.js)

## Endpoints
- `GET /music/search?q=term` → `{ q, count, items:[{id,title,artist,thumbnail,duration}] }`
- `GET /music/stream?id=encodeId` → `{ id, url }` (add `?redirect=1` for 302)
- `GET /music/lyric?id=encodeId` → `{ id, lyric }`
- `GET /healthz` → `ok`

## Render Deploy
- Runtime: Node 18+
- Build: `npm i`
- Start: `npm start`
- Env: `PORT=8080`, `CORS_ORIGINS=https://your-frontend-domain`

## Notes
- Tuân thủ bản quyền. Một số stream có thể thay đổi định kỳ.
- Render free có cold start.
