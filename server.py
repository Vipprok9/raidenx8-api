import os, requests
from flask import Flask, request, jsonify
from flask_cors import CORS

# ========= ENV =========
BOT_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "")
TG_API      = f"https://api.telegram.org/bot{BOT_TOKEN}"

BASE_URL    = os.environ.get("BASE_URL", "https://raidenx8-api.onrender.com")

# (Tuỳ chọn) Stripe test mode
STRIPE_API_KEY       = os.environ.get("STRIPE_API_KEY", "")
STRIPE_WEBHOOK_SECRET= os.environ.get("STRIPE_WEBHOOK_SECRET", "")

# ========= App =========
app = Flask(__name__)
# Cho phép Cloudflare Pages gọi API (có thể mở rộng thêm domain nếu cần)
CORS(app, resources={r"/*": {"origins": ["https://raidenx8.pages.dev"]}})

# ========= Demo products (chỉ minh hoạ, không bắt buộc) =========
PRODUCTS = [
    {"id": "p1", "name": "Huawei Smartwatch", "price": 19900, "image": "https://picsum.photos/seed/huawei-watch/400/300"},
    {"id": "p2", "name": "Smartphone X Pro",  "price": 69900, "image": "https://picsum.photos/seed/smartphone/400/300"},
    {"id": "p3", "name": "Smart Band 7",      "price":  4900, "image": "https://picsum.photos/seed/smartband/400/300"},
    {"id": "p4", "name": "Laptop UltraBook",  "price":129900, "image": "https://picsum.photos/seed/laptop/400/300"},
    {"id": "p5", "name": "Áo RaidenX8",       "price":  2500, "image": "https://picsum.photos/seed/ao/400/300"},
    {"id": "p6", "name": "Sticker Pack",      "price":   500, "image": "https://picsum.photos/seed/sticker/400/300"},
    {"id": "p7", "name": "Mũ Snapback",       "price":  1500, "image": "https://picsum.photos/seed/mu/400/300"},
]

# ========= Utils =========
def tg_send(chat_id: str, text: str):
    """Gửi tin nhắn Telegram đơn giản; in lỗi ra log nếu thất bại."""
    if not BOT_TOKEN or not chat_id:
        print("tg_send skipped: missing token/chat_id")
        return {"ok": False, "error": "missing_token_or_chat_id"}
    try:
        r = requests.post(f"{TG_API}/sendMessage", json={"chat_id": chat_id, "text": text})
        return r.json()
    except Exception as e:
        print("tg_send err:", e)
        return {"ok": False, "error": str(e)}

# ========= Routes =========
@app.route("/health")
def health():
    return "ok", 200

@app.route("/products")
def list_products():
    # trả demo products (tuỳ bạn dùng hay không)
    return jsonify({"items": PRODUCTS})

@app.route("/send", methods=["POST", "OPTIONS"])
def send_message():
    # Cho preflight CORS
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(silent=True) or {}
    text = data.get("text") or "Khách bấm Chat với shop từ web RaidenX8"
    # Cho phép override chat_id khi cần test, mặc định dùng TG_CHAT_ID từ env
    chat_id = str(data.get("chat_id") or TG_CHAT_ID)

    res = tg_send(chat_id, text)
    status = 200 if res.get("ok") else 500
    return jsonify(res), status

# (Tuỳ chọn) Webhook/Stripe… bạn có thể thêm sau

if __name__ == "__main__":
    # Chạy local khi cần test
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
