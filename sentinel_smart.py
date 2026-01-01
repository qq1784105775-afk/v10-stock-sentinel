# -*- coding: utf-8 -*-
"""
V9 智能哨兵 (融合版)
====================
融合了两个版本的优点 + 智能规则

功能：
1. 竞价监控（9:23-9:25）- 极简4行推送
2. 盘中监控 - 结合V9评分的智能推送
3. 持仓止损止盈 - 分级预警
4. 战术识别 - 诱多/黄金坑/暴力抢筹/尾盘异动
5. 大白话翻译 - 让推送易懂
6. SQLite持久化 - 重启不丢记录
7. 智能冷却 - 分类型不同频率

作者：Claude (融合版)
"""

import time
import requests
import json
import datetime
import sqlite3
import os
from typing import Dict, List, Optional, Tuple
from decimal import Decimal, ROUND_UP

# ==================== 配置区 ====================

PUSH_TOKEN = "5c315738bc1b4c73aca77ff37d3039a5"
DB_PATH = "/www/wwwroot/v9_upgrade/v8_data.db"
SENTINEL_DB = "/www/wwwroot/v9_upgrade/sentinel_smart.db"
API_BASE = "http://127.0.0.1:9000"

# 智能阈值配置（分类型）
THRESHOLDS = {
    # 集合竞价（9:23-9:25）
    "auction": {
        "min_pct": 1.5,           # 涨幅≥1.5%
        "min_ratio": 5.0,         # 买卖比≥5倍
        "min_amount": 2000000,    # 买一金额≥200万
    },
    # 盘中 - 自选股
    "watchlist": {
        "min_pct": 2.0,           # 涨幅≥2%
        "min_ratio": 3.0,         # 买卖比≥3倍
        "min_score": 70,          # V9评分≥70
    },
    # 盘中 - 全市场
    "market": {
        "min_pct": 3.0,           # 涨幅≥3%
        "min_score": 80,          # V9评分≥80
        "max_picks": 3,           # 每次最多推3只
    },
    # 黄金坑（逆势吸筹）
    "golden_pit": {
        "max_pct": 0,             # 涨幅≤0%（在跌）
        "min_ratio": 5.0,         # 买卖比≥5倍（有人接）
    },
    # 持仓止损
    "stop_loss": {
        "warn_pct": -3.0,         # 跌3%警告
        "action_pct": -5.0,       # 跌5%行动
        "urgent_pct": -7.0,       # 跌7%紧急
    },
    # 持仓止盈
    "take_profit": {
        "remind_pct": 5.0,        # 涨5%提醒
        "action_pct": 8.0,        # 涨8%强推
    },
    # 冷却时间（秒）
    "cooldown": {
        "position": 7200,         # 持仓：2小时
        "watchlist": 14400,       # 自选：4小时
        "market": 86400,          # 全市场：24小时（当日1次）
        "global": 300,            # 全局：5分钟
    },
    # 每日推送上限
    "daily_limit": {
        "position": 3,            # 持仓每只最多3次
        "watchlist": 1,           # 自选每只最多1次
        "market": 1,              # 全市场每只最多1次
    }
}

# ==================== 数据库初始化 ====================

def init_db():
    """初始化哨兵数据库"""
    conn = sqlite3.connect(SENTINEL_DB)
    
    # 推送历史表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS push_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT,
            push_type TEXT,
            push_time REAL,
            push_date TEXT,
            title TEXT,
            result TEXT DEFAULT 'unknown'
        )
    """)
    
    # 创建索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_push_code_date ON push_history(ts_code, push_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_push_type_date ON push_history(push_type, push_date)")
    
    # 全局状态表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS global_state (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at REAL
        )
    """)
    
    conn.commit()
    conn.close()
    print("✅ 数据库初始化完成")

def get_today_push_count(ts_code: str, push_type: str) -> int:
    """获取今日推送次数"""
    today = datetime.date.today().isoformat()
    conn = sqlite3.connect(SENTINEL_DB)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM push_history WHERE ts_code=? AND push_type=? AND push_date=?",
        (ts_code, push_type, today)
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_last_push_time(ts_code: str, push_type: str) -> float:
    """获取上次推送时间"""
    conn = sqlite3.connect(SENTINEL_DB)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT push_time FROM push_history WHERE ts_code=? AND push_type=? ORDER BY push_time DESC LIMIT 1",
        (ts_code, push_type)
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

def get_global_last_push() -> float:
    """获取全局上次推送时间"""
    conn = sqlite3.connect(SENTINEL_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM global_state WHERE key='last_push'")
    row = cursor.fetchone()
    conn.close()
    return float(row[0]) if row else 0

def record_push(ts_code: str, push_type: str, title: str):
    """记录推送"""
    now = time.time()
    today = datetime.date.today().isoformat()
    
    conn = sqlite3.connect(SENTINEL_DB)
    conn.execute(
        "INSERT INTO push_history (ts_code, push_type, push_time, push_date, title) VALUES (?, ?, ?, ?, ?)",
        (ts_code, push_type, now, today, title)
    )
    conn.execute(
        "INSERT OR REPLACE INTO global_state (key, value, updated_at) VALUES ('last_push', ?, ?)",
        (str(now), now)
    )
    conn.commit()
    conn.close()

def can_push(ts_code: str, push_type: str) -> Tuple[bool, str]:
    """
    检查是否可以推送
    返回: (可以推送, 原因)
    """
    now = time.time()
    
    # 1. 检查全局冷却
    global_last = get_global_last_push()
    global_cooldown = THRESHOLDS["cooldown"]["global"]
    if now - global_last < global_cooldown:
        remaining = int(global_cooldown - (now - global_last))
        return False, f"全局冷却中({remaining}秒)"
    
    # 2. 检查今日推送次数
    daily_count = get_today_push_count(ts_code, push_type)
    daily_limit = THRESHOLDS["daily_limit"].get(push_type, 1)
    if daily_count >= daily_limit:
        return False, f"今日已推{daily_count}次"
    
    # 3. 检查单票冷却
    last_push = get_last_push_time(ts_code, push_type)
    cooldown = THRESHOLDS["cooldown"].get(push_type, 3600)
    if now - last_push < cooldown:
        remaining = int(cooldown - (now - last_push))
        return False, f"冷却中({remaining}秒)"
    
    return True, "OK"

def clean_old_records():
    """清理7天前的记录"""
    week_ago = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    conn = sqlite3.connect(SENTINEL_DB)
    conn.execute("DELETE FROM push_history WHERE push_date < ?", (week_ago,))
    conn.commit()
    conn.close()

# ==================== 实时数据获取 ====================

def get_realtime(ts_code: str) -> Optional[Dict]:
    """获取实时行情（腾讯接口）"""
    try:
        code, market = ts_code.split('.')
        tx_code = f"{market.lower()}{code}"
        url = f"http://qt.gtimg.cn/q={tx_code}"
        
        resp = requests.get(url, timeout=2)
        if resp.status_code != 200 or '="' not in resp.text:
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
            'bid1_v': float(data[10]),    # 买一量（手）
            'ask1_v': float(data[20]),    # 卖一量（手）
            'bid1_p': float(data[9]),     # 买一价
            'amount': float(data[37]) if len(data) > 37 else 0,  # 成交额
        }
    except Exception as e:
        return None

def get_market_status() -> Dict:
    """获取大盘状态"""
    try:
        sh = get_realtime('000001.SH')
        if sh:
            return {
                'index': sh['price'],
                'pct': sh['pct'],
                'trend': 'up' if sh['pct'] > 0.5 else ('down' if sh['pct'] < -0.5 else 'flat')
            }
    except:
        pass
    return {'index': 0, 'pct': 0, 'trend': 'unknown'}

def get_v9_score(ts_code: str) -> Tuple[float, str]:
    """获取V9评分和决策"""
    try:
        resp = requests.get(f"{API_BASE}/api/stock/{ts_code}", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            score = data.get('score', 50)
            decision = data.get('v9_decision', data.get('action', '观察'))
            return score, decision
    except:
        pass
    return 50, "观察"

# ==================== 核心计算函数 ====================

def calc_rush_ratio(bid1_v: float, ask1_v: float) -> Optional[float]:
    """计算抢筹比：买一量/卖一量"""
    if ask1_v <= 0:
        return None
    return bid1_v / ask1_v

def calc_limit_price(pre_close: float, ts_code: str) -> Tuple[float, str]:
    """
    计算涨停价（区分板块）
    返回: (涨停价, 板块名称)
    """
    code = ts_code.split('.')[0]
    
    # 判断板块
    if code.startswith('30'):
        limit_pct, board = 0.20, "创业板"
    elif code.startswith('688'):
        limit_pct, board = 0.20, "科创板"
    elif code.startswith('8') or code.startswith('4'):
        limit_pct, board = 0.30, "北交所"
    else:
        limit_pct, board = 0.10, "主板"
    
    # 精确计算
    price_decimal = Decimal(str(pre_close))
    limit_decimal = price_decimal * Decimal(str(1 + limit_pct))
    limit_price = float(limit_decimal.quantize(Decimal('0.01'), rounding=ROUND_UP))
    
    return limit_price, board

# ==================== 战术识别（智能规则）====================

def analyze_tactics(pct: float, rush_ratio: Optional[float], 
                   score: float = 50, market_trend: str = 'flat',
                   is_afternoon: bool = False) -> Dict:
    """
    战术识别（核心智能逻辑）
    
    参数:
        pct: 涨跌幅
        rush_ratio: 抢筹比
        score: V9评分
        market_trend: 大盘趋势 (up/down/flat)
        is_afternoon: 是否下午盘
    
    返回:
        {signal: 信号, emoji: 表情, reason: 原因, level: 重要程度1-5}
    """
    if rush_ratio is None:
        return {'signal': '观察', 'emoji': '👁️', 'reason': '数据不足', 'level': 1}
    
    # ===== 危险信号优先 =====
    
    # 尾盘诱多：14:30后突然拉升但抢筹比低
    if is_afternoon and pct > 2 and rush_ratio < 1:
        return {
            'signal': '尾盘诱多',
            'emoji': '⚠️',
            'reason': '尾盘拉升无人接盘，警惕出货',
            'level': 4
        }
    
    # 高位诱多：涨幅高但抢筹比低
    if pct > 3 and rush_ratio < 0.5:
        return {
            'signal': '诱多出货',
            'emoji': '⚠️',
            'reason': '涨幅大但卖压重，主力在出货',
            'level': 4
        }
    
    # 普通诱多
    if pct > 2 and rush_ratio < 0.3:
        return {
            'signal': '诱多警惕',
            'emoji': '⚠️',
            'reason': '涨着但没人接，小心回落',
            'level': 3
        }
    
    # ===== 机会信号 =====
    
    # 暴力抢筹：涨幅高且抢筹比爆炸
    if pct > 2 and rush_ratio > 10:
        extra = ""
        if market_trend == 'down':
            extra = "（逆势更强）"
        return {
            'signal': '暴力抢筹',
            'emoji': '🔥',
            'reason': f'主力疯狂扫货{extra}',
            'level': 5
        }
    
    # 强势抢筹
    if pct > 1 and rush_ratio > 5:
        return {
            'signal': '强势抢筹',
            'emoji': '🔥',
            'reason': '资金积极进场',
            'level': 4
        }
    
    # 黄金坑：跌着但有人抢筹（增加更严格条件）
    # 必须满足：1.下跌 2.强烈抢筹 3.评分合格(如果有)
    if pct <= -2 and rush_ratio > 5:
        # 如果有评分，要求≥55分
        if score is not None and score < 55:
            return {'signal': '观察', 'emoji': '👁️', 'reason': '评分过低', 'level': 1}
        return {
            'signal': '黄金坑',
            'emoji': '💎',
            'reason': f'跌{abs(pct):.1f}%+抢筹{rush_ratio:.1f}' + (f'+评分{score}' if score else ''),
            'level': 5
        }
    
    # 逆势强势：大盘跌但个股涨
    if market_trend == 'down' and pct > 1 and rush_ratio > 3:
        return {
            'signal': '逆势强势',
            'emoji': '💪',
            'reason': '大盘跌它不跌，独立行情',
            'level': 4
        }
    
    # 启动信号：小涨+抢筹
    if 0 < pct <= 2 and rush_ratio > 3:
        return {
            'signal': '启动信号',
            'emoji': '🚀',
            'reason': '刚启动，还有空间',
            'level': 3
        }
    
    # 高分低吸
    if pct <= 0 and score >= 75 and rush_ratio > 2:
        return {
            'signal': '高分低吸',
            'emoji': '⭐',
            'reason': f'评分{score}分但在跌，低吸机会',
            'level': 3
        }
    
    # 默认观察
    return {'signal': '观察', 'emoji': '👁️', 'reason': '暂无明确信号', 'level': 1}

def analyze_stop_loss(pct_from_cost: float, rush_ratio: Optional[float]) -> Dict:
    """
    止损分级分析
    
    参数:
        pct_from_cost: 相对成本的涨跌幅
        rush_ratio: 抢筹比
    """
    cfg = THRESHOLDS["stop_loss"]
    
    # 紧急止损
    if pct_from_cost <= cfg["urgent_pct"]:
        if rush_ratio and rush_ratio > 5:
            return {
                'level': '黄金坑',
                'emoji': '💎',
                'action': '反向加仓',
                'reason': '跌多了但有人接，可能是洗盘'
            }
        return {
            'level': '紧急止损',
            'emoji': '🆘',
            'action': '立即止损',
            'reason': '亏损过大，保护本金'
        }
    
    # 行动止损
    if pct_from_cost <= cfg["action_pct"]:
        if rush_ratio and rush_ratio > 3:
            return {
                'level': '观察',
                'emoji': '👁️',
                'action': '持有观察',
                'reason': '有资金接盘，暂时观察'
            }
        return {
            'level': '止损',
            'emoji': '🚨',
            'action': '减仓50%',
            'reason': '跌破止损线，先减仓'
        }
    
    # 警告
    if pct_from_cost <= cfg["warn_pct"]:
        return {
            'level': '警告',
            'emoji': '⚠️',
            'action': '设好止损',
            'reason': '接近止损位，注意风险'
        }
    
    return None

# ==================== 大白话翻译 ====================

def translate_to_plain(strategy_type: str, reason: str) -> Tuple[str, str]:
    """把专业术语翻译成大白话"""
    
    strategy_map = {
        '底部反转': '抄底机会',
        '强势突破': '突破买入',
        '价值回归': '低估修复',
        '超跌反弹': '反弹机会',
        '趋势延续': '顺势做多',
        '主升浪': '主升行情',
        '黄金启动': '启动信号',
    }
    
    # 理由翻译
    if '筹码' in reason or '主力' in reason or '控盘' in reason:
        plain_reason = "主力吸够筹码，准备拉升"
    elif '资金' in reason and '流入' in reason:
        plain_reason = "大资金在买，看涨"
    elif '突破' in reason:
        plain_reason = "突破压力位，放量上攻"
    elif '超跌' in reason or '获利盘' in reason:
        plain_reason = "跌多了要反弹"
    elif '龙头' in reason or '板块' in reason:
        plain_reason = "板块龙头，跟着热点走"
    elif '放量' in reason or '量价' in reason:
        plain_reason = "成交放量，多头进场"
    elif '挖坑' in reason:
        plain_reason = "主力挖坑洗盘，准备拉升"
    elif '抢筹' in reason:
        plain_reason = "资金抢筹，供不应求"
    else:
        plain_reason = reason  # 保持原样
    
    plain_strategy = strategy_map.get(strategy_type, strategy_type)
    return plain_strategy, plain_reason

# ==================== 消息格式化 ====================

def format_auction_msg(stocks: List[Dict]) -> str:
    """
    竞价推送格式（极简4行）
    
    🔥 宁德时代 暴力抢筹！
    涨幅：+3.2%
    抢筹比：15.3倍
    👉 挂单：282.72
    """
    if not stocks:
        return ""
    
    lines = []
    for s in stocks:
        lines.append(f"{s['emoji']} {s['name']} {s['signal']}！")
        lines.append(f"涨幅：{s['pct']:+.2f}%")
        lines.append(f"抢筹比：{s['rush_ratio']:.1f}倍")
        lines.append(f"👉 挂单：{s['limit_price']}")
        lines.append("")
    
    return "\n".join(lines).strip()

def format_intraday_msg(stocks: List[Dict]) -> str:
    """
    盘中推送格式（适中7行）
    
    🚀 贵州茅台 强势抢筹！[自选股]
    
    💵 现价：1850.00 (+1.5%)
    ⭐ 评分：88分
    💡 信号：主力疯狂扫货
    🎯 挂单：2035.00
    """
    if not stocks:
        return ""
    
    lines = []
    for s in stocks:
        source = s.get('source', '自选')
        lines.append(f"{s['emoji']} {s['name']} {s['signal']}！[{source}]")
        lines.append("")
        lines.append(f"💵 现价：{s['price']:.2f} ({s['pct']:+.1f}%)")
        lines.append(f"⭐ 评分：{s['score']:.0f}分")
        lines.append(f"💡 信号：{s['reason']}")
        lines.append(f"🎯 挂单：{s['limit_price']}")
        lines.append("")
    
    return "\n".join(lines).strip()

def format_stop_loss_msg(stock: Dict) -> str:
    """
    止损推送格式（6行）
    
    🚨 贵州茅台 触发止损！
    
    💰 成本：1850.00
    💵 现价：1750.00 (-5.4%)
    🔢 抢筹比：0.3倍
    💡 建议：减仓50%
    """
    lines = [
        f"{stock['emoji']} {stock['name']} {stock['level']}！",
        "",
        f"💰 成本：{stock['cost']:.2f}",
        f"💵 现价：{stock['price']:.2f} ({stock['pct_from_cost']:+.1f}%)",
    ]
    
    if stock.get('rush_ratio'):
        lines.append(f"🔢 抢筹比：{stock['rush_ratio']:.1f}倍")
    
    lines.append(f"💡 建议：{stock['action']}")
    
    return "\n".join(lines)

def format_take_profit_msg(stock: Dict) -> str:
    """止盈推送格式"""
    lines = [
        f"🎉 {stock['name']} 盈利提醒！",
        "",
        f"💰 成本：{stock['cost']:.2f}",
        f"💵 现价：{stock['price']:.2f} ({stock['pct_from_cost']:+.1f}%)",
        f"💰 浮盈：{stock['profit']:.0f}元",
        f"💡 建议：{stock['action']}"
    ]
    return "\n".join(lines)

# ==================== 推送函数 ====================

def send_push(title: str, content: str, ts_code: str = "", push_type: str = "general"):
    """发送微信推送"""
    if not PUSH_TOKEN or not content:
        return False
    
    try:
        resp = requests.post(
            "http://www.pushplus.plus/send",
            json={
                "token": PUSH_TOKEN,
                "title": title,
                "content": content,
                "template": "txt"
            },
            timeout=5
        )
        
        if resp.status_code == 200:
            # 记录推送
            if ts_code:
                record_push(ts_code, push_type, title)
            print(f"📤 [{datetime.datetime.now().strftime('%H:%M:%S')}] 推送成功: {title}")
            return True
    except Exception as e:
        print(f"❌ 推送失败: {e}")
    
    return False

# ==================== 数据源获取 ====================

def get_positions() -> List[Dict]:
    """获取持仓"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ts_code, name, cost_price, total_qty 
            FROM positions WHERE total_qty > 0
        """)
        rows = cursor.fetchall()
        conn.close()
        return [{'ts_code': r[0], 'name': r[1], 'cost': float(r[2] or 0), 'qty': r[3]} for r in rows]
    except:
        return []

def get_watchlist() -> List[Dict]:
    """获取自选股"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT ts_code, name FROM watchlist")
        rows = cursor.fetchall()
        conn.close()
        return [{'ts_code': r[0], 'name': r[1]} for r in rows]
    except:
        return []

# ==================== 监控逻辑 ====================

def check_positions(market_trend: str) -> List[Dict]:
    """检查持仓止损止盈"""
    alerts = []
    positions = get_positions()
    
    for pos in positions:
        ts_code = pos['ts_code']
        
        # 获取实时数据
        rt = get_realtime(ts_code)
        if not rt or pos['cost'] <= 0:
            continue
        
        # 计算盈亏
        pct_from_cost = (rt['price'] - pos['cost']) / pos['cost'] * 100
        profit = (rt['price'] - pos['cost']) * pos['qty']
        rush_ratio = calc_rush_ratio(rt['bid1_v'], rt['ask1_v'])
        
        # 止损检查
        stop_result = analyze_stop_loss(pct_from_cost, rush_ratio)
        if stop_result and stop_result['level'] != '观察':
            # 检查是否可以推送
            ok, reason = can_push(ts_code, "position")
            if ok:
                alerts.append({
                    'ts_code': ts_code,
                    'name': rt['name'],
                    'cost': pos['cost'],
                    'price': rt['price'],
                    'pct_from_cost': pct_from_cost,
                    'rush_ratio': rush_ratio,
                    'level': stop_result['level'],
                    'emoji': stop_result['emoji'],
                    'action': stop_result['action'],
                    'type': 'stop_loss'
                })
        
        # 止盈检查
        cfg = THRESHOLDS["take_profit"]
        if pct_from_cost >= cfg["action_pct"]:
            ok, reason = can_push(ts_code, "position")
            if ok:
                alerts.append({
                    'ts_code': ts_code,
                    'name': rt['name'],
                    'cost': pos['cost'],
                    'price': rt['price'],
                    'pct_from_cost': pct_from_cost,
                    'profit': profit,
                    'action': '分批止盈，落袋为安',
                    'type': 'take_profit'
                })
        elif pct_from_cost >= cfg["remind_pct"]:
            ok, reason = can_push(ts_code, "position")
            if ok:
                alerts.append({
                    'ts_code': ts_code,
                    'name': rt['name'],
                    'cost': pos['cost'],
                    'price': rt['price'],
                    'pct_from_cost': pct_from_cost,
                    'profit': profit,
                    'action': '可以考虑减仓',
                    'type': 'take_profit'
                })
    
    return alerts

def check_auction() -> List[Dict]:
    """检查集合竞价机会"""
    opportunities = []
    watchlist = get_watchlist()
    cfg = THRESHOLDS["auction"]
    
    for stock in watchlist:
        ts_code = stock['ts_code']
        
        # 检查冷却
        ok, reason = can_push(ts_code, "watchlist")
        if not ok:
            continue
        
        # 获取数据
        rt = get_realtime(ts_code)
        if not rt:
            continue
        
        rush_ratio = calc_rush_ratio(rt['bid1_v'], rt['ask1_v'])
        if rush_ratio is None:
            continue
        
        # 买一金额
        amount = rt['bid1_p'] * rt['bid1_v'] * 100
        
        # 检查条件
        if rt['pct'] >= cfg['min_pct'] and rush_ratio >= cfg['min_ratio'] and amount >= cfg['min_amount']:
            limit_price, board = calc_limit_price(rt['pre_close'], ts_code)
            tactics = analyze_tactics(rt['pct'], rush_ratio)
            
            opportunities.append({
                'ts_code': ts_code,
                'name': rt['name'],
                'pct': rt['pct'],
                'rush_ratio': rush_ratio,
                'limit_price': limit_price,
                'signal': tactics['signal'],
                'emoji': tactics['emoji'],
                'reason': tactics['reason']
            })
    
    return opportunities

def check_watchlist_intraday(market_trend: str, is_afternoon: bool) -> List[Dict]:
    """检查自选股盘中机会"""
    opportunities = []
    watchlist = get_watchlist()
    cfg = THRESHOLDS["watchlist"]
    
    for stock in watchlist:
        ts_code = stock['ts_code']
        
        # 检查冷却
        ok, reason = can_push(ts_code, "watchlist")
        if not ok:
            continue
        
        # 获取数据
        rt = get_realtime(ts_code)
        if not rt:
            continue
        
        rush_ratio = calc_rush_ratio(rt['bid1_v'], rt['ask1_v'])
        
        # 获取V9评分
        score, decision = get_v9_score(ts_code)
        
        # 战术分析
        tactics = analyze_tactics(rt['pct'], rush_ratio, score, market_trend, is_afternoon)
        
        # ====== V10修复：涨跌停特殊处理 ======
        should_push = False
        push_priority = 1  # 推送优先级
        push_message = None  # 特殊推送内容
        
        # 最高优先级：涨停板（不受评分限制）
        if rt['pct'] >= 9.8:
            should_push = True
            push_priority = 5
            # 判断封单强度
            seal_strength = "强" if rush_ratio and rush_ratio > 10 else "弱"
            tactics = {
                'signal': '涨停板',
                'emoji': '🚀',
                'reason': f'涨停封板，封单{seal_strength}',
                'level': 5
            }
            # 生成涨停推送内容
            push_message = f"【涨停板】{rt['name']}\n"
            push_message += f"封单强度: {seal_strength}\n"
            push_message += f"买一: {rt.get('bid1_v', 0)}手\n"
            push_message += f"卖一: {rt.get('ask1_v', 0)}手\n"
            push_message += "建议: 持有待连板，不追高"
        
        # 次高优先级：跌停板（风险警告）
        elif rt['pct'] <= -9.8:
            should_push = True
            push_priority = 5
            # 判断是否有资金抄底
            bottom_fishing = rush_ratio and rush_ratio > 5
            tactics = {
                'signal': '跌停板',
                'emoji': '💀',
                'reason': '跌停风险' + ('，但有资金抄底' if bottom_fishing else '，注意止损'),
                'level': 5
            }
            # 生成跌停推送内容
            push_message = f"【跌停板】{rt['name']}\n"
            if bottom_fishing:
                push_message += f"⚠️ 有资金抄底，抢筹比{rush_ratio:.1f}\n"
                push_message += "建议: 激进者可小仓试探"
            else:
                push_message += "💀 无资金接盘\n"
                push_message += "建议: 立即止损，不要幻想"
        
        # 准涨停（8%-9.8%）
        elif rt['pct'] >= 8.0:
            should_push = True
            push_priority = 4
            distance_to_limit = 10.0 - rt['pct']
            tactics = {
                'signal': '冲击涨停',
                'emoji': '🔥',
                'reason': f'涨{rt["pct"]:.1f}%，距涨停{distance_to_limit:.1f}%',
                'level': 4
            }
            push_message = f"【冲击涨停】{rt['name']}\n"
            push_message += f"当前涨幅: {rt['pct']:.1f}%\n"
            push_message += f"距离涨停: {distance_to_limit:.1f}%\n"
            push_message += "建议: 持有为主，不获利了结"
        
        # 炸板检测（曾经涨停又打开）
        elif rt.get('high_pct', 0) >= 9.8 and rt['pct'] < 9.5:
            should_push = True
            push_priority = 4
            tactics = {
                'signal': '涨停炸板',
                'emoji': '💥',
                'reason': f'涨停炸板，当前{rt["pct"]:.1f}%',
                'level': 4
            }
            push_message = f"【涨停炸板】{rt['name']}\n"
            push_message += f"最高: {rt.get('high_pct', 0):.1f}%\n"
            push_message += f"当前: {rt['pct']:.1f}%\n"
            push_message += "建议: 观察封板力度，弱则减仓"
        
        # 大涨（5%-8%）
        elif rt['pct'] >= 5.0:
            if score >= 65:  # 降低评分要求
                should_push = True
                push_priority = 3
                push_message = f"【强势上涨】{rt['name']}\n"
                push_message += f"涨幅: {rt['pct']:.1f}% | 评分: {score}\n"
                push_message += "建议: 持有为主，可适当加仓"
        
        # 大跌（-5%以下）
        elif rt['pct'] <= -5.0:
            if rush_ratio and rush_ratio > 5:  # 大跌但有资金抄底
                should_push = True
                push_priority = 3
                tactics = {
                    'signal': '超跌抄底',
                    'emoji': '💎',
                    'reason': f'跌{abs(rt["pct"]):.1f}%但资金抢筹',
                    'level': 3
                }
                push_message = f"【超跌反弹】{rt['name']}\n"
                push_message += f"跌幅: {rt['pct']:.1f}%\n"
                push_message += f"抢筹比: {rush_ratio:.1f}\n"
                push_message += "建议: 激进者可小仓抄底"
        
        # 原有条件（评分和抢筹）
        else:
            # 条件1：涨幅+抢筹比达标
            if rt['pct'] >= cfg['min_pct'] and rush_ratio and rush_ratio >= cfg['min_ratio']:
                should_push = True
                push_priority = 2
            
            # 条件2：V9高分
            if score >= cfg['min_score'] and rt['pct'] > 0:
                should_push = True
                push_priority = 2
            
            # 条件3：黄金坑信号
            if tactics['signal'] == '黄金坑':
                should_push = True
                push_priority = 3
            
            # 条件4：重要信号（level >= 4）
            if tactics['level'] >= 4:
                should_push = True
                push_priority = tactics['level']
        
        # 排除诱多信号
        if '诱多' in tactics['signal']:
            should_push = False  # 诱多不推买入，但可以单独警告
        
        if should_push:
            limit_price, board = calc_limit_price(rt['pre_close'], ts_code)
            opportunities.append({
                'ts_code': ts_code,
                'name': rt['name'],
                'price': rt['price'],
                'pct': rt['pct'],
                'rush_ratio': rush_ratio or 0,
                'score': score,
                'limit_price': limit_price,
                'signal': tactics['signal'],
                'emoji': tactics['emoji'],
                'reason': tactics['reason'],
                'source': '自选股',
                'level': tactics['level']
            })
    
    # 按重要程度排序
    opportunities.sort(key=lambda x: x['level'], reverse=True)
    return opportunities[:5]  # 最多5个

def check_market_recommend() -> List[Dict]:
    """检查全市场推荐"""
    try:
        resp = requests.get(f"{API_BASE}/api/recommend", timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('success') and data.get('stocks'):
                result = []
                for stock in data['stocks'][:3]:  # 最多3个
                    ts_code = stock['ts_code']
                    
                    # 检查冷却
                    ok, reason = can_push(ts_code, "market")
                    if not ok:
                        continue
                    
                    # 检查评分门槛
                    if stock.get('score', 0) < THRESHOLDS["market"]["min_score"]:
                        continue
                    
                    # 获取实时数据补充
                    rt = get_realtime(ts_code)
                    if rt:
                        limit_price, board = calc_limit_price(rt['pre_close'], ts_code)
                        plain_strategy, plain_reason = translate_to_plain(
                            stock.get('type', '推荐'),
                            stock.get('reason', '综合看涨')
                        )
                        
                        result.append({
                            'ts_code': ts_code,
                            'name': stock['name'],
                            'price': rt['price'],
                            'pct': rt['pct'],
                            'score': stock['score'],
                            'limit_price': limit_price,
                            'signal': plain_strategy,
                            'emoji': '⭐',
                            'reason': plain_reason,
                            'source': '全市场'
                        })
                
                return result
    except Exception as e:
        print(f"  获取全市场推荐失败: {e}")
    
    return []

# ==================== 时间判断 ====================

def is_auction_time() -> bool:
    """是否竞价时间 9:23-9:25"""
    now = datetime.datetime.now().time()
    return datetime.time(9, 23) <= now <= datetime.time(9, 25, 59)

def is_trading_time() -> bool:
    """是否交易时间"""
    now = datetime.datetime.now().time()
    morning = datetime.time(9, 30) <= now <= datetime.time(11, 30)
    afternoon = datetime.time(13, 0) <= now <= datetime.time(14, 57)
    return morning or afternoon

def is_afternoon() -> bool:
    """是否下午盘（用于尾盘诱多判断）"""
    now = datetime.datetime.now().time()
    return now >= datetime.time(14, 0)

# ==================== 主循环 ====================

def run():
    """主运行循环"""
    print("=" * 60)
    print("🤖 V9 智能哨兵 (融合版)")
    print("=" * 60)
    print("✨ 功能：")
    print("  1. 竞价监控 - 极简4行推送")
    print("  2. 盘中监控 - 结合V9评分")
    print("  3. 持仓止损止盈 - 分级预警")
    print("  4. 战术识别 - 诱多/黄金坑/抢筹")
    print("  5. 智能冷却 - SQLite持久化")
    print("=" * 60)
    print("📊 阈值配置：")
    print(f"  竞价：涨幅≥{THRESHOLDS['auction']['min_pct']}%, 买卖比≥{THRESHOLDS['auction']['min_ratio']}")
    print(f"  盘中：涨幅≥{THRESHOLDS['watchlist']['min_pct']}%, 买卖比≥{THRESHOLDS['watchlist']['min_ratio']}, 评分≥{THRESHOLDS['watchlist']['min_score']}")
    print(f"  止损：{THRESHOLDS['stop_loss']['warn_pct']}%警告, {THRESHOLDS['stop_loss']['action_pct']}%行动")
    print("=" * 60)
    
    # 初始化
    init_db()
    clean_old_records()
    
    last_heartbeat = 0
    
    while True:
        try:
            now = time.time()
            dt = datetime.datetime.now()
            
            # 心跳日志（每分钟）
            if now - last_heartbeat > 60:
                print(f"[{dt.strftime('%H:%M:%S')}] 🟢 运行中...")
                last_heartbeat = now
            
            # 获取大盘状态
            market = get_market_status()
            market_trend = market['trend']
            afternoon = is_afternoon()
            
            # ===== 1. 竞价时间 =====
            if is_auction_time():
                print(f"[{dt.strftime('%H:%M:%S')}] 🔔 竞价监控...")
                opps = check_auction()
                if opps:
                    msg = format_auction_msg(opps)
                    for opp in opps:
                        send_push(
                            f"竞价信号 - {opp['name']}",
                            msg,
                            opp['ts_code'],
                            "watchlist"
                        )
                        break  # 竞价期间只推一条
            
            # ===== 2. 交易时间 =====
            if is_trading_time():
                # 2.1 持仓监控
                position_alerts = check_positions(market_trend)
                for alert in position_alerts:
                    if alert['type'] == 'stop_loss':
                        msg = format_stop_loss_msg(alert)
                        send_push(f"止损预警 - {alert['name']}", msg, alert['ts_code'], "position")
                    elif alert['type'] == 'take_profit':
                        msg = format_take_profit_msg(alert)
                        send_push(f"止盈提醒 - {alert['name']}", msg, alert['ts_code'], "position")
                
                # 2.2 自选股监控
                watchlist_opps = check_watchlist_intraday(market_trend, afternoon)
                if watchlist_opps:
                    # 只推最重要的
                    top = watchlist_opps[0]
                    msg = format_intraday_msg([top])
                    send_push(f"盘中信号 - {top['name']}", msg, top['ts_code'], "watchlist")
                
                # 2.3 全市场推荐（每30分钟检查一次）
                minute = dt.minute
                if minute in [0, 30]:
                    market_opps = check_market_recommend()
                    if market_opps:
                        top = market_opps[0]
                        msg = format_intraday_msg([top])
                        send_push(f"市场精选 - {top['name']}", msg, top['ts_code'], "market")
            
            # 休息
            sleep_time = 15 if is_auction_time() else (30 if is_trading_time() else 60)
            time.sleep(sleep_time)
            
        except KeyboardInterrupt:
            print("\n👋 哨兵已停止")
            break
        except Exception as e:
            print(f"❌ 错误: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(10)

if __name__ == "__main__":
    run()
