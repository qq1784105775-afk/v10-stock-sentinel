
import requests
import time
from datetime import datetime, time as dt_time

class L2Strategy:
    def __init__(self):
        self.headers = {'User-Agent': 'Mozilla/5.0'}

    def get_limit_rate(self, ts_code, name):
        if 'ST' in name: return 0.05
        elif ts_code.startswith('30') or ts_code.startswith('688'): return 0.20
        elif ts_code.startswith('4') or ts_code.startswith('8'): return 0.30
        else: return 0.10

    def get_realtime_depth(self, ts_code):
        try:
            code, market = ts_code.split('.')
            symbol = f"{market.lower()}{code}"
            url = f"http://qt.gtimg.cn/q={symbol}"
            resp = requests.get(url, headers=self.headers, timeout=1.5)
            if resp.status_code != 200: return None
            data = resp.text.split('~')
            
            # 修复 GPT 指出的风险：数据长度检查
            if len(data) < 40: return None 
            
            return {
                'name': data[1],
                'price': float(data[3]),
                'pre_close': float(data[4]),
                'open': float(data[5]),
                'high': float(data[33]),
                'change_pct': float(data[32]),
                'bid1_p': float(data[9]), 
                'bid1_v': int(data[10]),
                'ask1_p': float(data[19]),
                'ask1_v': int(data[20])
            }
        except: return None

    def check_call_auction(self, ts_code):
        now = datetime.now().time()
        if not (dt_time(9, 24) <= now <= dt_time(9, 31)): return None
        data = self.get_realtime_depth(ts_code)
        if not data or data['open'] == 0: return None
        
        if data['change_pct'] < 2.0: return None
        
        ask_v = data['ask1_v'] if data['ask1_v'] > 0 else 1
        ratio = data['bid1_v'] / ask_v
        if ratio < 3: return None
        
        money_amount = data['bid1_p'] * data['bid1_v'] * 100
        if money_amount < 2000000: return None
        
        bid_suggest = round(data['price'] * 1.01, 2)
        return f"🔥 {data['name']} 暴力抢筹！\n涨幅: +{data['change_pct']}%\n抢筹比: {ratio:.1f}倍\n👉 建议挂单：{bid_suggest}"

    def check_limit_break(self, ts_code, hold_cost):
        data = self.get_realtime_depth(ts_code)
        if not data: return None
        
        limit_rate = self.get_limit_rate(ts_code, data['name'])
        limit_up = round(data['pre_close'] * (1 + limit_rate), 2)
        
        # 炸板预警
        if data['high'] >= limit_up - 0.02:
            if data['price'] < limit_up * 0.98 and data['bid1_p'] < limit_up:
                return f"💣 {data['name']} 炸板核按钮！\n封单消失，回落超2%，建议止盈！"
        
        # 破位止损
        if hold_cost > 0 and data['price'] < hold_cost * 0.97:
             return f"🆘 {data['name']} 破位止损！\n触及风控线，快跑！"
             
        return None

l2_monitor = L2Strategy()
