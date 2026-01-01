# -*- coding: utf-8 -*-
"""
V10 Ultra Pro：交易状态机 (Trading State)
=========================================
明确的盘前/盘中/尾盘/盘后状态区分
不同状态启用不同因子权重和策略集
"""

from enum import Enum
from datetime import datetime, time
from typing import Dict, List, Tuple


class TradingState(Enum):
    """交易状态枚举"""
    PRE_MARKET = "pre_market"        # 盘前 (09:00-09:25)
    OPENING = "opening"               # 开盘 (09:25-09:35)
    MID_SESSION = "mid_session"       # 盘中 (09:35-14:30)
    TAIL_SESSION = "tail_session"     # 尾盘 (14:30-15:00)
    POST_MARKET = "post_market"       # 盘后 (15:00+)
    CLOSED = "closed"                 # 非交易日


# ====== 状态对应的因子权重调整 ======
STATE_FACTOR_WEIGHTS = {
    TradingState.PRE_MARKET: {
        "trend": 0.3,        # 趋势权重高，参考昨日
        "volume": 0.1,       # 量能无效
        "fund_flow": 0.2,    # 预判资金
        "chip": 0.2,         # 筹码稳定
        "sentiment": 0.2,    # 情绪预判
    },
    TradingState.OPENING: {
        "trend": 0.2,
        "volume": 0.3,       # 开盘量能重要
        "fund_flow": 0.2,
        "chip": 0.1,
        "sentiment": 0.2,
    },
    TradingState.MID_SESSION: {
        "trend": 0.2,
        "volume": 0.2,
        "fund_flow": 0.3,    # 盘中资金最重要
        "chip": 0.15,
        "sentiment": 0.15,
    },
    TradingState.TAIL_SESSION: {
        "trend": 0.15,
        "volume": 0.2,
        "fund_flow": 0.35,   # 尾盘资金定调
        "chip": 0.15,
        "sentiment": 0.15,
    },
    TradingState.POST_MARKET: {
        "trend": 0.25,
        "volume": 0.15,
        "fund_flow": 0.25,
        "chip": 0.2,
        "sentiment": 0.15,
    },
}


# ====== 状态对应的策略集 ======
STATE_STRATEGY_SETS = {
    TradingState.PRE_MARKET: ["gap_analysis", "sector_rotation"],
    TradingState.OPENING: ["opening_breakout", "reversal_detection"],
    TradingState.MID_SESSION: ["trend_follow", "fund_flow_chase", "dip_buy"],
    TradingState.TAIL_SESSION: ["tail_pull", "fund_accumulation"],
    TradingState.POST_MARKET: ["review", "next_day_prep"],
}


# ====== 状态对应的风控参数 ======
STATE_RISK_PARAMS = {
    TradingState.PRE_MARKET: {
        "allow_new_position": False,
        "max_position_pct": 0,
    },
    TradingState.OPENING: {
        "allow_new_position": True,
        "max_position_pct": 0.3,   # 开盘只允许30%仓位
        "stop_loss_strict": True,
    },
    TradingState.MID_SESSION: {
        "allow_new_position": True,
        "max_position_pct": 0.7,
        "stop_loss_strict": False,
    },
    TradingState.TAIL_SESSION: {
        "allow_new_position": True,
        "max_position_pct": 1.0,   # 尾盘放开
        "stop_loss_strict": False,
    },
    TradingState.POST_MARKET: {
        "allow_new_position": False,
        "max_position_pct": 0,
    },
}


class TradingStateManager:
    """交易状态管理器"""
    
    # A股交易时间定义
    TIME_RANGES = {
        TradingState.PRE_MARKET: (time(9, 0), time(9, 25)),
        TradingState.OPENING: (time(9, 25), time(9, 35)),
        TradingState.MID_SESSION: (time(9, 35), time(14, 30)),
        TradingState.TAIL_SESSION: (time(14, 30), time(15, 0)),
        TradingState.POST_MARKET: (time(15, 0), time(23, 59)),
    }
    
    def __init__(self):
        self.current_state = TradingState.CLOSED
        self._update_state()
    
    def _update_state(self) -> None:
        """根据当前时间更新状态"""
        now = datetime.now()
        current_time = now.time()
        weekday = now.weekday()
        
        # 周末非交易
        if weekday >= 5:
            self.current_state = TradingState.CLOSED
            return
        
        # 判断时间段
        for state, (start, end) in self.TIME_RANGES.items():
            if start <= current_time < end:
                self.current_state = state
                return
        
        # 早于9点
        if current_time < time(9, 0):
            self.current_state = TradingState.CLOSED
        else:
            self.current_state = TradingState.POST_MARKET
    
    def get_current_state(self) -> TradingState:
        """获取当前交易状态"""
        self._update_state()
        return self.current_state
    
    def get_factor_weights(self) -> Dict[str, float]:
        """获取当前状态的因子权重"""
        state = self.get_current_state()
        return STATE_FACTOR_WEIGHTS.get(state, STATE_FACTOR_WEIGHTS[TradingState.POST_MARKET])
    
    def get_active_strategies(self) -> List[str]:
        """获取当前状态的活跃策略集"""
        state = self.get_current_state()
        return STATE_STRATEGY_SETS.get(state, [])
    
    def get_risk_params(self) -> Dict:
        """获取当前状态的风控参数"""
        state = self.get_current_state()
        return STATE_RISK_PARAMS.get(state, STATE_RISK_PARAMS[TradingState.POST_MARKET])
    
    def is_trading_allowed(self) -> Tuple[bool, str]:
        """
        是否允许交易
        
        Returns:
            (是否允许, 原因)
        """
        state = self.get_current_state()
        risk_params = self.get_risk_params()
        
        if state == TradingState.CLOSED:
            return False, "非交易时段"
        
        if not risk_params.get('allow_new_position', False):
            return False, f"{state.value}时段不允许新开仓"
        
        return True, "允许交易"
    
    def get_state_info(self) -> Dict:
        """获取完整状态信息"""
        state = self.get_current_state()
        
        return {
            'state': state.value,
            'state_name': self._get_state_name(state),
            'factor_weights': self.get_factor_weights(),
            'active_strategies': self.get_active_strategies(),
            'risk_params': self.get_risk_params(),
            'trading_allowed': self.is_trading_allowed()[0],
            'timestamp': datetime.now().isoformat()
        }
    
    def _get_state_name(self, state: TradingState) -> str:
        """获取状态中文名"""
        names = {
            TradingState.PRE_MARKET: "盘前准备",
            TradingState.OPENING: "开盘交易",
            TradingState.MID_SESSION: "盘中交易",
            TradingState.TAIL_SESSION: "尾盘交易",
            TradingState.POST_MARKET: "盘后复盘",
            TradingState.CLOSED: "休市",
        }
        return names.get(state, "未知")


# ====== 全局实例 ======
_state_manager = None

def get_state_manager() -> TradingStateManager:
    """获取状态管理器单例"""
    global _state_manager
    if _state_manager is None:
        _state_manager = TradingStateManager()
    return _state_manager


def get_current_trading_state() -> TradingState:
    """获取当前交易状态（便捷函数）"""
    return get_state_manager().get_current_state()


def get_state_factor_weights() -> Dict[str, float]:
    """获取当前状态因子权重（便捷函数）"""
    return get_state_manager().get_factor_weights()
