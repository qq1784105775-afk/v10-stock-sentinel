# -*- coding: utf-8 -*-
"""
V10 Ultra Pro：智能出场模块 (Exit Strategy)
==========================================
问题#14：出场逻辑弱

修复：增加趋势失效/资金撤离识别
不再仅靠止损止盈
"""

from typing import Dict, List, Tuple, Optional
from enum import Enum
from datetime import datetime


class ExitReason(Enum):
    """出场原因枚举"""
    STOP_LOSS = "stop_loss"              # 触发止损
    TAKE_PROFIT = "take_profit"          # 触发止盈
    TREND_FAILURE = "trend_failure"       # 趋势失效
    FUND_WITHDRAWAL = "fund_withdrawal"   # 资金撤离
    EMOTION_RETREAT = "emotion_retreat"   # 情绪退潮
    TIME_LIMIT = "time_limit"            # 持仓时间过长
    MARKET_CRASH = "market_crash"        # 市场崩盘
    MANUAL = "manual"                    # 手动卖出


class ExitStrategy:
    """智能出场策略"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        
        # 出场阈值配置
        self.thresholds = {
            'stop_loss_pct': -5.0,         # 止损线 -5%
            'take_profit_pct': 10.0,       # 止盈线 +10%
            'trailing_stop_pct': 3.0,      # 移动止损（从高点回撤）
            'fund_withdrawal_threshold': -3000,  # 资金撤离阈值（万元）
            'ma_break_confirm_days': 2,    # 均线破位确认天数
            'max_hold_days': 20,           # 最大持仓天数
        }
    
    def check_trend_failure(self, 
                            daily_data: List[Dict],
                            entry_price: float) -> Tuple[bool, str]:
        """
        趋势失效检测
        
        条件：
        1. 跌破MA5且连续2天收盘在MA5下方
        2. MACD死叉确认
        3. 量价背离（价涨量缩）
        
        Returns:
            (是否趋势失效, 失效描述)
        """
        if len(daily_data) < 10:
            return False, ""
        
        closes = [d['close'] for d in daily_data]
        
        # 计算MA5
        ma5 = sum(closes[:5]) / 5
        ma10 = sum(closes[:10]) / 10
        
        current_close = closes[0]
        prev_close = closes[1] if len(closes) > 1 else current_close
        
        # 条件1：跌破MA5连续2天
        below_ma5_today = current_close < ma5
        below_ma5_yesterday = prev_close < (sum(closes[1:6]) / 5) if len(closes) > 5 else False
        
        if below_ma5_today and below_ma5_yesterday:
            return True, f"跌破MA5连续2天，当前{current_close:.2f} < MA5 {ma5:.2f}"
        
        # 条件2：MA5死叉MA10
        if ma5 < ma10:
            prev_ma5 = sum(closes[1:6]) / 5 if len(closes) > 5 else ma5
            prev_ma10 = sum(closes[1:11]) / 10 if len(closes) > 10 else ma10
            if prev_ma5 >= prev_ma10:  # 刚刚死叉
                return True, f"MA5死叉MA10，趋势转弱"
        
        # 条件3：价涨量缩（连续3天）
        if len(daily_data) >= 3:
            price_up = all(daily_data[i]['close'] > daily_data[i+1]['close'] for i in range(2))
            vol_down = all(daily_data[i]['vol'] < daily_data[i+1]['vol'] for i in range(2))
            if price_up and vol_down:
                return True, "价涨量缩连续3天，量价背离"
        
        return False, ""
    
    def check_fund_withdrawal(self,
                              money_flow: List[Dict],
                              days: int = 3) -> Tuple[bool, str]:
        """
        资金撤离检测
        
        条件：
        1. 单日净流出超阈值
        2. 连续N天净流出
        
        Returns:
            (是否资金撤离, 描述)
        """
        if not money_flow:
            return False, ""
        
        # 单日大额流出
        today_flow = money_flow[0].get('main_net_inflow', 0)
        if today_flow < self.thresholds['fund_withdrawal_threshold']:
            return True, f"主力单日净流出{abs(today_flow):.0f}万"
        
        # 连续流出
        if len(money_flow) >= days:
            consecutive_outflow = all(
                money_flow[i].get('main_net_inflow', 0) < 0 
                for i in range(days)
            )
            if consecutive_outflow:
                total_outflow = sum(money_flow[i].get('main_net_inflow', 0) for i in range(days))
                return True, f"连续{days}日净流出，合计{abs(total_outflow):.0f}万"
        
        return False, ""
    
    def check_emotion_retreat(self,
                              market_sentiment: str,
                              prev_sentiment: str = "") -> Tuple[bool, str]:
        """
        情绪退潮检测
        
        条件：市场情绪从强转弱
        """
        strong_states = ['very_strong', 'strong']
        weak_states = ['weak', 'very_weak']
        
        if prev_sentiment in strong_states and market_sentiment in weak_states:
            return True, f"市场情绪从{prev_sentiment}转为{market_sentiment}"
        
        return False, ""
    
    def check_trailing_stop(self,
                            entry_price: float,
                            current_price: float,
                            peak_price: float) -> Tuple[bool, str]:
        """
        移动止损检测
        
        从最高点回撤超过阈值触发
        """
        if peak_price <= entry_price:
            return False, ""
        
        # 只有盈利时才启用移动止损
        profit_from_entry = (peak_price - entry_price) / entry_price * 100
        if profit_from_entry < 5:  # 盈利超过5%才启用
            return False, ""
        
        drawdown_from_peak = (peak_price - current_price) / peak_price * 100
        if drawdown_from_peak >= self.thresholds['trailing_stop_pct']:
            return True, f"从高点{peak_price:.2f}回撤{drawdown_from_peak:.1f}%"
        
        return False, ""
    
    def should_exit(self,
                    entry_price: float,
                    current_price: float,
                    peak_price: float,
                    daily_data: List[Dict] = None,
                    money_flow: List[Dict] = None,
                    market_sentiment: str = "",
                    hold_days: int = 0) -> Tuple[bool, ExitReason, str]:
        """
        综合出场判断
        
        优先级：
        1. 止损 > 2. 市场崩盘 > 3. 资金撤离 > 4. 趋势失效 > 5. 移动止损 > 6. 止盈
        
        Returns:
            (是否应该卖出, 出场原因, 描述)
        """
        change_pct = (current_price - entry_price) / entry_price * 100
        
        # 1. 止损检测
        if change_pct <= self.thresholds['stop_loss_pct']:
            return True, ExitReason.STOP_LOSS, f"触发止损：亏损{abs(change_pct):.1f}%"
        
        # 2. 持仓时间过长
        if hold_days >= self.thresholds['max_hold_days']:
            return True, ExitReason.TIME_LIMIT, f"持仓{hold_days}天超上限"
        
        # 3. 资金撤离
        if money_flow:
            is_withdrawal, desc = self.check_fund_withdrawal(money_flow)
            if is_withdrawal:
                return True, ExitReason.FUND_WITHDRAWAL, desc
        
        # 4. 趋势失效
        if daily_data:
            is_failure, desc = self.check_trend_failure(daily_data, entry_price)
            if is_failure:
                return True, ExitReason.TREND_FAILURE, desc
        
        # 5. 移动止损
        is_trailing_hit, desc = self.check_trailing_stop(entry_price, current_price, peak_price)
        if is_trailing_hit:
            return True, ExitReason.STOP_LOSS, f"移动止损：{desc}"
        
        # 6. 止盈检测
        if change_pct >= self.thresholds['take_profit_pct']:
            return True, ExitReason.TAKE_PROFIT, f"触发止盈：盈利{change_pct:.1f}%"
        
        return False, None, ""


# ====== 全局实例 ======
_exit_strategy = None

def get_exit_strategy() -> ExitStrategy:
    global _exit_strategy
    if _exit_strategy is None:
        _exit_strategy = ExitStrategy()
    return _exit_strategy


def should_exit_position(entry_price: float,
                         current_price: float,
                         peak_price: float,
                         daily_data: List[Dict] = None,
                         money_flow: List[Dict] = None,
                         hold_days: int = 0) -> Dict:
    """便捷函数：判断是否应该出场"""
    strategy = get_exit_strategy()
    should_exit, reason, desc = strategy.should_exit(
        entry_price, current_price, peak_price,
        daily_data, money_flow, hold_days=hold_days
    )
    return {
        'should_exit': should_exit,
        'reason': reason.value if reason else None,
        'description': desc
    }
