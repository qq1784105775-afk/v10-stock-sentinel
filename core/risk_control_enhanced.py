# -*- coding: utf-8 -*-
"""
V10 Ultra Pro：增强风控模块
===========================
包含：
1. 动态止损策略
2. 最大回撤控制
3. 资金流强度分析
4. 牛熊市自动识别
5. 市场情绪指标
6. V10新增：账户级风控
7. V10新增：核按钮（一键全停）
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta


# ====== V10新增：全局风控状态 ======
class GlobalRiskState:
    """全局风控状态（核按钮）"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.kill_switch_active = False
            cls._instance.kill_reason = ""
            cls._instance.kill_timestamp = None
            cls._instance.consecutive_losses = 0
            cls._instance.today_drawdown = 0
            cls._instance.account_drawdown = 0
        return cls._instance
    
    def activate_kill_switch(self, reason: str) -> None:
        """激活核按钮 - 全系统禁止新开仓"""
        self.kill_switch_active = True
        self.kill_reason = reason
        self.kill_timestamp = datetime.now()
        print(f"🚨 核按钮激活：{reason}")
    
    def deactivate_kill_switch(self) -> None:
        """解除核按钮"""
        self.kill_switch_active = False
        self.kill_reason = ""
        self.kill_timestamp = None
        print("✅ 核按钮已解除")
    
    def is_trading_allowed(self) -> Tuple[bool, str]:
        """检查是否允许交易"""
        if self.kill_switch_active:
            return False, f"核按钮激活：{self.kill_reason}"
        return True, "正常"
    
    def record_trade_result(self, is_win: bool, pnl_pct: float) -> None:
        """记录交易结果，更新连续亏损"""
        if is_win:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            
            # V10优化：连续亏损>=2次（原3次）激活核按钮
            if self.consecutive_losses >= 2:
                self.activate_kill_switch(f"连续亏损{self.consecutive_losses}次")
    
    def update_drawdown(self, current_value: float, peak_value: float) -> None:
        """更新回撤"""
        if peak_value > 0:
            self.account_drawdown = (peak_value - current_value) / peak_value
            
            # V10优化：回撤>=10%（原15%）激活核按钮
            if self.account_drawdown >= 0.10:
                self.activate_kill_switch(f"账户回撤{self.account_drawdown*100:.1f}%")


# 全局实例
def get_global_risk_state() -> GlobalRiskState:
    return GlobalRiskState()


class EnhancedRiskControl:
    """增强风控管理器"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.peak_value = 0  # 历史最高净值
        self.drawdown_threshold = 0.15  # 最大回撤阈值15%
        self.market_regime = "SHOCK"  # 市场状态
        self.global_risk = get_global_risk_state()  # V10新增：全局风控
        

    def calculate_atr(self, daily_data: List[Dict], period: int = 14) -> float:
        """
        计算ATR（平均真实波幅）
        用于动态止损
        """
        if len(daily_data) < period:
            return 0
        
        tr_list = []
        for i in range(len(daily_data) - 1):
            high = daily_data[i].get('high', daily_data[i]['close'])
            low = daily_data[i].get('low', daily_data[i]['close'])
            prev_close = daily_data[i+1]['close']
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            tr_list.append(tr)
        
        if len(tr_list) >= period:
            return np.mean(tr_list[-period:])
        return np.mean(tr_list) if tr_list else 0
    
    def dynamic_stop_loss(self, 
                         current_price: float,
                         entry_price: float,
                         atr: float,
                         profit_pct: float) -> Dict:
        """
        动态止损策略
        根据ATR和盈利情况动态调整止损位
        """
        # 基础止损：2倍ATR
        base_stop = entry_price - (2 * atr)
        
        # 修复：使用elif避免条件覆盖
        if profit_pct > 20:
            # 盈利20%以上，止损位上移到盈利10%位置
            stop_price = max(base_stop, entry_price * 1.10)
        elif profit_pct > 10:
            # 盈利10%以上，止损位上移到盈利5%位置
            stop_price = max(base_stop, entry_price * 1.05)
        elif profit_pct > 5:
            # 盈利5%以上，止损位上移到成本价
            stop_price = max(base_stop, entry_price)
        elif profit_pct > 0:
            # 小幅盈利，使用基础止损
            stop_price = base_stop
        else:
            # 亏损时的固定止损
            stop_price = base_stop
        
        stop_pct = (stop_price - current_price) / current_price * 100
        
        return {
            'stop_price': round(stop_price, 2),
            'stop_pct': round(stop_pct, 2),
            'type': 'trailing' if profit_pct > 5 else 'fixed',
            'suggestion': self._get_stop_suggestion(stop_pct, profit_pct)
        }
    
    def _get_stop_suggestion(self, stop_pct: float, profit_pct: float) -> str:
        """获取止损建议"""
        if profit_pct > 20:
            return "大幅盈利，建议分批止盈"
        elif profit_pct > 10:
            return "盈利良好，可考虑减仓锁利"
        elif profit_pct > 5:
            return "小幅盈利，持有为主"
        elif stop_pct < -8:
            return "接近止损，密切关注"
        elif stop_pct < -5:
            return "注意风险，设好止损"
        else:
            return "正常持有"
    
    def max_drawdown_control(self,
                            current_value: float,
                            peak_value: float) -> Dict:
        """
        最大回撤控制
        监控并限制最大回撤
        """
        # 更新峰值
        if current_value > peak_value:
            self.peak_value = current_value
            peak_value = current_value
        
        # 计算回撤
        drawdown = 0
        if peak_value > 0:
            drawdown = (peak_value - current_value) / peak_value
        
        # 生成控制信号
        action = "正常"
        suggestion = "继续执行策略"
        
        if drawdown > 0.20:
            action = "停止交易"
            suggestion = "回撤超20%，暂停所有交易，等待市场稳定"
        elif drawdown > 0.15:
            action = "强制减仓"
            suggestion = "回撤超15%，减仓50%，控制风险"
        elif drawdown > 0.10:
            action = "减仓警告"
            suggestion = "回撤超10%，考虑减仓30%"
        elif drawdown > 0.05:
            action = "风险提示"
            suggestion = "回撤超5%，注意控制仓位"
        
        return {
            'current_drawdown': round(drawdown * 100, 2),
            'max_allowed': round(self.drawdown_threshold * 100, 2),
            'action': action,
            'suggestion': suggestion,
            'peak_value': round(peak_value, 2),
            'current_value': round(current_value, 2)
        }
    
    def fund_flow_strength(self,
                          inflow: float,
                          outflow: float,
                          volume: float,
                          avg_volume: float) -> Dict:
        """
        资金流强度分析
        评估主力资金动向
        """
        net_flow = inflow - outflow
        total_flow = inflow + outflow
        
        # 计算各项指标
        flow_ratio = inflow / outflow if outflow > 0 else 999
        net_ratio = net_flow / total_flow * 100 if total_flow > 0 else 0
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1
        
        # 主力净流入率
        main_net_rate = net_flow / (volume * 10000) * 100 if volume > 0 else 0
        
        # 资金集中度（大单占比）
        concentration = 0
        if volume > 0:
            large_order_pct = (inflow + outflow) / (volume * 10000) * 100
            concentration = min(large_order_pct / 30 * 100, 100)  # 30%为基准
        
        # 综合评分
        score = 50
        signals = []
        
        # 修复：阈值单位改为万元（Tushare返回万元）
        if net_flow > 5000:  # 净流入超5000万元
            score += 30
            signals.append("巨额流入")
        elif net_flow > 1000:  # 1000万元
            score += 20
            signals.append("大幅流入")
        elif net_flow < -5000:  # -5000万元
            score -= 30
            signals.append("巨额流出")
        elif net_flow < -1000:  # -1000万元
            score -= 20
            signals.append("大幅流出")
        
        if flow_ratio > 3:
            score += 10
            signals.append("买盘强劲")
        elif flow_ratio < 0.3:
            score -= 10
            signals.append("卖压沉重")
        
        if concentration > 70:
            score += 10
            signals.append("资金集中")
        elif concentration < 30:
            score -= 10
            signals.append("资金分散")
        
        # 生成建议
        if score >= 80:
            suggestion = "主力大举建仓，积极跟进"
        elif score >= 60:
            suggestion = "资金流入，可以关注"
        elif score <= 20:
            suggestion = "资金大幅流出，规避风险"
        elif score <= 40:
            suggestion = "资金流出，谨慎观望"
        else:
            suggestion = "资金平衡，等待方向"
        
        return {
            'score': max(0, min(100, score)),
            'net_flow': round(net_flow / 10000, 2),
            'flow_ratio': round(flow_ratio, 2),
            'concentration': round(concentration, 2),
            'signals': signals,
            'suggestion': suggestion
        }
    
    def detect_market_regime(self,
                            index_data: List[Dict],
                            volume_data: List[float] = None) -> Dict:
        """
        牛熊市自动识别
        基于均线系统和成交量判断市场状态
        """
        if len(index_data) < 200:
            return {
                'regime': 'UNKNOWN',
                'confidence': 0,
                'signals': ['数据不足'],
                'suggestion': '数据不足，无法判断'
            }
        
        closes = [d['close'] for d in index_data]
        
        # 计算均线
        ma20 = np.mean(closes[-20:])
        ma50 = np.mean(closes[-50:])
        ma200 = np.mean(closes[-200:])
        
        current = closes[-1]
        
        # 均线排列
        signals = []
        score = 0
        
        # 多头排列：MA20 > MA50 > MA200
        if ma20 > ma50 > ma200:
            signals.append("多头排列")
            score += 40
        # 空头排列：MA20 < MA50 < MA200
        elif ma20 < ma50 < ma200:
            signals.append("空头排列")
            score -= 40
        else:
            signals.append("均线纠缠")
        
        # 价格位置
        if current > ma200:
            signals.append("站上年线")
            score += 20
        else:
            signals.append("跌破年线")
            score -= 20
        
        if current > ma50:
            score += 15
        else:
            score -= 15
        
        if current > ma20:
            score += 10
        else:
            score -= 10
        
        # 趋势强度
        trend_20 = (current - closes[-20]) / closes[-20] * 100
        trend_50 = (current - closes[-50]) / closes[-50] * 100
        
        if trend_20 > 10:
            signals.append(f"20日涨{trend_20:.1f}%")
            score += 15
        elif trend_20 < -10:
            signals.append(f"20日跌{abs(trend_20):.1f}%")
            score -= 15
        
        # 判定市场状态
        if score >= 50:
            regime = "BULL"
            suggestion = "牛市特征明显，可积极做多"
        elif score <= -50:
            regime = "BEAR"
            suggestion = "熊市特征明显，控制仓位"
        else:
            regime = "SHOCK"
            suggestion = "震荡市，高抛低吸"
        
        self.market_regime = regime
        
        return {
            'regime': regime,
            'confidence': min(abs(score), 100),
            'signals': signals,
            'ma20': round(ma20, 2),
            'ma50': round(ma50, 2),
            'ma200': round(ma200, 2),
            'current': round(current, 2),
            'score': score,
            'suggestion': suggestion
        }
    
    def market_sentiment_index(self,
                             up_count: int,
                             down_count: int,
                             limit_up: int,
                             limit_down: int,
                             volume: float,
                             avg_volume: float,
                             north_money: float = 0) -> Dict:
        """
        市场情绪指数
        综合多个指标判断市场情绪
        """
        total_stocks = up_count + down_count
        if total_stocks == 0:
            return {
                'sentiment': 50,
                'level': '中性',
                'signals': ['无数据'],
                'suggestion': '等待数据'
            }
        
        # 涨跌比
        up_ratio = up_count / total_stocks * 100
        
        # 涨跌停比
        extreme_ratio = 0
        if limit_up + limit_down > 0:
            extreme_ratio = limit_up / (limit_up + limit_down) * 100
        
        # 成交量比
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1
        
        # 计算情绪分数
        sentiment = 50
        signals = []
        
        # 涨跌比影响（权重30%）
        if up_ratio > 70:
            sentiment += 15
            signals.append(f"普涨({up_ratio:.0f}%)")
        elif up_ratio > 60:
            sentiment += 8
            signals.append("多数上涨")
        elif up_ratio < 30:
            sentiment -= 15
            signals.append(f"普跌({up_ratio:.0f}%)")
        elif up_ratio < 40:
            sentiment -= 8
            signals.append("多数下跌")
        
        # 涨跌停影响（权重20%）
        if limit_up > 100:
            sentiment += 10
            signals.append(f"涨停{limit_up}家")
        elif limit_up > 50:
            sentiment += 5
            signals.append(f"涨停{limit_up}家")
        
        if limit_down > 100:
            sentiment -= 10
            signals.append(f"跌停{limit_down}家")
        elif limit_down > 50:
            sentiment -= 5
            signals.append(f"跌停{limit_down}家")
        
        # 成交量影响（权重20%）
        if volume_ratio > 1.5:
            sentiment += 10
            signals.append("放量")
        elif volume_ratio > 1.2:
            sentiment += 5
            signals.append("温和放量")
        elif volume_ratio < 0.7:
            sentiment -= 10
            signals.append("缩量")
        elif volume_ratio < 0.9:
            sentiment -= 5
            signals.append("小幅缩量")
        
        # 北向资金影响（权重30%）
        # 注意：north_money 传入时单位是百万元，需要正确转换
        # 修复：调整阈值（100为100百万=1亿元，50为50百万=0.5亿）
        if north_money > 100:  # 流入100百万（1亿）以上
            sentiment += 15
            signals.append(f"北向流入{north_money/100:.1f}亿")
        elif north_money > 50:  # 50百万
            sentiment += 8
            signals.append(f"北向流入{north_money/100:.1f}亿")
        elif north_money < -100:  # 流出1亿以上
            sentiment -= 15
            signals.append(f"北向流出{abs(north_money)/100:.1f}亿")
        elif north_money < -50:
            sentiment -= 8
            signals.append(f"北向流出{abs(north_money)/100:.1f}亿")
        
        # 确定情绪等级
        if sentiment >= 80:
            level = "极度乐观"
            suggestion = "市场过热，注意风险"
        elif sentiment >= 65:
            level = "乐观"
            suggestion = "市场向好，可适当加仓"
        elif sentiment <= 20:
            level = "极度恐慌"
            suggestion = "市场超跌，可能有机会"
        elif sentiment <= 35:
            level = "恐慌"
            suggestion = "市场偏弱，控制仓位"
        else:
            level = "中性"
            suggestion = "市场平稳，正常操作"
        
        return {
            'sentiment': max(0, min(100, sentiment)),
            'level': level,
            'signals': signals,
            'up_ratio': round(up_ratio, 1),
            'limit_up': limit_up,
            'limit_down': limit_down,
            'volume_ratio': round(volume_ratio, 2),
            'north_money': round(north_money / 100, 2),  # 百万元转换为亿
            'suggestion': suggestion
        }
