
import os, json, requests
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO
import stripe

# ========== ENV ==========
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else None

BASE_URL = os.environ.get("BASE_URL", "")  # e.g. https://raidenx8-api.onrender.com

# Stripe (Test mode recommended while learning)
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

# PayPal (optional - M2). Works with sandbox or live depending on PAYPAL_ENV.
PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")
PAYPAL_SECRET = os.environ.get("PAYPAL_SECRET", "")
PAYPAL_ENV = os.environ.get("PAYPAL_ENV", "sandbox")  # 'sandbox' or 'live'
PAYPAL_BASE = "https://api-m.sandbox.paypal.com" if PAYPAL_ENV == "sandbox" else "https://api-m.paypal.com"

# Web3 optional placeholders (M2)
EVM_RPC_URL = os.environ.get("EVM_RPC_URL", "")
EVM_USDT_ADDRESS = os.environ.get("EVM_USDT_ADDRESS", "")
MERCHANT_EVM_ADDRESS = os.environ.get("MERCHANT_EVM_ADDRESS", "")

# ========== App setup ==========
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
sio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# Demo product data (USD cents)
PRODUCTS = [
    {"id": "p1", "name": "Áo RaidenX8", "price": 1500, "currency": "usd", "desc": "Áo thun R8", "image": "https://placehold.co/600x450?text=Ao"},
    {"id": "p2", "name": "Sticker Pack", "price": 400, "currency": "usd", "desc": "Sticker R8", "image": "https://placehold.co/600x450?text=Sticker"},
    {"id": "p3", "name": "Mũ Snapback", "price": 2500, "currency": "usd", "desc": "Mũ R8", "image": "https://placehold.co/600x450?text=Mu"}
]
ORDERS = {}  # order_id -> {status, total, ts}

# ========== Utils ==========
def tg_send(chat_id, text):
    if not TG_API or not chat_id:
        return
    try:
        requests.post(f"{TG_API}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception as e:
        print("tg_send err:", e)

# ========== Routes ==========
@app.get("/health")
def health():
    return "ok"

@app.get("/products")
def list_products():
    return jsonify({"ok": True, "data": PRODUCTS})

# ----- Stripe checkout (M1) -----
@app.post("/checkout")
def checkout():
    data = request.get_json(force=True, silent=True) or {}
    items = data.get("items", [])
    chat_id = data.get("chat_id")

    if not items:
        return jsonify({"ok": False, "error": "empty_cart"}), 400

    line_items = []
    total = 0
    for it in items:
        pid = it.get("id")
        qty = int(it.get("qty", 1))
        prod = next((p for p in PRODUCTS if p["id"] == pid), None)
        if not prod:
            continue
        total += prod["price"] * qty
        line_items.append({
            "price_data": {
                "currency": prod["currency"],
                "product_data": {"name": prod["name"], "description": prod.get("desc","")},
                "unit_amount": prod["price"],
            },
            "quantity": max(1, qty)
        })

    if not line_items:
        return jsonify({"ok": False, "error": "invalid_items"}), 400

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=line_items,
            success_url=f"{BASE_URL}/payment_success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{BASE_URL}/payment_cancel",
            metadata={"chat_id": str(chat_id or "")}
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    order_id = session.id
    ORDERS[order_id] = {"status": "PENDING", "ts": datetime.utcnow().isoformat(), "total": total}
    sio.emit("order_update", {"order_id": order_id, "status": "PENDING", "total": total})
    return jsonify({"ok": True, "checkout_url": session.url, "order_id": order_id})

@app.post("/stripe_webhook")
def stripe_webhook():
    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        print("stripe webhook err:", e)
        return ("", 400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        order_id = session.get("id")
        chat_id = session.get("metadata", {}).get("chat_id")
        amount_total = session.get("amount_total")
        currency = (session.get("currency") or "usd").upper()

        if order_id in ORDERS:
            ORDERS[order_id]["status"] = "PAID"
            ORDERS[order_id]["paid"] = amount_total
            sio.emit("order_update", {"order_id": order_id, "status": "PAID", "paid": amount_total, "currency": currency})

        if chat_id:
            try:
                tg_send(int(chat_id), f"✅ Stripe: thanh toán thành công {amount_total/100:.2f} {currency} — Đơn {order_id}")
            except Exception as e:
                print("tg notify err:", e)

    return ("", 200)

# ----- Telegram webhook -----
@app.post("/webhook")
def webhook():
    upd = request.get_json(force=True, silent=True) or {}
    msg = upd.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    text = (msg.get("text") or "").strip().lower()
    if not chat_id:
        return "ok"

    if text in ("/start", "shop", "store", "mua"):
        reply_markup = {
            "keyboard": [[{
                "text": "🛒 Mở RaidenX8 Store",
                "web_app": {"url": "https://<raidenx8-store>.pages.dev"}
            }]],
            "resize_keyboard": True
        }
        try:
            requests.post(f"{TG_API}/sendMessage", json={
                "chat_id": chat_id,
                "text": "Chào mừng bạn đến RaidenX8 Store!",
                "reply_markup": reply_markup
            })
        except Exception as e:
            print("send keyboard err:", e)
    return "ok"

# ===== PayPal (M2 optional) =====
def paypal_access_token():
    if not PAYPAL_CLIENT_ID or not PAYPAL_SECRET:
        return None
    resp = requests.post(f"{PAYPAL_BASE}/v1/oauth2/token",
                         auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
                         data={"grant_type": "client_credentials"})
    if resp.status_code == 200:
        return resp.json().get("access_token")
    return None

@app.post("/checkout_paypal")
def checkout_paypal():
    # Create PayPal Order (CAPTURE)
    data = request.get_json(force=True, silent=True) or {}
    items = data.get("items", [])
    if not items:
        return jsonify({"ok": False, "error": "empty_cart"}), 400

    total = 0
    for it in items:
        pid = it.get("id"); qty = int(it.get("qty",1))
        prod = next((p for p in PRODUCTS if p["id"]==pid), None)
        if not prod: continue
        total += prod["price"]*qty
    # convert cents->dollars
    amount_str = f"{total/100:.2f}"

    token = paypal_access_token()
    if not token:
        return jsonify({"ok": False, "error": "paypal_not_configured"}), 500

    body = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "amount": {"currency_code": "USD", "value": amount_str}
        }],
        "application_context": {
            "brand_name": "RaidenX8 Store",
            "return_url": f"{BASE_URL}/payment_success",
            "cancel_url": f"{BASE_URL}/payment_cancel"
        }
    }
    r = requests.post(f"{PAYPAL_BASE}/v2/checkout/orders",
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                      data=json.dumps(body))
    if r.status_code not in (200, 201):
        return jsonify({"ok": False, "error": "paypal_create_failed", "detail": r.text}), 500

    order = r.json()
    approve = next((l["href"] for l in order.get("links", []) if l.get("rel")=="approve"), None)
    return jsonify({"ok": True, "paypal_order_id": order.get("id"), "approve_url": approve})

@app.post("/paypal_webhook")
def paypal_webhook():
    # NOTE: For production, verify transmission signature per PayPal docs.
    payload = request.get_json(force=True, silent=True) or {}
    event_type = payload.get("event_type")
    if event_type in ("CHECKOUT.ORDER.APPROVED", "PAYMENT.CAPTURE.COMPLETED"):
        # You would mark order as PAID here after validation.
        sio.emit("order_update", {"order_id": payload.get("resource",{}).get("id","paypal"), "status": "PAID", "provider": "PayPal"})
    return ("", 200)

if __name__ == "__main__":
    sio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
