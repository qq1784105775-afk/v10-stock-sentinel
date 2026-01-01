# -*- coding: utf-8 -*-
"""
V9升级：多因子评分引擎 (融合版)
=================================
融合了两个版本的优点：
1. 旧版本的11个完整因子
2. 新版本的诱多/挖坑/高危检测
3. 新版本的动态权重调整
4. 新版本的五维意图分析
5. 新增：RSI/MACD/布林带等技术指标
"""

import numpy as np
from typing import Dict, List, Tuple, Any
from enum import Enum

# ============ 技术指标计算函数 ============

def calculate_rsi(prices: List[float], period: int = 14) -> Tuple[float, str]:
    """
    计算RSI相对强弱指数（修复：使用标准计算方法）
    返回: (RSI值, 信号描述)
    """
    if len(prices) < period + 1:
        return 50.0, "数据不足"
    
    # 计算价格变化
    deltas = np.diff(prices[-period-1:])
    
    # 修复：使用平均值而非总和
    gains = deltas[deltas > 0]
    losses = -deltas[deltas < 0]
    
    avg_gain = gains.mean() if len(gains) > 0 else 0
    avg_loss = losses.mean() if len(losses) > 0 else 0.001  # 避免除零
    
    if avg_loss == 0:
        return 100.0, "极度超买"
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    # 生成信号
    if rsi > 80:
        signal = "严重超买"
    elif rsi > 70:
        signal = "超买"
    elif rsi < 20:
        signal = "严重超卖"
    elif rsi < 30:
        signal = "超卖"
    else:
        signal = "中性"
    
    return round(rsi, 2), signal

def calculate_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[float, float, str]:
    """
    计算MACD指标
    返回: (MACD值, 信号线, 信号描述)
    """
    if len(prices) < slow + signal:
        return 0.0, 0.0, "数据不足"
    
    # 计算EMA
    def ema(data, period):
        alpha = 2 / (period + 1)
        ema_values = [data[0]]
        for price in data[1:]:
            ema_values.append(price * alpha + ema_values[-1] * (1 - alpha))
        return ema_values
    
    prices_array = prices[-slow-signal:]
    ema_fast = ema(prices_array, fast)
    ema_slow = ema(prices_array, slow)
    
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = ema(macd_line, signal)
    
    current_macd = macd_line[-1]
    current_signal = signal_line[-1]
    histogram = current_macd - current_signal
    
    # 判断金叉死叉
    prev_macd = macd_line[-2] if len(macd_line) > 1 else current_macd
    prev_signal = signal_line[-2] if len(signal_line) > 1 else current_signal
    
    if prev_macd <= prev_signal and current_macd > current_signal:
        signal_desc = "金叉买入"
    elif prev_macd >= prev_signal and current_macd < current_signal:
        signal_desc = "死叉卖出"
    elif histogram > 0:
        signal_desc = "多头"
    else:
        signal_desc = "空头"
    
    return current_macd, current_signal, signal_desc

def calculate_bollinger_bands(prices: List[float], period: int = 20, std_dev: int = 2) -> Tuple[float, float, float, str]:
    """
    计算布林带
    返回: (上轨, 中轨, 下轨, 信号描述)
    """
    if len(prices) < period:
        return 0, 0, 0, "数据不足"
    
    recent_prices = prices[-period:]
    middle = np.mean(recent_prices)
    std = np.std(recent_prices)
    
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    
    current_price = prices[-1]
    
    # 生成信号
    band_width = (upper - lower) / middle * 100
    position = (current_price - lower) / (upper - lower) * 100 if upper != lower else 50
    
    if current_price > upper:
        signal = "触顶回调"
    elif current_price < lower:
        signal = "触底反弹"
    elif band_width < 5:
        signal = "带宽收窄"
    elif position > 80:
        signal = "接近上轨"
    elif position < 20:
        signal = "接近下轨"
    else:
        signal = "中轨运行"
    
    return upper, middle, lower, signal

# ============ 市场状态枚举 ============
class MarketRegime(Enum):
    BULL = "bull"
    BEAR = "bear"
    SHOCK = "shock"

CURRENT_REGIME = MarketRegime.SHOCK

# ============ V10新增：因子标签系统 ============
# 每个因子必须带解释标签：类别 + 适用市场
FACTOR_LABELS = {
    "trend": {
        "name": "趋势因子",
        "category": "trend",           # trend/reversal/sentiment
        "applicable_market": ["bull", "shock"],  # 适用市场
        "description": "均线排列 + 动量方向",
        "can_trigger_buy": False,      # 是否能单独触发买入（趋势只能确认，不能触发）
    },
    "volume": {
        "name": "量能因子",
        "category": "sentiment",
        "applicable_market": ["bull", "shock", "bear"],
        "description": "成交量变化反映市场情绪",
        "can_trigger_buy": False,
    },
    "position": {
        "name": "位置因子",
        "category": "reversal",
        "applicable_market": ["shock", "bear"],
        "description": "价格所处历史位置",
        "can_trigger_buy": False,
    },
    "chip": {
        "name": "筹码因子",
        "category": "trend",
        "applicable_market": ["bull", "shock"],
        "description": "获利盘分布",
        "can_trigger_buy": False,      # 筹码降级使用：只用于趋势确认和风险提示
    },
    "money": {
        "name": "资金因子",
        "category": "sentiment",
        "applicable_market": ["bull", "shock", "bear"],
        "description": "主力资金流向",
        "can_trigger_buy": True,       # 资金可以触发买入
    },
    "market": {
        "name": "大盘同步因子",
        "category": "sentiment",
        "applicable_market": ["bull", "shock", "bear"],
        "description": "与大盘的相对强弱",
        "can_trigger_buy": False,
    },
}

# ============ 权重配置 ============
# V10优化：提高资金因子权重（最可靠），降低位置因子权重（最不可靠）
BASE_WEIGHTS = {
    "trend": 0.18,      # 趋势（均线+动量）↓ 趋势滞后性
    "volume": 0.15,     # 量能（量比+量价配合）
    "position": 0.10,   # 位置 ↓ 位置因子准确性低
    "chip": 0.17,       # 筹码 ↓ 筹码数据精度有限
    "money": 0.25,      # 资金 ↑ 资金流向最可靠
    "market": 0.15      # 大盘同步 ↑ 系统性风险重要
}

# V10新增：因子有效性阈值（低于此值的因子不参与评分）
FACTOR_VALIDITY_THRESHOLD = {
    "trend": 0.3,       # 趋势因子最小贡献
    "volume": 0.2,
    "position": 0.2,
    "chip": 0.3,
    "money": 0.4,       # 资金因子要求更高
    "market": 0.2
}

# 市场状态调整系数（动态权重）
REGIME_ADJUSTMENTS = {
    MarketRegime.BULL: {"trend": 1.3, "chip": 0.8, "position": 0.7, "money": 1.2},
    MarketRegime.BEAR: {"money": 1.5, "chip": 1.2, "position": 1.3, "trend": 0.6},
    MarketRegime.SHOCK: {"volume": 1.2, "chip": 1.1, "money": 1.3}
}

def get_adjusted_weights() -> Dict[str, float]:

    """获取根据市场状态调整后的权重"""
    weights = BASE_WEIGHTS.copy()
    adjustments = REGIME_ADJUSTMENTS.get(CURRENT_REGIME, {})
    for key, mult in adjustments.items():
        if key in weights:
            weights[key] *= mult
    total = sum(weights.values())
    return {k: v/total for k, v in weights.items()}

# ============ 工具函数 ============
def calc_ma(prices: List[float], period: int) -> float:
    if len(prices) < period:
        return 0
    return sum(prices[-period:]) / period

# ============ 旧版本的完整因子 ============

def factor_ma_alignment(daily: List[Dict]) -> Tuple[float, str]:
    """均线多头排列因子"""
    if len(daily) < 60:
        return 50, "数据不足"
    
    closes = [d['close'] for d in daily]
    closes.reverse()
    
    ma5 = calc_ma(closes, 5)
    ma10 = calc_ma(closes, 10)
    ma20 = calc_ma(closes, 20)
    ma60 = calc_ma(closes, 60)
    
    if ma5 > ma10 > ma20 > ma60:
        return 95, "完美多头"
    elif ma5 > ma10 > ma20:
        return 80, "中期多头"
    elif ma5 > ma10:
        return 65, "短期向上"
    elif ma5 < ma10 < ma20 < ma60:
        return 10, "空头排列"
    elif ma5 < ma10 < ma20:
        return 25, "中期空头"
    elif ma5 < ma10:
        return 40, "短期走弱"
    return 50, "盘整"

def factor_momentum(daily: List[Dict]) -> Tuple[float, str]:
    """趋势动量因子"""
    if len(daily) < 20:
        return 50, "数据不足"
    
    closes = [d['close'] for d in daily]
    roc5 = (closes[0] - closes[4]) / closes[4] * 100 if closes[4] > 0 else 0
    roc10 = (closes[0] - closes[9]) / closes[9] * 100 if closes[9] > 0 else 0
    
    momentum = roc5 * 0.6 + roc10 * 0.4
    score = max(0, min(100, 50 + momentum * 3))
    
    if momentum > 5:
        signal = "强势上涨"
    elif momentum > 0:
        signal = "温和上涨"
    elif momentum > -5:
        signal = "温和下跌"
    else:
        signal = "急跌"
    
    return score, signal

def factor_position(daily: List[Dict]) -> Tuple[float, str]:
    """价格位置因子"""
    if len(daily) < 60:
        return 50, "数据不足"
    
    closes = [d['close'] for d in daily[:60]]
    current = closes[0]
    high_60 = max(closes)
    low_60 = min(closes)
    
    if high_60 <= low_60:
        return 50, "异常"
    
    position_pct = (current - low_60) / (high_60 - low_60) * 100
    score = 100 - position_pct  # 低位高分
    
    drawdown = (high_60 - current) / high_60 * 100
    
    if position_pct < 20:
        signal = f"深度低位(回撤{drawdown:.0f}%)"
    elif position_pct < 40:
        signal = "相对低位"
    elif position_pct < 60:
        signal = "中位区间"
    elif position_pct < 80:
        signal = "相对高位"
    else:
        signal = "历史高位"
    
    return score, signal

def factor_volume_ratio(daily: List[Dict]) -> Tuple[float, str]:
    """量比因子"""
    if len(daily) < 10:
        return 50, "数据不足"
    
    volumes = [d['vol'] for d in daily]
    current = volumes[0]
    avg5 = sum(volumes[1:6]) / 5 if len(volumes) >= 6 else volumes[0]
    
    if avg5 <= 0:
        return 50, "异常"
    
    ratio = current / avg5
    
    if ratio >= 3.0:
        return 95, f"巨量({ratio:.1f}倍)"
    elif ratio >= 2.0:
        return 85, f"显著放量({ratio:.1f}倍)"
    elif ratio >= 1.5:
        return 75, f"明显放量({ratio:.1f}倍)"
    elif ratio >= 1.0:
        return 60, "温和放量"
    elif ratio >= 0.7:
        return 45, "轻微缩量"
    else:
        return 25, "极度缩量"

def factor_volume_pattern(daily: List[Dict]) -> Tuple[float, str]:
    """量价配合因子"""
    if len(daily) < 5:
        return 50, "数据不足"
    
    score = 50
    signals = []
    
    for i in range(min(3, len(daily)-1)):
        p_chg = (daily[i]['close'] - daily[i+1]['close']) / daily[i+1]['close'] * 100
        v_chg = (daily[i]['vol'] - daily[i+1]['vol']) / daily[i+1]['vol'] * 100 if daily[i+1]['vol'] > 0 else 0
        
        if p_chg > 0 and v_chg > 10:
            score += 10
            if i == 0:
                signals.append("价涨量增")
        elif p_chg > 0 and v_chg < -10:
            score -= 5
            if i == 0:
                signals.append("价涨量缩")
        elif p_chg < 0 and v_chg < -10:
            score += 5
            if i == 0:
                signals.append("缩量下跌")
    
    return max(0, min(100, score)), " ".join(signals) if signals else "量价平淡"

def factor_chip_profit(cyq_data: Dict) -> Tuple[float, str]:
    """筹码获利盘因子"""
    if not cyq_data or not cyq_data.get("valid"):
        return 50, "无数据"
    
    winner = cyq_data.get("winner_rate", 50)
    
    # 修复：更合理的筹码评分逻辑
    if winner >= 90:
        # 主力完全控盘，跟随主力
        return 90, f"🚀 主力控盘({winner:.0f}%)"
    elif winner >= 70:
        # 获利盘高，趋势向上
        return 75, f"📈 获利盘高({winner:.0f}%)"
    elif winner >= 40:
        # 多空平衡，需要等待方向
        return 55, f"⚖️ 多空平衡({winner:.0f}%)"
    elif winner >= 15:
        # 套牢较多，上方压力大
        return 35, f"📉 套牢较多({winner:.0f}%)"
    else:
        # 超跌区域，可能有反弹机会，但风险也大
        return 50, f"💎 超跌区域({winner:.0f}%)"

def factor_main_flow(money_flow: List[Dict]) -> Tuple[float, str]:
    """主力资金因子"""
    if not money_flow or len(money_flow) < 3:
        return 50, "数据不足"
    
    flow_3d = sum(f.get('main_net_inflow', 0) or 0 for f in money_flow[:3])
    
    consecutive = 0
    for f in money_flow[:3]:
        if (f.get('main_net_inflow', 0) or 0) > 0:
            consecutive += 1
        else:
            break
    
    score = 50
    signals = []
    
    # 修复：阈值单位改为万元（Tushare返回万元）
    # 5000万 = 5000（万元单位的值）
    if flow_3d > 5000:  # 5000万元
        score += 35
        signals.append(f"3日流入{flow_3d:.0f}万")
    elif flow_3d > 2000:  # 2000万元
        score += 25
    elif flow_3d > 0:
        score += 10
    elif flow_3d > -2000:  # -2000万元
        score -= 10
    else:
        score -= 25
        signals.append(f"3日流出{abs(flow_3d):.0f}万")
    
    if consecutive >= 3:
        score += 15
        signals.append("连续流入")
    
    return max(0, min(100, score)), " ".join(signals) if signals else "资金观望"

def factor_market_sync(daily: List[Dict], market: List[Dict]) -> Tuple[float, str]:
    """大盘同步因子"""
    if len(daily) < 5 or not market or len(market) < 5:
        return 50, "数据不足"
    
    stock_ret = sum(d.get('change_pct', 0) for d in daily[:5])
    market_ret = sum(d.get('change_pct', 0) for d in market[:5])
    alpha = stock_ret - market_ret
    
    score = 50 + alpha * 5
    score = max(0, min(100, score))
    
    if alpha > 3:
        signal = f"跑赢大盘+{alpha:.1f}%"
    elif alpha > 0:
        signal = "略强于盘"
    elif alpha > -3:
        signal = "略弱于盘"
    else:
        signal = f"跑输大盘{alpha:.1f}%"
    
    return score, signal

# ============ 你昨天新增的逻辑 ============

def calc_tech_indicators(closes: List[float]) -> Tuple[float, str]:
    """布林带+RSI技术信号（你昨天的逻辑）"""
    if len(closes) < 30:
        return 0, "无"
    
    ma20 = sum(closes[-20:]) / 20
    std_dev = np.std(closes[-20:])
    upper = ma20 + (2 * std_dev)
    lower = ma20 - (2 * std_dev)
    current = closes[-1]
    
    # RSI计算
    deltas = np.diff(closes)
    gains = deltas[deltas > 0].sum()
    losses = -deltas[deltas < 0].sum()
    rsi = 50
    if losses > 0:
        rsi = 100 - (100 / (1 + gains / losses))
    
    ma5 = sum(closes[-5:]) / 5
    
    signal = "普通"
    score = 0
    
    if current < lower:
        signal = "触底"
        score = +25
    elif current > upper:
        signal = "触顶"
        score = -25
    elif rsi > 85:
        signal = "超买"
        score = -20
    elif rsi < 15:
        signal = "超卖"
        score = +20
    elif ma5 > ma20:
        signal = "金叉"
        score = +10
    
    return score, signal

def calc_fund_divergence(money_flow: List[Dict], pct_chg: float) -> Tuple[float, str]:
    """资金背离检测（增强版：更严格的阈值）"""
    if not money_flow:
        return 50, "正常"
    
    # net_flow 已经是万元单位（Tushare moneyflow接口返回万元）
    net = money_flow[0].get('main_net_inflow', 0)
    score = 50 + (10 if net > 0 else 0) + (10 if net > 1000 else 0)  # 1000万
    msg = "正常"
    
    # 🔥 严重诱多：大涨但主力大幅流出（阈值提高到2000万）
    if pct_chg > 3 and net < -2000:
        msg = "严重诱多"
        score -= 30
    # 一般诱多：涨但资金流出（阈值提高到1000万）
    elif pct_chg > 2 and net < -1000:
        msg = "诱多"
        score -= 20
    
    # 🔥 明显挖坑：大跌但主力大幅流入（阈值提高到2000万）
    if pct_chg < -3 and net > 2000:
        msg = "明显挖坑"
        score += 25
    # 一般挖坑：跌但资金流入（阈值提高到1000万）
    elif pct_chg < -2 and net > 1000:
        msg = "挖坑"
        score += 15
    
    return score, msg

def calc_chip_risk(cyq_data: Dict, price: float) -> Tuple[float, str]:
    """筹码风险检测（你昨天的高危逻辑）"""
    if not cyq_data:
        return 50, "正常"
    
    win = cyq_data.get('winner_rate', 50)
    cost = cyq_data.get('avg_cost', price) or price
    
    if cost > 0:
        bias = (price - cost) / cost * 100
    else:
        bias = 0
    
    msg = "正常"
    
    # 🔥 高危检测：获利盘高 + 偏离成本大
    if win > 90 and bias > 20:
        msg = "高危"
    
    return win, msg

def calc_regime(market: List[Dict]) -> str:
    """市场状态判断（你昨天的逻辑）"""
    if not market or len(market) < 20:
        return "SHOCK"
    
    closes = [d['close'] for d in market]
    ma20 = sum(closes[:20]) / len(closes[:20])
    trend = (closes[0] - ma20) / ma20 * 100
    
    if trend > 1:
        return "BULL"
    if trend < -1:
        return "BEAR"
    return "SHOCK"

# ============ 五维意图分析（你昨天的核心逻辑）============

def analyze_intent(score: float, flow_msg: str, chip_msg: str, pct_chg: float, tech_signal: str) -> str:
    """
    五维意图分析 - 综合技术+资金+筹码判断
    这是你昨天更新的核心逻辑！
    """
    # 技术信号优先
    if "触底" in tech_signal:
        return "💎铁底回补"
    if "触顶" in tech_signal:
        return "⚠️触顶回落"
    if "超买" in tech_signal:
        return "⚠️顶部风险"
    if "超卖" in tech_signal:
        return "💎黄金坑"
    
    # 资金信号
    if "诱多" in flow_msg:
        return "⚠️诱多出货"
    if "挖坑" in flow_msg:
        return "💎主力挖坑"
    
    # 筹码信号
    if "高危" in chip_msg:
        return "💣高位派发"
    
    # 趋势信号
    if "金叉" in tech_signal and score > 65:
        return "🚀趋势加速"
    
    # 评分信号
    if score > 85:
        return "🚀主升浪"
    if score > 70:
        return "✨强势拉升"
    if score < 35:
        return "🌧破位下跌"
    
    # 洗盘识别
    if 50 < score < 75 and -5 < pct_chg < 0:
        return "🛁主力洗盘"
    
    return "☁️观察等待"

# ============ 综合评分引擎（融合版）============

def calculate_v9_score(
    daily: List[Dict],
    money_flow: List[Dict],
    market: List[Dict],
    cyq_data: Dict,
    realtime_fund: Dict = None  # V10新增：实时资金数据
) -> Tuple[float, Dict[str, Any], str]:
    """
    V9多因子综合评分（增强版）
    
    融合了：
    1. 旧版本的11个完整因子
    2. 你昨天的诱多/挖坑/高危检测
    3. 你昨天的五维意图分析
    4. 你昨天的动态权重调整
    5. 新增RSI/MACD/布林带技术指标
    6. V10新增：实时资金数据优先
    """
    if not daily or len(daily) < 30:
        return 50.0, {}, "观察"
    
    try:
        # 获取动态权重
        weights = get_adjusted_weights()
        
        # ===== 旧版本的完整因子计算 =====
        ma_score, ma_sig = factor_ma_alignment(daily)
        mom_score, mom_sig = factor_momentum(daily)
        pos_score, pos_sig = factor_position(daily)
        trend_avg = (ma_score + mom_score + pos_score) / 3
        
        vol_ratio, vol_sig = factor_volume_ratio(daily)
        vol_pattern, vol_pat_sig = factor_volume_pattern(daily)
        volume_avg = (vol_ratio + vol_pattern) / 2
        
        chip_score, chip_sig = factor_chip_profit(cyq_data)
        
        # ====== V10修复：优先使用实时资金数据 ======
        if realtime_fund and realtime_fund.get('valid'):
            # 使用实时资金数据计算评分
            rt_net = realtime_fund.get('main_net', 0)  # 万元
            
            # 实时资金评分
            if rt_net > 5000:  # 5000万以上
                money_score = 95
                money_sig = f"🔥实时流入{rt_net:.0f}万"
            elif rt_net > 2000:
                money_score = 80
                money_sig = f"🟢实时流入{rt_net:.0f}万"
            elif rt_net > 500:
                money_score = 65
                money_sig = f"实时小幅流入{rt_net:.0f}万"
            elif rt_net > -500:
                money_score = 50
                money_sig = "实时资金平衡"
            elif rt_net > -2000:
                money_score = 35
                money_sig = f"实时小幅流出{abs(rt_net):.0f}万"
            else:
                money_score = 15
                money_sig = f"🔴实时大幅流出{abs(rt_net):.0f}万"
        else:
            # 没有实时数据，使用历史数据
            money_score, money_sig = factor_main_flow(money_flow)
        
        market_score, market_sig = factor_market_sync(daily, market)
        

        # ===== 新增技术指标计算 =====
        closes = [d['close'] for d in daily][::-1]
        pct_chg = daily[0].get('change_pct', 0)
        price = daily[0].get('close', 0)
        
        # RSI指标
        rsi_value, rsi_signal = calculate_rsi(closes)
        rsi_score = 50  # 默认中性
        if rsi_value < 30:
            rsi_score = 80  # 超卖买入
        elif rsi_value > 70:
            rsi_score = 20  # 超买卖出
        else:
            rsi_score = 50 + (50 - rsi_value) * 0.5  # 线性调整
        
        # MACD指标
        macd_val, signal_val, macd_signal = calculate_macd(closes)
        macd_score = 50
        if "金叉" in macd_signal:
            macd_score = 85
        elif "死叉" in macd_signal:
            macd_score = 15
        elif macd_val > signal_val:
            macd_score = 65
        else:
            macd_score = 35
        
        # 布林带指标
        bb_upper, bb_middle, bb_lower, bb_signal = calculate_bollinger_bands(closes)
        bb_score = 50
        if "触底" in bb_signal:
            bb_score = 80
        elif "触顶" in bb_signal:
            bb_score = 20
        elif "带宽收窄" in bb_signal:
            bb_score = 60  # 即将变盘
        
        # 技术指标综合（权重：RSI 40%, MACD 40%, BB 20%）
        tech_indicator_score = rsi_score * 0.4 + macd_score * 0.4 + bb_score * 0.2
        
        # ===== 原有的技术指标修正 =====
        tech_fix, tech_signal = calc_tech_indicators(closes)
        
        # 合并技术信号
        combined_tech_signal = f"{tech_signal}, RSI:{rsi_signal}, MACD:{macd_signal}, BB:{bb_signal}"
        
        # 资金背离检测（诱多/挖坑）
        divergence_score, flow_msg = calc_fund_divergence(money_flow, pct_chg)
        
        # 筹码风险检测（高危）
        chip_win, chip_msg = calc_chip_risk(cyq_data, price)
        
        # ===== 加权计算（修复：权重正确归一化） =====
        # 基础六因子占80%权重，技术指标占20%权重
        base_factor_score = (
            trend_avg * weights["trend"] +
            volume_avg * weights["volume"] +
            pos_score * weights["position"] +
            chip_score * weights["chip"] +
            money_score * weights["money"] +
            market_score * weights["market"]
        )
        
        # 综合评分 = 基础因子80% + 技术指标20%
        base_score = base_factor_score * 0.8 + tech_indicator_score * 0.2
        
        # 应用技术修正 + 背离修正
        final_score = base_score + tech_fix
        
        # 诱多扣分
        if flow_msg == "诱多":
            final_score -= 15
        # 挖坑加分
        elif flow_msg == "挖坑":
            final_score += 10
        
        # 高危扣分
        if chip_msg == "高危":
            final_score -= 10
        
        final_score = max(1, min(99, final_score))
        
        # ===== 生成决策 =====
        breakdown = {
            "trend": round(trend_avg, 1),
            "volume": round(volume_avg, 1),
            "position": round(pos_score, 1),
            "chip": round(chip_score, 1),
            "money": round(money_score, 1),
            "market": round(market_score, 1),
            "tech_signal": tech_signal,
            "flow_msg": flow_msg,
            "chip_msg": chip_msg
        }
        
        # 使用你昨天的五维意图分析
        decision = analyze_intent(final_score, flow_msg, chip_msg, pct_chg, tech_signal)
        
        return round(final_score, 1), breakdown, decision
        
    except Exception as e:
        return 50.0, {"error": str(e)}, "观察"

# ============ 辅助函数 ============

def set_market_regime(regime: str):
    """设置市场状态"""
    global CURRENT_REGIME
    regime_map = {
        "bull": MarketRegime.BULL,
        "bear": MarketRegime.BEAR,
        "shock": MarketRegime.SHOCK
    }
    CURRENT_REGIME = regime_map.get(regime, MarketRegime.SHOCK)

def get_current_regime() -> str:
    """获取当前市场状态"""
    return CURRENT_REGIME.value
