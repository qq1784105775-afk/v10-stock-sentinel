# -*- coding: utf-8 -*-
"""
V10 Ultra Pro：失败模式追踪器 (Failure Tracker)
===============================================
记录和分析交易失败的模式：
- 假突破
- 情绪退潮  
- 资金撤离
- 趋势反转
- 市场系统性风险
"""

from typing import Dict, List, Optional
from enum import Enum
from datetime import datetime, timedelta
from collections import defaultdict


class FailureType(Enum):
    """失败类型枚举"""
    FAKE_BREAKOUT = "fake_breakout"       # 假突破
    EMOTION_RETREAT = "emotion_retreat"   # 情绪退潮
    FUND_WITHDRAWAL = "fund_withdrawal"   # 资金撤离
    TREND_REVERSAL = "trend_reversal"     # 趋势反转
    MARKET_CRASH = "market_crash"         # 市场崩盘
    STOP_LOSS_HIT = "stop_loss_hit"       # 触发止损
    BLACK_SWAN = "black_swan"             # 黑天鹅事件
    UNKNOWN = "unknown"                   # 未知


class FailureTracker:
    """失败模式追踪器"""
    
    def __init__(self):
        self.failures: List[Dict] = []
        self.failure_stats = defaultdict(int)
    
    def record_failure(self,
                       ts_code: str,
                       stock_name: str,
                       failure_type: FailureType,
                       entry_price: float,
                       exit_price: float,
                       loss_pct: float,
                       entry_factors: List[str] = None,
                       exit_reason: str = "",
                       market_context: Dict = None) -> None:
        """
        记录一次失败
        
        Args:
            ts_code: 股票代码
            stock_name: 股票名称
            failure_type: 失败类型
            entry_price: 入场价
            exit_price: 出场价
            loss_pct: 亏损比例
            entry_factors: 入场时的因子
            exit_reason: 出场原因
            market_context: 市场环境
        """
        failure_record = {
            'timestamp': datetime.now().isoformat(),
            'ts_code': ts_code,
            'stock_name': stock_name,
            'failure_type': failure_type.value,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'loss_pct': loss_pct,
            'entry_factors': entry_factors or [],
            'exit_reason': exit_reason,
            'market_context': market_context or {}
        }
        
        self.failures.append(failure_record)
        self.failure_stats[failure_type.value] += 1
    
    def detect_failure_type(self,
                            entry_data: Dict,
                            exit_data: Dict,
                            market_data: Dict = None) -> FailureType:
        """
        自动检测失败类型
        
        Args:
            entry_data: 入场时数据
            exit_data: 出场时数据
            market_data: 市场数据
            
        Returns:
            FailureType
        """
        # 检查市场崩盘
        if market_data:
            index_change = market_data.get('index_change', 0)
            if index_change < -3:
                return FailureType.MARKET_CRASH
        
        # 检查资金撤离
        entry_fund = entry_data.get('main_net_flow', 0)
        exit_fund = exit_data.get('main_net_flow', 0)
        if entry_fund > 0 and exit_fund < -2000:
            return FailureType.FUND_WITHDRAWAL
        
        # 检查假突破
        entry_breakout = entry_data.get('is_breakout', False)
        exit_price = exit_data.get('price', 0)
        entry_price = entry_data.get('price', 0)
        if entry_breakout and exit_price < entry_price * 0.97:
            return FailureType.FAKE_BREAKOUT
        
        # 检查情绪退潮
        entry_sentiment = entry_data.get('market_sentiment', 50)
        exit_sentiment = exit_data.get('market_sentiment', 50)
        if entry_sentiment > 70 and exit_sentiment < 40:
            return FailureType.EMOTION_RETREAT
        
        # 检查趋势反转
        entry_trend = entry_data.get('trend', 'up')
        exit_trend = exit_data.get('trend', 'down')
        if entry_trend == 'up' and exit_trend == 'down':
            return FailureType.TREND_REVERSAL
        
        return FailureType.UNKNOWN
    
    def get_statistics(self) -> Dict:
        """获取失败统计"""
        total = len(self.failures)
        
        if total == 0:
            return {
                'total_failures': 0,
                'by_type': {},
                'most_common': None,
                'avg_loss': 0
            }
        
        # 类型分布
        by_type = dict(self.failure_stats)
        
        # 最常见类型
        most_common = max(by_type.items(), key=lambda x: x[1]) if by_type else None
        
        # 平均亏损
        avg_loss = sum(f['loss_pct'] for f in self.failures) / total
        
        return {
            'total_failures': total,
            'by_type': by_type,
            'most_common': {
                'type': most_common[0],
                'count': most_common[1],
                'percentage': most_common[1] / total * 100
            } if most_common else None,
            'avg_loss': round(avg_loss, 2)
        }
    
    def get_improvement_suggestions(self) -> List[str]:
        """
        根据失败模式生成改进建议
        """
        stats = self.get_statistics()
        suggestions = []
        
        if stats['total_failures'] == 0:
            return ["暂无失败记录"]
        
        most_common = stats.get('most_common')
        if not most_common:
            return ["数据不足，无法生成建议"]
        
        failure_type = most_common['type']
        pct = most_common['percentage']
        
        # 根据最常见失败类型生成建议
        if failure_type == FailureType.FAKE_BREAKOUT.value:
            suggestions.append(f"❗ 假突破占失败的{pct:.0f}%")
            suggestions.append("建议：增加突破确认条件，如成交量>2倍均量")
            suggestions.append("建议：等待回踩确认再入场")
            
        elif failure_type == FailureType.FUND_WITHDRAWAL.value:
            suggestions.append(f"❗ 资金撤离占失败的{pct:.0f}%")
            suggestions.append("建议：提高P2资金流权重")
            suggestions.append("建议：实时监控盘中资金变化")
            
        elif failure_type == FailureType.EMOTION_RETREAT.value:
            suggestions.append(f"❗ 情绪退潮占失败的{pct:.0f}%")
            suggestions.append("建议：避免在情绪高点追涨")
            suggestions.append("建议：增加情绪退潮预警机制")
            
        elif failure_type == FailureType.TREND_REVERSAL.value:
            suggestions.append(f"❗ 趋势反转占失败的{pct:.0f}%")
            suggestions.append("建议：增加趋势确认因子")
            suggestions.append("建议：设置移动止损保护利润")
            
        elif failure_type == FailureType.MARKET_CRASH.value:
            suggestions.append(f"❗ 市场崩盘占失败的{pct:.0f}%")
            suggestions.append("建议：增强P1市场状态权重")
            suggestions.append("建议：极端行情自动减仓")
        
        return suggestions
    
    def get_pattern_analysis(self, days: int = 30) -> Dict:
        """
        失败模式分析
        
        分析最近N天的失败规律
        """
        cutoff = datetime.now() - timedelta(days=days)
        recent_failures = [
            f for f in self.failures 
            if datetime.fromisoformat(f['timestamp']) > cutoff
        ]
        
        if not recent_failures:
            return {'period_days': days, 'count': 0}
        
        # 按失败类型分组
        by_type = defaultdict(list)
        for f in recent_failures:
            by_type[f['failure_type']].append(f)
        
        # 分析每种类型的共同特征
        patterns = {}
        for ft, failures in by_type.items():
            common_factors = self._find_common_factors(failures)
            avg_loss = sum(f['loss_pct'] for f in failures) / len(failures)
            
            patterns[ft] = {
                'count': len(failures),
                'avg_loss': round(avg_loss, 2),
                'common_entry_factors': common_factors
            }
        
        return {
            'period_days': days,
            'total_failures': len(recent_failures),
            'patterns': patterns
        }
    
    def _find_common_factors(self, failures: List[Dict]) -> List[str]:
        """找出共同的入场因子"""
        if not failures:
            return []
        
        factor_counts = defaultdict(int)
        for f in failures:
            for factor in f.get('entry_factors', []):
                factor_counts[factor] += 1
        
        # 返回出现超过50%的因子
        threshold = len(failures) * 0.5
        common = [f for f, c in factor_counts.items() if c >= threshold]
        
        return common


# ====== 全局追踪器 ======
_tracker = None

def get_failure_tracker() -> FailureTracker:
    """获取追踪器单例"""
    global _tracker
    if _tracker is None:
        _tracker = FailureTracker()
    return _tracker


def record_trade_failure(ts_code: str,
                         stock_name: str,
                         failure_type: str,
                         loss_pct: float,
                         **kwargs) -> None:
    """便捷函数：记录交易失败"""
    tracker = get_failure_tracker()
    
    # 转换字符串到枚举
    ft = FailureType.UNKNOWN
    for member in FailureType:
        if member.value == failure_type:
            ft = member
            break
    
    tracker.record_failure(
        ts_code=ts_code,
        stock_name=stock_name,
        failure_type=ft,
        entry_price=kwargs.get('entry_price', 0),
        exit_price=kwargs.get('exit_price', 0),
        loss_pct=loss_pct,
        entry_factors=kwargs.get('entry_factors'),
        exit_reason=kwargs.get('exit_reason', ''),
        market_context=kwargs.get('market_context')
    )
