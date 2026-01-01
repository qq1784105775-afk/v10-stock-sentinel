# -*- coding: utf-8 -*-
"""
V10 Ultra Pro：胜率模型 (Win Rate Model)
========================================
不再使用简单加权求和
输出三项核心指标：
1. Win_Prob（胜率）
2. Exp_Return（期望收益）
3. Max_Drawdown_Risk（最大回撤风险）
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import numpy as np
from datetime import datetime


@dataclass
class WinRateResult:
    """胜率模型输出"""
    win_prob: float          # 胜率 0-1
    exp_return: float        # 期望收益 -10% ~ +20%
    max_dd_risk: float       # 最大回撤风险 0-1
    confidence: float        # 模型置信度
    signal: str              # 信号描述
    details: Dict            # 详细分解


class WinRateModel:
    """
    胜率预测模型
    
    基于历史统计和因子分析，而非简单加权
    """
    
    # ====== 历史统计参数（V10优化：降低乐观估计）======
    FACTOR_WIN_RATES = {
        # 资金流相关（V10优化：降低胜率估计）
        'fund_flow_strong_buy': 0.62,      # 大幅流入 ↓ (原0.68)
        'fund_flow_buy': 0.54,             # 小幅流入 ↓ (原0.58)
        'fund_flow_neutral': 0.45,         # 中性 ↓ (原0.48)
        'fund_flow_sell': 0.32,            # 小幅流出 ↓ (原0.35)
        'fund_flow_strong_sell': 0.18,     # 大幅流出 ↓ (原0.22)
        
        # 趋势相关（V10优化：趋势追踪滞后，降低权重）
        'trend_strong_up': 0.58,           # 强势上涨 ↓ (原0.65)
        'trend_up': 0.52,                  # 温和上涨 ↓ (原0.56)
        'trend_neutral': 0.48,             # 震荡
        'trend_down': 0.38,                # 下跌
        'trend_strong_down': 0.28,         # 急跌
        
        # 技术信号（V10优化：单一技术信号不可靠）
        'macd_golden_cross': 0.55,         # MACD金叉 ↓ (原0.62)
        'macd_dead_cross': 0.42,           # MACD死叉
        'rsi_oversold': 0.52,              # RSI超卖 ↓ (原0.58)
        'rsi_overbought': 0.40,            # RSI超买
        'bollinger_bottom': 0.54,          # 布林下轨 ↓ (原0.60)
        'bollinger_top': 0.32,             # 布林上轨
        
        # 筹码相关（V10优化：筹码数据精度有限）
        'chip_high_profit': 0.48,          # 高获利盘 ↓ (原0.55) => 警惕抛压
        'chip_low_profit': 0.52,           # 低获利盘（可能超跌）
        
        # 市场状态
        'market_bull': 0.56,               # ↓ (原0.60)
        'market_shock': 0.48,              # ↓ (原0.50)
        'market_bear': 0.35,               # ↓ (原0.38)
    }
    
    # 期望收益参数
    FACTOR_EXP_RETURNS = {
        'fund_flow_strong_buy': 0.08,
        'fund_flow_buy': 0.04,
        'fund_flow_neutral': 0.01,
        'fund_flow_sell': -0.02,
        'fund_flow_strong_sell': -0.05,
        
        'trend_strong_up': 0.06,
        'trend_up': 0.03,
        'trend_neutral': 0.00,
        'trend_down': -0.02,
        'trend_strong_down': -0.04,
    }
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.historical_accuracy = 0.52  # 历史预测准确率
    
    def classify_fund_flow(self, main_net: float) -> str:
        """资金流分类"""
        if main_net > 5000:
            return 'fund_flow_strong_buy'
        elif main_net > 1000:
            return 'fund_flow_buy'
        elif main_net > -1000:
            return 'fund_flow_neutral'
        elif main_net > -5000:
            return 'fund_flow_sell'
        else:
            return 'fund_flow_strong_sell'
    
    def classify_trend(self, 
                       ma5: float, 
                       ma10: float, 
                       ma20: float,
                       change_pct: float) -> str:
        """趋势分类"""
        if ma5 > ma10 > ma20 and change_pct > 3:
            return 'trend_strong_up'
        elif ma5 > ma10 and change_pct > 0:
            return 'trend_up'
        elif ma5 < ma10 < ma20 and change_pct < -3:
            return 'trend_strong_down'
        elif ma5 < ma10 and change_pct < 0:
            return 'trend_down'
        else:
            return 'trend_neutral'
    
    def classify_tech_signal(self,
                             rsi: float = 50,
                             macd_signal: str = "",
                             bb_position: float = 50) -> List[str]:
        """技术信号分类"""
        signals = []
        
        if rsi < 30:
            signals.append('rsi_oversold')
        elif rsi > 70:
            signals.append('rsi_overbought')
        
        if '金叉' in macd_signal:
            signals.append('macd_golden_cross')
        elif '死叉' in macd_signal:
            signals.append('macd_dead_cross')
        
        if bb_position < 20:
            signals.append('bollinger_bottom')
        elif bb_position > 80:
            signals.append('bollinger_top')
        
        return signals if signals else ['trend_neutral']
    
    def calculate_win_probability(self, factors: List[str]) -> Tuple[float, Dict]:
        """
        计算综合胜率
        
        使用贝叶斯更新方法，而非简单平均
        """
        if not factors:
            return 0.5, {}
        
        # 基础胜率（先验）
        base_prob = 0.5
        odds = base_prob / (1 - base_prob)  # 转换为赔率
        
        details = {}
        for factor in factors:
            factor_prob = self.FACTOR_WIN_RATES.get(factor, 0.5)
            details[factor] = factor_prob
            
            # 贝叶斯更新（简化版）
            if factor_prob != 0.5:
                likelihood_ratio = factor_prob / (1 - factor_prob)
                odds *= (likelihood_ratio / 1.0) ** 0.5  # 衰减系数
        
        # 转换回概率
        prob = odds / (1 + odds)
        
        # 限制范围
        prob = max(0.15, min(0.85, prob))
        
        return prob, details
    
    def calculate_expected_return(self, 
                                  win_prob: float,
                                  factors: List[str],
                                  avg_win: float = 0.05,
                                  avg_loss: float = -0.03) -> float:
        """
        计算期望收益
        
        E[R] = P(win) * avg_win + P(loss) * avg_loss
        """
        # 调整平均收益
        factor_adjustment = 0
        for factor in factors:
            factor_adjustment += self.FACTOR_EXP_RETURNS.get(factor, 0)
        
        adjusted_win = avg_win + factor_adjustment * 0.3
        adjusted_loss = avg_loss + factor_adjustment * 0.2
        
        exp_return = win_prob * adjusted_win + (1 - win_prob) * adjusted_loss
        
        return round(exp_return, 4)
    
    def calculate_drawdown_risk(self,
                                volatility: float = 0.02,
                                position_pct: float = 0.5,
                                market_regime: str = "shock") -> float:
        """
        计算最大回撤风险
        
        基于波动率和仓位估算
        """
        # 基础回撤风险
        base_risk = volatility * position_pct * 3  # 3倍波动作为极端情况
        
        # 市场状态调整
        regime_multipliers = {
            'bull': 0.7,
            'shock': 1.0,
            'bear': 1.5
        }
        multiplier = regime_multipliers.get(market_regime, 1.0)
        
        dd_risk = base_risk * multiplier
        
        return min(dd_risk, 1.0)
    
    def predict(self,
                main_net_flow: float = 0,
                daily_data: List[Dict] = None,
                rsi: float = 50,
                macd_signal: str = "",
                market_regime: str = "shock",
                volatility: float = 0.02) -> WinRateResult:
        """
        完整预测
        
        Args:
            main_net_flow: 主力净流入（万元）
            daily_data: 日线数据
            rsi: RSI值
            macd_signal: MACD信号
            market_regime: 市场状态
            volatility: 波动率
            
        Returns:
            WinRateResult
        """
        factors = []
        
        # 1. 资金流分类
        fund_factor = self.classify_fund_flow(main_net_flow)
        factors.append(fund_factor)
        
        # 2. 趋势分类
        if daily_data and len(daily_data) >= 20:
            closes = [d['close'] for d in daily_data]
            ma5 = sum(closes[:5]) / 5
            ma10 = sum(closes[:10]) / 10
            ma20 = sum(closes[:20]) / 20
            change_pct = daily_data[0].get('change_pct', 0)
            
            trend_factor = self.classify_trend(ma5, ma10, ma20, change_pct)
            factors.append(trend_factor)
        
        # 3. 技术信号
        tech_factors = self.classify_tech_signal(rsi, macd_signal)
        factors.extend(tech_factors)
        
        # 4. 市场状态
        factors.append(f'market_{market_regime}')
        
        # 计算胜率
        win_prob, prob_details = self.calculate_win_probability(factors)
        
        # 计算期望收益
        exp_return = self.calculate_expected_return(win_prob, factors)
        
        # 计算回撤风险
        dd_risk = self.calculate_drawdown_risk(volatility, 0.5, market_regime)
        
        # 生成信号
        if win_prob >= 0.65 and exp_return > 0.02:
            signal = "✅ 强烈看多"
            confidence = 0.8
        elif win_prob >= 0.55 and exp_return > 0:
            signal = "📈 偏多"
            confidence = 0.65
        elif win_prob <= 0.35 or exp_return < -0.02:
            signal = "❌ 看空"
            confidence = 0.75
        elif win_prob <= 0.45:
            signal = "📉 偏空"
            confidence = 0.6
        else:
            signal = "⚖️ 中性观望"
            confidence = 0.5
        
        return WinRateResult(
            win_prob=round(win_prob, 3),
            exp_return=exp_return,
            max_dd_risk=round(dd_risk, 3),
            confidence=confidence,
            signal=signal,
            details={
                'factors': factors,
                'prob_breakdown': prob_details,
                'timestamp': datetime.now().isoformat()
            }
        )


# ====== 工厂函数 ======
def create_win_rate_model(config: Dict = None) -> WinRateModel:
    """创建胜率模型"""
    return WinRateModel(config)


# ====== 便捷函数 ======
def quick_win_rate(main_net_flow: float,
                   score: float = 50,
                   market_regime: str = "shock") -> Dict:
    """
    快速胜率预测
    
    Returns:
        {win_prob, exp_return, max_dd_risk, signal}
    """
    model = WinRateModel()
    
    # 简化版因子
    factors = [model.classify_fund_flow(main_net_flow)]
    factors.append(f'market_{market_regime}')
    
    if score >= 70:
        factors.append('trend_strong_up')
    elif score >= 55:
        factors.append('trend_up')
    elif score <= 35:
        factors.append('trend_down')
    
    win_prob, _ = model.calculate_win_probability(factors)
    exp_return = model.calculate_expected_return(win_prob, factors)
    dd_risk = model.calculate_drawdown_risk()
    
    return {
        'win_prob': round(win_prob, 3),
        'exp_return': round(exp_return, 4),
        'max_dd_risk': round(dd_risk, 3),
        'signal': '看多' if win_prob > 0.55 else ('看空' if win_prob < 0.45 else '中性')
    }
