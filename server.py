import os, json, requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

app = Flask(__name__)
CORS(app)

# ==== Cấu hình ====
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL_FAST = os.getenv("GEMINI_MODEL_FAST", "models/gemini-2.5-flash")
MODEL_SMART = os.getenv("GEMINI_MODEL_SMART", "models/gemini-2.5-pro")
GEN_BASE = "https://generativelanguage.googleapis.com/v1beta"

# ==== Session tối ưu tốc độ ====
session = requests.Session()
retries = Retry(total=1, backoff_factor=0.2, status_forcelist=[429, 500, 502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retries, pool_connections=50, pool_maxsize=50))
session.headers.update({"Connection": "keep-alive"})

# ==== Prompt & Few-shot (giảm “chung chung”) ====
SYS_PROMPT = (
  "Bạn là RaidenX8 – AI Gen-Z, phản hồi NGẮN, THẲNG, CỤ THỂ.\n"
  "• Mở đầu = 1 câu kết luận rõ ràng.\n"
  "• Sau đó 3–5 bullet: số liệu, ví dụ, bước hành động.\n"
  "• Nếu có dữ liệu server (weather/price) → dùng ngay; KHÔNG nói 'hãy lên Google'.\n"
  "• Không dùng ký tự ** hoặc *; không nói 'với tư cách là AI'.\n"
  "• Nếu chưa chắc: nêu giả định + bước kiểm chứng ngắn.\n"
  "Giữ văn phong tự nhiên, dễ hiểu."
)

FEWSHOT = [
  {"role":"user","parts":[{"text":"Tối ưu SEO trang NFT?"}]},
  {"role":"model","parts":[{"text":"Tập trung tốc độ + từ khóa NFT.\n- LCP <2.5s, CLS <0.1\n- <title>/<meta> chứa NFT, Solana\n- Schema Product JSON-LD\n- Hình WebP + lazy load"}]},
  {"role":"user","parts":[{"text":"Cách tăng tương tác cộng đồng Web3?"}]},
  {"role":"model","parts":[{"text":"Tạo minigame + phần thưởng rõ ràng.\n- AMA hàng tuần + giveaway\n- Leaderboard token\n- Social quest (Zealy)\n- Thu thập feedback → airdrop nhỏ"}]},
]

BAD_PHRASES = [
  "as an ai", "với tư cách là", "hãy tìm trên google",
  "tôi không thể truy cập", "i cannot access", "as a language model"
]

def _clean(text: str) -> str:
    if not text: return ""
    for s in BAD_PHRASES: text = text.replace(s, "")
    text = text.replace("*", "").strip()
    return "\n".join([ln.strip() for ln in text.splitlines() if ln.strip()])

def _is_generic(t: str) -> bool:
    if not t: return True
    low = t.lower()
    generic = ["tùy trường hợp", "hãy tìm hiểu thêm", "không thể cung cấp", "có thể cân nhắc"]
    return any(k in low for k in generic) or len(t.split()) < 25

def _choose_model(q: str) -> str:
    if len(q) > 140 or any(k in q.lower() for k in ["tại sao","phân tích","so sánh","thuật toán","design","vì sao"]):
        return MODEL_SMART
    return MODEL_FAST

def gemini_call(question: str, retry: bool = True) -> str:
    model = _choose_model(question)
    url = f"{GEN_BASE}/{model}:generateContent?key={GEMINI_API_KEY}"
    contents = [{"role":"user","parts":[{"text": SYS_PROMPT}]}, *FEWSHOT,
                {"role":"user","parts":[{"text": question}]}]
    payload = {
        "contents": contents,
        "generationConfig": {"temperature": 0.45, "topK": 40, "topP": 0.9, "maxOutputTokens": 384}
    }
    try:
        r = session.post(url, json=payload, timeout=(3.5, 8))
        if not r.ok:
            return "Mạng hơi chậm, thử lại giúp mình nhé."
        t = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return "Hơi kẹt, thử lại giúp mình nhé."

    t = _clean(t)

    # Nếu còn chung chung → reprompt 1 lần yêu cầu cụ thể hóa
    if retry and _is_generic(t):
        payload["contents"].append({"role":"user","parts":[{"text":"Cụ thể hơn: thêm số/bước/ví dụ, 3–5 bullet, ngắn gọn."}]})
        try:
            r2 = session.post(url, json=payload, timeout=(3.5, 8))
            if r2.ok:
                t2 = _clean(r2.json()["candidates"][0]["content"]["parts"][0]["text"])
                if not _is_generic(t2):
                    return t2
        except Exception:
            pass
    return t

@app.post("/ai/chat_sync")
def chat_sync():
    data = request.get_json(force=True)
    q = (data.get("message") or "").strip()
    if not q:
        return jsonify({"error": "missing message"}), 400
    return jsonify({"reply": gemini_call(q)})

@app.get("/health")
def health():
    return jsonify({"ok": True, "model_fast": MODEL_FAST, "model_smart": MODEL_SMART})
