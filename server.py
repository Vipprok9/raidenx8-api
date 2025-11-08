
from flask import Flask, request, jsonify
import os, requests

app = Flask(__name__)

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_msg = data.get('message', '').lower()
    if 'thời tiết' in user_msg:
        return jsonify({"reply": "Trời ở Huế hôm nay mát mẻ, có nắng nhẹ ☀️"})
    elif 'btc' in user_msg:
        return jsonify({"reply": "Giá BTC hiện khoảng 68,000 USD 💰"})
    else:
        return jsonify({"reply": "Xin chào! Tôi là Aurora Bot 🌌"})
    
@app.route('/')
def home():
    return jsonify({"ok": True, "model": "gemini-2.5-flash-preview-05-20"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
