import os, requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO
import stripe

# ========== ENV ==========
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

BASE_URL = os.environ.get("BASE_URL", "https://raidenx8-api.onrender.com")

# Stripe (test mode)
stripe.api_key = os.environ.get("STRIPE_API_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

# ========== App ==========
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
sio = SocketIO(app, cors_allowed_origins="*")

# ========== Demo products ==========
PRODUCTS = [
    {"id": "p1", "name": "Huawei Smartwatch", "price": 19900, "currency": "usd",
     "image": "https://picsum.photos/seed/huawei-watch/400/300"},
    {"id": "p2", "name": "Smartphone X Pro", "price": 69900, "currency": "usd",
     "image": "https://picsum.photos/seed/smartphone/400/300"},
    {"id": "p3", "name": "Smart Band 7", "price": 4900, "currency": "usd",
     "image": "https://picsum.photos/seed/smartband/400/300"},
    {"id": "p4", "name": "Laptop UltraBook", "price": 129900, "currency": "usd",
     "image": "https://picsum.photos/seed/laptop/400/300"},
    {"id": "p5", "name": "Áo RaidenX8", "price": 2500, "currency": "usd",
     "image": "https://picsum.photos/seed/ao/400/300"},
    {"id": "p6", "name": "Sticker Pack", "price": 500, "currency": "usd",
     "image": "https://picsum.photos/seed/sticker/400/300"},
    {"id": "p7", "name": "Mũ Snapback", "price": 1500, "currency": "usd",
     "image": "https://picsum.photos/seed/mu/400/300"},
]

ORDERS = {}

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

@app.post("/checkout")
def checkout():
    data = request.get_json(force=True)
    items = data.get("items", [])
    chat_id = data.get("chat_id")

    if not items:
        return jsonify({"ok": False, "error": "No items"}), 400

    line_items, total = [], 0
    for it in items:
        pid, qty = it.get("id"), int(it.get("qty", 1))
        prod = next((p for p in PRODUCTS if p["id"] == pid), None)
        if not prod: continue
        total += prod["price"] * qty
        line_items.append({
            "price_data": {
                "currency": prod["currency"],
                "product_data": {"name": prod["name"]},
                "unit_amount": prod["price"]
            },
            "quantity": max(1, qty)
        })

    if not line_items:
        return jsonify({"ok": False, "error": "Invalid items"}), 400

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=line_items,
            mode="payment",
            success_url=BASE_URL + "/success",
            cancel_url=BASE_URL + "/cancel",
            metadata={"chat_id": chat_id or ""}
        )
        order_id = session.id
        ORDERS[order_id] = {"status": "PENDING", "total": total}
        sio.emit("order_update", {"order_id": order_id, "status": "PENDING"})
        return jsonify({"ok": True, "checkout_url": session.url, "order_id": order_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.post("/stripe_webhook")
def stripe_webhook():
    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        print("stripe webhook err:", e)
        return "", 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        order_id = session.get("id")
        chat_id = session.get("metadata", {}).get("chat_id")
        if order_id in ORDERS:
            ORDERS[order_id]["status"] = "PAID"
            ORDERS[order_id]["paid"] = True
            sio.emit("order_update", {"order_id": order_id, "status": "PAID"})
            if chat_id:
                tg_send(chat_id, f"✅ Thanh toán thành công! Order {order_id}")
    return "", 200

@app.post("/webhook")
def webhook():
    data = request.get_json(force=True)
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")
        if text.lower() == "/start":
            tg_send(chat_id, "Xin chào! Đây là RaidenX8 Store 🛍️")
    return jsonify({"ok": True})

@app.route("/events")
def events():
    return jsonify({"orders": ORDERS})

# ========== Main ==========
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
