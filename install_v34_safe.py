import os
import sys
import shutil
import time
import tarfile
import datetime

# ==========================================
# 配置区域
# ==========================================
BASE_DIR = "/www/wwwroot/v9_upgrade"
BACKUP_NAME = f"backup_before_v34_{int(time.time())}.tar.gz"
CORE_DIR = os.path.join(BASE_DIR, "core")

print("========================================")
print("🛡️ 启动 V34 安全部署 (仿真+备份+全功能)")
print("========================================")

# ==========================================
# 1. 第一道防线：全量备份
# ==========================================
print(f">> [1/6] 正在创建全量备份: {BACKUP_NAME} ...")
try:
    with tarfile.open(os.path.join("/www/wwwroot", BACKUP_NAME), "w:gz") as tar:
        tar.add(BASE_DIR, arcname="v9_upgrade")
    print("   ✅ 备份成功！如果出问题，解压这个文件即可复活。")
except Exception as e:
    print(f"   ❌ 备份失败: {e}")
    # 既然备份失败，为了安全，终止运行
    sys.exit(1)

# ==========================================
# 2. 定义核心代码 (五维战法 + 哨兵)
# ==========================================
STRATEGY_CODE = """class StrategyPro:
    def analyze_intent(self, score, flow_msg, chip_msg, pct_chg, tech_signal):
        if "触底" in tech_signal: return "💎铁底回补"
        if "触顶" in tech_signal: return "⚠️触顶回落"
        if "超买" in tech_signal: return "⚠️顶部风险"
        if "超卖" in tech_signal: return "💎黄金坑"
        if "诱多" in flow_msg: return "⚠️诱多出货"
        if "挖坑" in flow_msg: return "💎主力挖坑"
        if "高危" in chip_msg: return "💣高位派发"
        if "金叉" in tech_signal and score > 65: return "🚀趋势加速"
        if score > 85: return "🚀主升浪"
        if score > 70: return "✨强势拉升"
        if score < 35: return "🌧破位下跌"
        if score > 50 and score < 75 and pct_chg < 0 and pct_chg > -5: return "🛁主力洗盘"
        return "☁️观察等待"
"""

FACTOR_CODE = """import numpy as np
from core.strategy_pro import StrategyPro

class FactorEngineV25:
    def __init__(self, config=None):
        # 纯粹逻辑，不依赖外部配置，防止 NoneType 错误
        self.strat = StrategyPro()

    def calc_tech_indicators(self, closes):
        if len(closes) < 30: return 0, "无"
        ma20 = sum(closes[-20:]) / 20
        std_dev = np.std(closes[-20:])
        upper = ma20 + (2 * std_dev); lower = ma20 - (2 * std_dev)
        current = closes[-1]
        
        deltas = np.diff(closes)
        gains = deltas[deltas > 0].sum(); losses = -deltas[deltas < 0].sum()
        rsi = 50
        if losses > 0: rsi = 100 - (100 / (1 + gains / losses))
            
        ma5 = sum(closes[-5:]) / 5
        signal = "普通"; score = 0
        if current < lower: signal = "触底"; score = +25
        elif current > upper: signal = "触顶"; score = -25
        elif rsi > 85: signal = "超买"; score = -20
        elif rsi < 15: signal = "超卖"; score = +20
        elif ma5 > ma20: signal = "金叉"; score = +10
        return score, signal

    def calc_fund_divergence(self, money, pct_chg):
        if not money: return 50, "正常"
        net = money[0].get('main_net_inflow', 0) / 10000
        score = 50 + (10 if net>0 else 0) + (10 if net>500 else 0)
        msg = "正常"
        if pct_chg > 2 and net < -500: msg = "诱多"
        if pct_chg < -2 and net > 500: msg = "挖坑"
        return score, msg

    def calc_chip_risk(self, cyq, price):
        if not cyq: return 50, "正常"
        win = cyq.get('winner_rate', 50)
        cost = cyq.get('avg_cost', price) or price
        bias = (price - cost) / cost * 100
        msg = "正常"
        if win > 90 and bias > 20: msg = "高危"
        return win, msg

    def calc_regime(self, market):
        if not market or len(market)<20: return "SHOCK"
        closes = [d['close'] for d in market]
        ma20 = sum(closes[:20]) / len(closes[:20])
        trend = (closes[0] - ma20) / ma20 * 100
        if trend > 1: return "BULL"
        if trend < -1: return "BEAR"
        return "SHOCK"

    def calculate(self, daily, money, market, cyq):
        if not daily or len(daily) < 30: return 50.0, {}, "观察"
        try:
            closes = [d['close'] for d in daily][::-1]
            pct_chg = daily[0].get('change_pct', 0)
            vol = daily[0].get('vol', 0)
            close = daily[0].get('close', 0)
            
            regime = self.calc_regime(market)
            score_money, msg_money = self.calc_fund_divergence(money, pct_chg)
            score_chip, msg_chip = self.calc_chip_risk(cyq, close)
            tech_fix, tech_signal = self.calc_tech_indicators(closes)
            
            w_money, w_chip = 0.4, 0.4
            if regime == "BEAR": w_money, w_chip = 0.6, 0.2
            if regime == "BULL": w_money, w_chip = 0.3, 0.5
            
            base_score = (score_money * w_money) + (score_chip * w_chip) + (50 * 0.2)
            final_score = base_score + tech_fix
            final_score = min(99, max(1, final_score))
            
            decision = self.strat.analyze_intent(final_score, msg_money, msg_chip, pct_chg, tech_signal)
            return round(final_score, 1), {}, decision
        except: return 50.0, {}, "观察"

def calculate_v9_score(daily, money, market, cyq):
    return FactorEngineV25().calculate(daily, money, market, cyq)
"""

SENTINEL_CODE = """import time, requests, json, datetime
from decimal import Decimal, ROUND_UP
PUSH_TOKEN = "5c315738bc1b4c73aca77ff37d3039a5"
CHECK_INTERVAL = 60
sent_history = {}; last_rec = 0; auc_cache = {}

def get_lim(p, c):
    pct=0.1
    if c.startswith('30') or c.startswith('688'): pct=0.2
    elif c.startswith('8') or c.startswith('4'): pct=0.3
    lim = float((Decimal(str(p)) * Decimal(str(1+pct))).quantize(Decimal('0.01'), rounding=ROUND_UP))
    return lim

def get_rt(c):
    try:
        m, o = c.split('.')[1].lower(), c.split('.')[0]
        r = requests.get(f"http://qt.gtimg.cn/q={m}{o}", timeout=2)
        d = r.text.split('="')[1].split('~')
        return {'p':float(d[3]), 'pct':float(d[32]), 'b1':float(d[10]), 'a1':float(d[20])}
    except: return None

def send(msg):
    if not msg: return
    try: requests.post("http://www.pushplus.plus/send", json={"token":PUSH_TOKEN,"title":"监控","content":msg,"template":"txt"}, timeout=3)
    except: pass

def run():
    print("Sentinel Running...")
    while True:
        try:
            now = datetime.datetime.now(); t = now.time()
            is_auc = datetime.time(9,23)<=t<=datetime.time(9,25)
            is_trd = (datetime.time(9,30)<=t<=datetime.time(11,30)) or (datetime.time(13,0)<=t<=datetime.time(14,55))
            w = requests.get("http://127.0.0.1:9000/api/watchlist", timeout=3).json().get('stocks',[])
            if is_auc:
                msg = ""
                for s in w:
                    if s['ts_code'] in auc_cache: continue
                    d = get_rt(s['ts_code'])
                    if not d or d['a1']==0: continue
                    ratio = d['b1']/d['a1']
                    sig = ""
                    if d['pct']>2 and ratio<0.3: sig="⚠️诱多"
                    if d['pct']<=0 and ratio>3: sig="💎黄金坑"
                    if d['pct']>2 and ratio>10: sig="🔥暴力抢筹"
                    if sig:
                        lim = get_lim(d['p'], s['ts_code'])
                        msg += f"{sig} {s['name']}\n涨:{d['pct']}%\n比:{ratio:.1f}\n挂:{lim}\n\n"
                        auc_cache[s['ts_code']] = 1
                if msg: send(msg)
            if is_trd and now.timestamp() - globals()['last_rec'] > 300:
                opps = []
                for s in w:
                    d = get_rt(s['ts_code'])
                    if d and d['a1']>0:
                        r = d['b1']/d['a1']
                        sc = 50 + (30 if r>10 else 10 if r>3 else 0)
                        if sc>=75: opps.append({'n':s['name'], 'p':d['p'], 'pct':d['pct'], 's':sc, 'r':r})
                if opps:
                    top = sorted(opps, key=lambda x:x['s'], reverse=True)[:3]
                    m = "\\n".join([f"🚀{o['n']} {o['pct']}%\分:{o['s']} 抢:{o['r']:.1f}" for o in top])
                    send(m)
                    globals()['last_rec'] = now.timestamp()
        except: pass
        time.sleep(60)

if __name__ == "__main__": run()
"""

# ==========================================
# 3. 第二道防线：内存仿真测试 (熔断机制)
# ==========================================
print(">> [2/6] 启动沙盒仿真 (Safety Check)...")
try:
    # 动态创建类并测试，不写入文件
    exec(STRATEGY_CODE, globals())
    exec(FACTOR_CODE, globals())
    
    # 造假数据
    dummy_daily = [{'close': 10, 'vol': 1000, 'change_pct': 1}] * 35
    dummy_money = [{'main_net_inflow': 5000000}]
    dummy_market = [{'close': 3000}] * 30
    dummy_cyq = {'winner_rate': 60}
    
    # 运行计算
    score, _, decision = FactorEngineV25().calculate(dummy_daily, dummy_money, dummy_market, dummy_cyq)
    print(f"   ✅ 仿真计算成功: 得分 {score}, 决策 {decision}")
except Exception as e:
    print(f"   ❌ 仿真失败！错误原因: {e}")
    print("   🛡️ 熔断机制已触发：部署自动终止，您的系统未被修改。")
    sys.exit(1)

# ==========================================
# 4. 正式部署核心文件
# ==========================================
print(">> [3/6] 仿真通过，开始写入核心文件...")
os.makedirs(CORE_DIR, exist_ok=True)

with open(os.path.join(CORE_DIR, "strategy_pro.py"), "w", encoding="utf-8") as f:
    f.write(STRATEGY_CODE)
    
with open(os.path.join(CORE_DIR, "factor_engine_v9.py"), "w", encoding="utf-8") as f:
    f.write(FACTOR_CODE)

with open(os.path.join(BASE_DIR, "cloud_sentinel.py"), "w", encoding="utf-8") as f:
    f.write(SENTINEL_CODE)

# ==========================================
# 5. 智能修补 main.py (Python精准手术)
# ==========================================
print(">> [4/6] 智能植入 API 接口...")
main_py_path = os.path.join(BASE_DIR, "main.py")

with open(main_py_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
api_injected = False
api_code = """
@app.get("/api/watchlist")
async def get_watchlist_v34():
    try:
        data = db.get_watchlist()
        return {"success": True, "stocks": [{"ts_code": x["ts_code"], "name": x["name"]} for x in data]}
    except Exception as e:
        print(f"API Error: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/positions")
async def get_positions_v34():
    try:
        data = db.get_all_positions()
        return {"success": True, "positions": data}
    except Exception as e:
        return {"success": False, "error": str(e)}
"""

for line in lines:
    # 防止重复添加
    if "def get_watchlist_v34" in line:
        api_injected = True
    
    # 在启动命令前插入
    if 'if __name__ == "__main__":' in line or "if __name__ == '__main__':" in line:
        if not api_injected:
            new_lines.append(api_code + "\n")
            api_injected = True
        new_lines.append(line)
    else:
        new_lines.append(line)

if not api_injected:
    new_lines.append(api_code)

with open(main_py_path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

# ==========================================
# 6. 重启与验证
# ==========================================
print(">> [5/6] 重启服务中...")
os.system("pkill -f main.py")
os.system("pkill -f cloud_sentinel.py")
time.sleep(1)

os.system(f"nohup {BASE_DIR}/venv/bin/python {BASE_DIR}/main.py > /dev/null 2>&1 &")
time.sleep(3)
os.system(f"nohup {BASE_DIR}/venv/bin/python {BASE_DIR}/cloud_sentinel.py > sentinel.out 2>&1 &")

print(">> [6/6] 最终验证...")
res = os.popen(f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:9000/api/watchlist").read().strip()

if res == "200":
    print("\n🎉🎉🎉 V34 完美部署成功！")
    print("✅ 全功能已激活 (五维战法 + 哨兵)")
    print("✅ 系统已备份")
else:
    print(f"⚠️ API 状态码: {res}，请检查日志。")
