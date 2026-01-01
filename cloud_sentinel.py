import time
import requests
import json
import datetime

PUSH_TOKEN = "5c315738bc1b4c73aca77ff37d3039a5"
CHECK_INTERVAL = 60 
API_URL = "http://127.0.0.1:9000/api/monitor/check"
sent_history = {}

def send_wechat(msg):
    if not PUSH_TOKEN: return
    now = time.time()
    expired = [k for k, v in sent_history.items() if now - v > 600]
    for k in expired: del sent_history[k]
    if msg in sent_history: return
    sent_history[msg] = now

    url = "http://www.pushplus.plus/send"
    data = {
        "token": PUSH_TOKEN,
        "title": "🚨 V28 监控预警",
        "content": msg,
        "template": "html"
    }
    try: requests.post(url, json=data)
    except: pass

def run_sentinel():
    print(f"📡 智能哨兵 V28 启动 (静默模式)...")
    while True:
        try:
            res = requests.get(API_URL, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data.get('alarm'):
                    send_wechat(data.get('message'))
                    print(f"⚠️ [{datetime.datetime.now().strftime('%H:%M')}] 触发警报")
                # 正常时不打印日志，防止写爆磁盘
        except: pass
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    run_sentinel()
