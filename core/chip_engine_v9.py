# -*- coding: utf-8 -*-
"""
V9升级：机构级筹码分析引擎
多源融合：Tushare官方 + VWAP估算 + 换手衰减模型
精度目标：误差 < 5%
"""

import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# 导入原有模块作为基础
from core.cyq_real import get_cyq_analysis as _original_cyq

# 融合权重
TUSHARE_WEIGHT = 0.50
VWAP_WEIGHT = 0.30  
DECAY_WEIGHT = 0.20
DECAY_HALF_LIFE = 20

def _safe_float(x, default=0.0):
    try:
        return float(x) if x is not None else default
    except:
        return default

class TurnoverDecayModel:
    """换手衰减模型"""
    
    def __init__(self, half_life: int = 20):
        self.decay_rate = math.log(2) / half_life
    
    def calculate_weight(self, days_ago: int, turnover_rate: float) -> float:
        time_decay = math.exp(-self.decay_rate * days_ago)
        turnover_factor = math.exp(-turnover_rate / 100 * 0.5)
        return time_decay * turnover_factor
    
    def estimate(self, daily_data: List[Dict], current_price: float, lookback: int = 120) -> Optional[Dict]:
        if not daily_data or len(daily_data) < 10 or current_price <= 0:
            return None
        
        data = daily_data[:lookback]
        price_volume = {}
        total_weighted = 0
        
        for i, row in enumerate(data):
            close = _safe_float(row.get('close'))
            vol = _safe_float(row.get('vol'))
            turnover = _safe_float(row.get('turnover_rate', 2))
            
            if close <= 0 or vol <= 0:
                continue
            
            weight = self.calculate_weight(i, turnover)
            weighted_vol = vol * weight
            
            price_key = round(close, 2)
            price_volume[price_key] = price_volume.get(price_key, 0) + weighted_vol
            total_weighted += weighted_vol
        
        if total_weighted <= 0:
            return None
        
        # 计算统计
        prices = sorted(price_volume.keys())
        cumulative = 0
        cost_percentiles = {}
        winner_vol = 0
        weighted_cost = 0
        
        for price in prices:
            vol = price_volume[price]
            weighted_cost += price * vol
            if price <= current_price:
                winner_vol += vol
            cumulative += vol
            pct = cumulative / total_weighted * 100
            for target in [10, 30, 50, 70, 90]:
                if target not in cost_percentiles and pct >= target:
                    cost_percentiles[target] = price
        
        avg_cost = weighted_cost / total_weighted
        winner_rate = winner_vol / total_weighted * 100
        
        # 计算集中度
        if len(prices) > 1:
            import numpy as np
            price_std = np.std(prices)
            price_mean = np.mean(prices)
            cv = price_std / price_mean if price_mean > 0 else 0
            concentration = max(0, min(100, (1 - cv) * 100))
        else:
            concentration = 100
        
        return {
            "avg_cost": round(avg_cost, 2),
            "winner_rate": round(winner_rate, 2),
            "cost_50": cost_percentiles.get(50, avg_cost),
            "cost_70": cost_percentiles.get(70, avg_cost),
            "cost_90": cost_percentiles.get(90, avg_cost),
            "concentration": round(concentration, 2),
            "source": "turnover_decay"
        }

class VWAPEstimator:
    """VWAP估算器"""
    
    def estimate(self, daily_data: List[Dict], current_price: float, window: int = 60) -> Optional[Dict]:
        if not daily_data or len(daily_data) < 10 or current_price <= 0:
            return None
        
        data = daily_data[:window]
        total_amount = 0
        total_volume = 0
        winner_volume = 0
        
        for row in data:
            close = _safe_float(row.get('close'))
            vol = _safe_float(row.get('vol'))
            amount = _safe_float(row.get('amount'))
            
            if close <= 0 or vol <= 0:
                continue
            
            total_volume += vol
            total_amount += amount
            if close <= current_price:
                winner_volume += vol
        
        if total_volume <= 0:
            return None
        
        avg_cost = (total_amount * 10) / total_volume
        winner_rate = (winner_volume / total_volume) * 100
        
        return {
            "avg_cost": round(avg_cost, 2),
            "winner_rate": round(winner_rate, 2),
            "source": "vwap"
        }

def get_cyq_analysis_v9(
    ts_code: str,
    pro=None,
    daily_rows: List[Dict] = None,
    current_price: float = 0.0
) -> Dict[str, Any]:
    """
    V9升级版筹码分析
    多源融合：官方数据 + VWAP + 换手衰减
    """
    results = []
    weights = []
    
    # 1. 尝试原有方法（含Tushare官方）
    original = _original_cyq(ts_code, pro=pro, daily_rows=daily_rows, current_price=current_price)
    if original.get('valid') and original.get('source') == 'tushare_cyq_perf':
        results.append(original)
        weights.append(TUSHARE_WEIGHT)
    
    # 2. VWAP估算
    vwap = VWAPEstimator().estimate(daily_rows or [], current_price)
    if vwap:
        results.append(vwap)
        w = VWAP_WEIGHT if results else VWAP_WEIGHT + TUSHARE_WEIGHT * 0.6
        weights.append(w)
    
    # 3. 换手衰减模型
    decay = TurnoverDecayModel().estimate(daily_rows or [], current_price)
    if decay:
        results.append(decay)
        w = DECAY_WEIGHT if len(results) > 1 else DECAY_WEIGHT + TUSHARE_WEIGHT * 0.4
        weights.append(w)
    
    # 无数据
    if not results:
        return original if original else {"avg_cost": 0, "winner_rate": 0, "desc": "无数据", "valid": False}
    
    # 归一化权重
    total_w = sum(weights)
    norm_weights = [w / total_w for w in weights]
    
    # 融合计算
    avg_cost = sum(r.get("avg_cost", 0) * w for r, w in zip(results, norm_weights))
    winner_rate = sum(r.get("winner_rate", 0) * w for r, w in zip(results, norm_weights))
    
    # 获取额外信息
    concentration = 50
    cost_50 = avg_cost
    for r in results:
        if "concentration" in r:
            concentration = r["concentration"]
        if "cost_50" in r:
            cost_50 = r["cost_50"]
    
    # 置信度
    confidence = 0.3 + 0.25 * len(results)
    if any(r.get("source") == "tushare_cyq_perf" for r in results):
        confidence += 0.2
    confidence = min(1.0, confidence)
    
    # 描述
    if winner_rate >= 90:
        desc = f"🚀 获利盘{winner_rate:.0f}%，主力完全控盘"
    elif winner_rate >= 70:
        desc = f"📈 获利盘{winner_rate:.0f}%，上行通道"
    elif winner_rate >= 40:
        desc = f"⚖️ 获利盘{winner_rate:.0f}%，多空平衡"
    elif winner_rate >= 15:
        desc = f"📉 获利盘{winner_rate:.0f}%，承压区间"
    else:
        desc = f"💎 获利盘{winner_rate:.0f}%，超跌区域"
    
    sources = [r.get("source", "unknown") for r in results]
    
    return {
        "avg_cost": round(avg_cost, 2),
        "winner_rate": round(winner_rate, 2),
        "cost_50": round(cost_50, 2),
        "concentration": round(concentration, 2),
        "confidence": round(confidence, 2),
        "desc": desc,
        "valid": True,
        "source": "+".join(sources),
        "v9_enhanced": True
    }


# ====== V10新增：筹码参与决策闭环（问题#18）======
def get_chip_decision_signal(cyq_data: Dict, current_price: float = 0) -> Dict:
    """
    筹码参与决策闭环
    
    问题#18：筹码变化未参与决策闭环，只展示，不决定生死
    修复：输出明确的决策信号，而不是仅仅展示
    
    输出信号类型：
    - VETO: 否决买入（风险信号）
    - CONFIRM: 确认买入（趋势确认）
    - NEUTRAL: 中性（不影响决策）
    - WARNING: 风险提示（但不否决）
    
    Returns:
        {
            'signal': 'VETO'|'CONFIRM'|'WARNING'|'NEUTRAL',
            'description': str,
            'risk_level': 0-100,
            'can_affect_decision': bool
        }
    """
    if not cyq_data or not cyq_data.get('valid'):
        return {
            'signal': 'NEUTRAL',
            'description': '筹码数据无效',
            'risk_level': 50,
            'can_affect_decision': False
        }
    
    winner_rate = cyq_data.get('winner_rate', 50)
    avg_cost = cyq_data.get('avg_cost', 0)
    concentration = cyq_data.get('concentration', 50)
    
    # 计算风险等级
    risk_level = 50
    
    # ====== 否决信号 ======
    # 获利盘极高 + 股价远高于成本 = 抛压风险
    if winner_rate >= 95:
        if current_price > 0 and avg_cost > 0:
            premium = (current_price - avg_cost) / avg_cost * 100
            if premium > 20:  # 溢价20%以上
                return {
                    'signal': 'VETO',
                    'description': f'🚨 获利盘{winner_rate:.0f}%+溢价{premium:.0f}%，抛压极大',
                    'risk_level': 90,
                    'can_affect_decision': True
                }
    
    # ====== 风险警告 ======
    if winner_rate >= 85:
        return {
            'signal': 'WARNING',
            'description': f'⚠️ 获利盘{winner_rate:.0f}%，高位风险',
            'risk_level': 70,
            'can_affect_decision': True
        }
    
    # ====== 确认信号 ======
    # 低获利盘 + 主力成本区 = 超跌确认
    if winner_rate <= 20:
        return {
            'signal': 'CONFIRM',
            'description': f'💎 获利盘{winner_rate:.0f}%，超跌区域可关注',
            'risk_level': 30,
            'can_affect_decision': True
        }
    
    # 筹码高度集中 = 主力控盘
    if concentration >= 80 and 30 <= winner_rate <= 70:
        return {
            'signal': 'CONFIRM',
            'description': f'📈 筹码集中度{concentration:.0f}%，主力控盘',
            'risk_level': 40,
            'can_affect_decision': True
        }
    
    # ====== 中性 ======
    return {
        'signal': 'NEUTRAL',
        'description': f'获利盘{winner_rate:.0f}%，位置中性',
        'risk_level': 50,
        'can_affect_decision': False
    }


def chip_affects_verdict(chip_signal: Dict, original_action: str) -> tuple:
    """
    筹码信号影响最终裁决
    
    Args:
        chip_signal: get_chip_decision_signal的输出
        original_action: 原始决策动作
        
    Returns:
        (新动作, 新动作分类, 是否被修改)
    """
    signal = chip_signal.get('signal', 'NEUTRAL')
    
    # 否决信号：强制降级
    if signal == 'VETO' and original_action in ['搞！', '主升浪', '强势上涨']:
        return '⚠️ 筹码否决', 'watch', True
    
    # 警告信号：看多降级
    if signal == 'WARNING' and original_action in ['搞！']:
        return '谨慎看多', 'watch', True
    
    return original_action, None, False

