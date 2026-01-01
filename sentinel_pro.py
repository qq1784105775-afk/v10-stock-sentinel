# -*- coding: utf-8 -*-
"""
V9 智能哨兵系统 Pro
修复版：解决推送过于频繁的问题

核心改进：
1. 推送阈值大幅提高
2. 单票当日只推1次（SQLite持久化）
3. 分类推送：持仓/自选/全市场 不同策略
4. 智能冷却：全局30分钟，单票4小时
"""

import time
import requests
import json
import datetime
import sqlite3
import os
from decimal import Decimal, ROUND_UP

# ==================== 配置区 ====================
PUSH_TOKEN = "5c315738bc1b4c73aca77ff37d3039a5"
DB_PATH = "/www/wwwroot/v9_upgrade/v8_data.db"
SENTINEL_DB = "/www/wwwroot/v9_upgrade/sentinel_history.db"
API_BASE = "http://127.0.0.1:9000"

# 推送阈值配置（大幅提高）
CONFIG = {
    # 集合竞价（9:24-9:30）
    "auction": {
        "min_pct": 3.0,          # 涨幅至少3%
        "min_ratio": 10.0,       # 买卖比至少10倍
        "min_amount": 5000000,   # 买一金额至少500万
    },
    # 盘中监控
    "trading": {
        "min_pct": 5.0,          # 涨幅至少5%
        "min_ratio": 8.0,        # 买卖比至少8倍
        "min_score": 80,         # 评分至少80
    },
    # 止损止盈
    "stop": {
        "loss_pct": -5.0,        # 跌破成本5%止损
        "profit_pct": 8.0,       # 涨8%提醒止盈
    },
    # 冷却时间（秒）
    "cooldown": {
        "global": 1800,          # 全局30分钟
        "per_stock": 14400,      # 单票4小时
        "daily_limit": 1,        # 每只票每天最多推1次
    }
}

# ==================== 工具函数 ====================

def init_sentinel_db():
    """初始化哨兵历史数据库"""
    conn = sqlite3.connect(SENTINEL_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS push_history (
            ts_code TEXT,
            push_type TEXT,
            push_time REAL,
            push_date TEXT,
            message TEXT,
            PRIMARY KEY (ts_code, push_date, push_type)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS global_state (
            key TEXT PRIMARY KEY,
            value REAL
        )
    """)
    conn.commit()
    conn.close()

def can_push_stock(ts_code: str, push_type: str) -> bool:
    """检查该股票今天是否可以推送"""
    today = datetime.date.today().isoformat()
    conn = sqlite3.connect(SENTINEL_DB)
    cursor = conn.cursor()
    
    # 检查今日是否已推送
    cursor.execute(
        "SELECT COUNT(*) FROM push_history WHERE ts_code=? AND push_date=?",
        (ts_code, today)
    )
    count = cursor.fetchone()[0]
    conn.close()
    
    return count < CONFIG["cooldown"]["daily_limit"]

def can_push_global() -> bool:
    """检查全局冷却"""
    conn = sqlite3.connect(SENTINEL_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM global_state WHERE key='last_push'")
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return True
    
    last_push = row[0]
    return time.time() - last_push > CONFIG["cooldown"]["global"]

def record_push(ts_code: str, push_type: str, message: str):
    """记录推送历史"""
    now = time.time()
    today = datetime.date.today().isoformat()
    
    conn = sqlite3.connect(SENTINEL_DB)
    conn.execute(
        "INSERT OR REPLACE INTO push_history VALUES (?, ?, ?, ?, ?)",
        (ts_code, push_type, now, today, message)
    )
    conn.execute(
        "INSERT OR REPLACE INTO global_state VALUES ('last_push', ?)",
        (now,)
    )
    conn.commit()
    conn.close()

def clean_old_history():
    """清理7天前的历史记录"""
    week_ago = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    conn = sqlite3.connect(SENTINEL_DB)
    conn.execute("DELETE FROM push_history WHERE push_date < ?", (week_ago,))
    conn.commit()
    conn.close()

def send_push(title: str, content: str):
    """发送微信推送"""
    if not PUSH_TOKEN:
        return
    try:
        requests.post(
            "http://www.pushplus.plus/send",
            json={
                "token": PUSH_TOKEN,
                "title": title,
                "content": content,
                "template": "txt"
            },
            timeout=5
        )
        print(f"📤 已推送: {title}")
    except Exception as e:
        print(f"❌ 推送失败: {e}")

def get_realtime(ts_code: str) -> dict:
    """获取实时行情"""
    try:
        code = ts_code.split('.')[0]
        market = ts_code.split('.')[1].lower()
        url = f"http://qt.gtimg.cn/q={market}{code}"
        resp = requests.get(url, timeout=2)
        
        if '="' not in resp.text:
            return None
        
        data = resp.text.split('="')[1].split('~')
        if len(data) < 40:
            return None
        
        return {
            'name': data[1],
            'price': float(data[3]),
            'pre_close': float(data[4]),
            'open': float(data[5]),
            'pct': float(data[32]),
            'high': float(data[33]),
            'low': float(data[34]),
            'bid1_v': float(data[10]),  # 买一量
            'ask1_v': float(data[20]),  # 卖一量
            'bid1_p': float(data[9]),   # 买一价
        }
    except:
        return None

def get_limit_price(price: float, ts_code: str) -> float:
    """计算涨停价"""
    code = ts_code.split('.')[0]
    if code.startswith('30') or code.startswith('688'):
        pct = 0.2
    elif code.startswith('8') or code.startswith('4'):
        pct = 0.3
    else:
        pct = 0.1
    
    return float((Decimal(str(price)) * Decimal(str(1+pct))).quantize(
        Decimal('0.01'), rounding=ROUND_UP
    ))

# ==================== 数据获取 ====================

def get_positions() -> list:
    """获取持仓列表"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT ts_code, name, cost_price, total_qty FROM positions WHERE total_qty > 0")
        rows = cursor.fetchall()
        conn.close()
        return [{'ts_code': r[0], 'name': r[1], 'cost': float(r[2] or 0), 'qty': r[3]} for r in rows]
    except:
        return []

def get_watchlist() -> list:
    """获取自选列表"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT ts_code, name FROM watchlist")
        rows = cursor.fetchall()
        conn.close()
        return [{'ts_code': r[0], 'name': r[1]} for r in rows]
    except:
        return []

def get_stock_score(ts_code: str) -> float:
    """获取股票V9评分"""
    try:
        resp = requests.get(f"{API_BASE}/api/stock/{ts_code}", timeout=10)
        data = resp.json()
        return data.get('score', 50)
    except:
        return 50

# ==================== 监控逻辑 ====================

def check_positions():
    """监控持仓：止损/止盈"""
    alerts = []
    positions = get_positions()
    
    for pos in positions:
        if not can_push_stock(pos['ts_code'], 'stop'):
            continue
        
        rt = get_realtime(pos['ts_code'])
        if not rt or pos['cost'] <= 0:
            continue
        
        pnl_pct = (rt['price'] - pos['cost']) / pos['cost'] * 100
        
        # 止损提醒
        if pnl_pct <= CONFIG['stop']['loss_pct']:
            msg = f"🚨 {rt['name']} 止损预警\n"
            msg += f"💰 成本：{pos['cost']:.2f}\n"
            msg += f"💵 现价：{rt['price']:.2f}\n"
            msg += f"📉 浮亏：{pnl_pct:.1f}%\n"
            msg += f"💡 建议：减仓或止损"
            alerts.append(('stop_loss', pos['ts_code'], f"🚨 {rt['name']} 止损", msg))
        
        # 止盈提醒
        elif pnl_pct >= CONFIG['stop']['profit_pct']:
            msg = f"🎉 {rt['name']} 止盈提醒\n"
            msg += f"💰 成本：{pos['cost']:.2f}\n"
            msg += f"💵 现价：{rt['price']:.2f}\n"
            msg += f"📈 盈利：+{pnl_pct:.1f}%\n"
            msg += f"💡 建议：分批止盈"
            alerts.append(('stop_profit', pos['ts_code'], f"🎉 {rt['name']} 盈利", msg))
    
    return alerts

def check_watchlist_auction():
    """集合竞价监控自选股"""
    alerts = []
    watchlist = get_watchlist()
    
    for stock in watchlist:
        if not can_push_stock(stock['ts_code'], 'auction'):
            continue
        
        rt = get_realtime(stock['ts_code'])
        if not rt:
            continue
        
        # 计算买卖比
        ask_v = rt['ask1_v'] if rt['ask1_v'] > 0 else 1
        ratio = rt['bid1_v'] / ask_v
        amount = rt['bid1_p'] * rt['bid1_v'] * 100  # 买一金额
        
        # 检查是否满足条件
        cfg = CONFIG['auction']
        if (rt['pct'] >= cfg['min_pct'] and 
            ratio >= cfg['min_ratio'] and 
            amount >= cfg['min_amount']):
            
            limit_price = get_limit_price(rt['pre_close'], stock['ts_code'])
            
            msg = f"🔥 {rt['name']} 暴力抢筹！\n"
            msg += f"📈 涨幅：+{rt['pct']:.1f}%\n"
            msg += f"💪 抢筹比：{ratio:.1f}倍\n"
            msg += f"💰 买一金额：{amount/10000:.0f}万\n"
            msg += f"🎯 建议挂单：{limit_price}"
            
            alerts.append(('auction', stock['ts_code'], f"🔥 {rt['name']} 抢筹", msg))
    
    return alerts

def check_watchlist_trading():
    """盘中监控自选股"""
    alerts = []
    watchlist = get_watchlist()
    
    for stock in watchlist:
        if not can_push_stock(stock['ts_code'], 'trading'):
            continue
        
        rt = get_realtime(stock['ts_code'])
        if not rt:
            continue
        
        cfg = CONFIG['trading']
        
        # 涨幅条件
        if rt['pct'] < cfg['min_pct']:
            continue
        
        # 买卖比条件
        ask_v = rt['ask1_v'] if rt['ask1_v'] > 0 else 1
        ratio = rt['bid1_v'] / ask_v
        if ratio < cfg['min_ratio']:
            continue
        
        # 评分条件（可选，API调用较慢）
        # score = get_stock_score(stock['ts_code'])
        # if score < cfg['min_score']:
        #     continue
        
        limit_price = get_limit_price(rt['pre_close'], stock['ts_code'])
        
        msg = f"🚀 {rt['name']} 强势突破！\n"
        msg += f"📈 涨幅：+{rt['pct']:.1f}%\n"
        msg += f"💪 买卖比：{ratio:.1f}倍\n"
        msg += f"💵 现价：{rt['price']}\n"
        msg += f"🎯 涨停价：{limit_price}"
        
        alerts.append(('trading', stock['ts_code'], f"🚀 {rt['name']} 突破", msg))
    
    return alerts

# ==================== 主循环 ====================

def is_auction_time() -> bool:
    """是否集合竞价时间"""
    now = datetime.datetime.now().time()
    return datetime.time(9, 24) <= now <= datetime.time(9, 30)

def is_trading_time() -> bool:
    """是否交易时间"""
    now = datetime.datetime.now().time()
    morning = datetime.time(9, 30) <= now <= datetime.time(11, 30)
    afternoon = datetime.time(13, 0) <= now <= datetime.time(14, 57)
    return morning or afternoon

def run():
    """主运行循环"""
    print("=" * 50)
    print("🚀 V9 智能哨兵 Pro 启动")
    print("=" * 50)
    print(f"📋 推送阈值：涨幅≥{CONFIG['trading']['min_pct']}%, 买卖比≥{CONFIG['trading']['min_ratio']}")
    print(f"⏰ 冷却时间：全局{CONFIG['cooldown']['global']//60}分钟, 单票每日{CONFIG['cooldown']['daily_limit']}次")
    print("=" * 50)
    
    # 初始化
    init_sentinel_db()
    clean_old_history()
    
    last_heartbeat = 0
    
    while True:
        try:
            now = time.time()
            
            # 心跳日志（每分钟）
            if now - last_heartbeat > 60:
                dt = datetime.datetime.now().strftime('%H:%M:%S')
                print(f"[{dt}] 🟢 哨兵运行中...")
                last_heartbeat = now
            
            all_alerts = []
            
            # 集合竞价时段
            if is_auction_time():
                all_alerts.extend(check_watchlist_auction())
            
            # 交易时段
            if is_trading_time():
                all_alerts.extend(check_positions())
                all_alerts.extend(check_watchlist_trading())
            
            # 发送推送（检查全局冷却）
            for alert in all_alerts:
                push_type, ts_code, title, content = alert
                
                if can_push_global() and can_push_stock(ts_code, push_type):
                    send_push(title, content)
                    record_push(ts_code, push_type, content)
                    time.sleep(1)  # 避免推送太快
            
            # 休息
            time.sleep(30 if is_trading_time() else 60)
            
        except KeyboardInterrupt:
            print("\n👋 哨兵已停止")
            break
        except Exception as e:
            print(f"❌ 错误: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run()
