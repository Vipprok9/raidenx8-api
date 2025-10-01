
# RaidenX8 API (Render) — Stripe + WebSocket + (Optional PayPal)

## ENV (Render)
- TELEGRAM_BOT_TOKEN = <token bot X8>
- BASE_URL = https://<raidenx8-api>.onrender.com
- STRIPE_SECRET_KEY = sk_test_...
- STRIPE_WEBHOOK_SECRET = whsec_...
- (optional) PAYPAL_CLIENT_ID, PAYPAL_SECRET, PAYPAL_ENV=sandbox|live

## Runbook
1) Deploy this folder to Render as a Web Service.
2) Set ENV above. Start service, check /health = ok.
3) Stripe Dashboard (Test mode) → Webhooks → add endpoint
   - URL: https://<raidenx8-api>.onrender.com/stripe_webhook
   - Event: checkout.session.completed
   - Copy Signing Secret → STRIPE_WEBHOOK_SECRET
4) Telegram webhook:
   https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://<raidenx8-api>.onrender.com/webhook
5) Test in Telegram: /start → Mở RaidenX8 Store

## Notes
- Socket.IO uses eventlet kernel in Procfile.
- Use HTTPS only (Render + Pages provide it).
- PayPal webhook verification is simplified for learning; for production follow PayPal docs to verify signatures.
