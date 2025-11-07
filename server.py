import os, json, time, requests, re
from flask import Flask, request, Response, jsonify
from flask_cors import CORS
from functools import lru_cache

app = Flask(__name__)
CORS(app)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash")
GEN_URL_STREAM = f"https://generativelanguage.googleapis.com/v1beta/{GEMINI_MODEL}:streamGenerateContent"

SYS_PROMPT = (
    "Bạn là RaidenX8 – trợ lý Gen-Z quốc tế, trả lời NGẮN – THẲNG – CÓ SỐ.\n"
    "Quy tắc:\n"
    "- Luôn mở đầu bằng đáp án hoặc kết luận 1 câu.\n"
    "- Sau đó cho 3–5 gạch đầu dòng hành động/số liệu/ví dụ cụ thể.\n"
    "- Nếu server đã cung cấp dữ liệu (thời tiết/giá coin), PHẢI dùng, KHÔNG nói 'hãy tự lên Google'.\n"
    "- Không dùng ký tự ** hoặc * để in đậm. Không nói 'với tư cách là AI'.\n"
)

BAD_PHRASES = [
    "với tư cách là một ai", "as an ai", "tôi không thể truy cập", "hãy tìm trên google",
    "tôi không có khả năng", "i cannot access real-time", "as a language model"
]

def clean_text(t: str) -> str:
    if not t:
        return t
    t = t.replace("*", "")
    for s in BAD_PHRASES:
        t = t.replace(s, "")
    # gọn dòng, bỏ đuôi trống
    lines = [ln.rstrip() for ln in t.splitlines()]
    lines = [ln for ln in lines if ln.strip()]
    return "\n".join(lines)

def sse_pack(text: str):
    return f"data: {text}\n\n"

@app.get("/health")
def health():
    return {"ok": True, "model": GEMINI_MODEL}

# ---------------------- Routers: Weather / Prices ---------------------- #

@lru_cache(maxsize=64)
def _geo_lookup(city: str):
    # Open-Meteo geocoding (no key)
    url = "https://geocoding-api.open-meteo.com/v1/search"
    r = requests.get(url, params={"name": city, "language": "vi", "count": 1, "format": "json"}, timeout=5)
    j = r.json()
    if j.get("results"):
        res = j["results"][0]
        return {"lat": res["latitude"], "lon": res["longitude"], "name": res["name"], "country": res.get("country")}
    return None

def get_weather(query: str):
    # bắt city từ câu hỏi
    m = re.search(r"(thời tiết|mưa|nắng|nhiệt độ).*(?:tại|ở)\s+([A-Za-zÀ-ỹ\s]+)", query, re.IGNORECASE)
    city = m.group(2).strip() if m else "Huế"
    g = _geo_lookup(city)
    if not g:
        return None
    url = "https://api.open-meteo.com/v1/forecast"
    r = requests.get(url, params={
        "latitude": g["lat"], "longitude": g["lon"],
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,precipitation",
        "timezone": "auto"
    }, timeout=5)
    j = r.json().get("current", {})
    if not j:
        return None
    return {
        "city": g["name"], "country": g.get("country"),
        "temp": j.get("temperature_2m"), "feels": j.get("apparent_temperature"),
        "hum": j.get("relative_humidity_2m"), "wind": j.get("wind_speed_10m"),
        "rain": j.get("precipitation")
    }

def get_price(asset: str):
    # map nhanh vài coin phổ biến
    slug = {
        "btc": "bitcoin", "bitcoin": "bitcoin",
        "eth": "ethereum", "ethereum": "ethereum",
        "bnb": "binancecoin", "sol": "solana", "ton": "the-open-network",
        "xrp": "ripple", "usdt":"tether", "usdc":"usd-coin"
    }.get(asset.lower(), asset.lower())
    url = "https://api.coingecko.com/api/v3/simple/price"
    r = requests.get(url, params={"ids": slug, "vs_currencies": "usd"}, timeout=5)
    j = r.json()
    if slug in j:
        return {"asset": slug, "usd": j[slug]["usd"]}
    return None

def looks_like_weather(q: str) -> bool:
    return bool(re.search(r"\b(thời tiết|mưa|nắng|gió|nhiệt độ)\b", q, re.IGNORECASE))

def looks_like_price(q: str) -> str | None:
    m = re.search(r"(giá|price)\s+([a-zA-Z]{2,6})", q, re.IGNORECASE)
    return m.group(2) if m else None

# ---------------------- Gemini Stream ---------------------- #

def gemini_stream_reply(user_text: str):
    if not GEMINI_API_KEY:
        yield sse_pack("⚠️ Chưa cấu hình GEMINI_API_KEY ở Render.")
        return
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": f"{SYS_PROMPT}\n\nNgười dùng: {user_text}"}]}
        ],
        "generationConfig": {
            "temperature": 0.5, "topK": 40, "topP": 0.9, "maxOutputTokens": 512
        }
    }
    try:
        with requests.post(
            f"{GEN_URL_STREAM}?key={GEMINI_API_KEY}",
            json=payload, timeout=8, stream=True, headers={"Connection": "keep-alive"}
        ) as r:
            buff = []
            for line in r.iter_lines(decode_unicode=True):
                if not line: 
                    continue
                # mỗi dòng JSON nhỏ chứa parts[].text
                try:
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    obj = json.loads(line)
                    parts = obj.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    chunk = "".join(p.get("text", "") for p in parts)
                    if not chunk:
                        continue
                    chunk = clean_text(chunk)
                    if chunk:
                        buff.append(chunk)
                        yield sse_pack(chunk)
                except Exception:
                    # dòng keepalive hoặc định dạng khác → bỏ qua
                    continue
            # đóng gói đảm bảo có ít nhất dấu chấm câu kết thúc
            if buff:
                yield sse_pack("\n")
    except requests.exceptions.Timeout:
        yield sse_pack("⏱️ Hệ thống hơi chậm, thử lại giúp mình nhé.")
    except Exception as e:
        yield sse_pack(f"⚠️ Lỗi: {str(e)[:120]}")

@app.post("/ai/chat")
def ai_chat():
    data = request.get_json(silent=True) or {}
    text = (data.get("message") or "").strip()
    if not text:
        return jsonify({"error": "missing message"}), 400

    # Router trước để trả lời có số liệu thật (siêu nhanh)
    asset = looks_like_price(text)
    if asset:
        pr = get_price(asset)
        if pr:
            msg = f"Giá {asset.upper()}: ~{pr['usd']:,} USD.\n- Nguồn nhanh: CoinGecko.\n- Nhắc: giá biến động theo giây."
            return jsonify({"reply": msg})

    if looks_like_weather(text):
        w = get_weather(text)
        if w:
            msg = (
                f"Thời tiết {w['city']}: {w['temp']}°C, thể cảm {w['feels']}°C.\n"
                f"- Ẩm: {w['hum']}%\n- Gió: {w['wind']} km/h\n- Lượng mưa: {w['rain']} mm/h"
            )
            return jsonify({"reply": msg})

    # Không vào rule → gọi Gemini (stream SSE)
    return Response(gemini_stream_reply(text), mimetype="text/event-stream")

# fallback reply không stream, nếu frontend cần
@app.post("/ai/chat_sync")
def ai_chat_sync():
    data = request.get_json(silent=True) or {}
    text = (data.get("message") or "").strip()
    if not text:
        return jsonify({"error": "missing message"}), 400

    payload = {
        "contents":[{"role":"user","parts":[{"text": f"{SYS_PROMPT}\n\nNgười dùng: {text}"}]}],
        "generationConfig":{"temperature":0.5,"topK":40,"topP":0.9,"maxOutputTokens":512}
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    r = requests.post(url, json=payload, timeout=12)
    j = r.json()
    try:
        t = "".join(p.get("text","") for p in j["candidates"][0]["content"]["parts"])
    except Exception:
        t = "Xin lỗi, có lỗi khi tạo câu trả lời."
    return jsonify({"reply": clean_text(t)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=False)
