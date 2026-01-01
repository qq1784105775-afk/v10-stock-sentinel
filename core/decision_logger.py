# -*- coding: utf-8 -*-
"""
V10 Ultra Pro：决策日志系统 (Decision Logger)
=============================================
记录每笔交易的：
- 触发因子
- 否决因子
- 最终裁决理由
"""

import json
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path


class DecisionLogger:
    """决策日志记录器"""
    
    def __init__(self, log_dir: str = None):
        """
        初始化日志器
        
        Args:
            log_dir: 日志目录，默认为当前目录下的 logs
        """
        if log_dir:
            self.log_dir = Path(log_dir)
        else:
            self.log_dir = Path(__file__).parent.parent / 'logs' / 'decisions'
        
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.session_logs: List[Dict] = []
    
    def log_decision(self,
                     ts_code: str,
                     stock_name: str,
                     action: str,
                     action_class: str,
                     trigger_factors: List[str],
                     veto_factors: List[str],
                     final_reason: str,
                     score: float = 0,
                     win_prob: float = 0,
                     extra_info: Dict = None) -> None:
        """
        记录单笔决策
        
        Args:
            ts_code: 股票代码
            stock_name: 股票名称
            action: 最终动作
            action_class: 动作分类 (go/watch/run)
            trigger_factors: 触发因子列表
            veto_factors: 否决因子列表
            final_reason: 最终裁决理由
            score: 综合评分
            win_prob: 胜率
            extra_info: 额外信息
        """
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'ts_code': ts_code,
            'stock_name': stock_name,
            'action': action,
            'action_class': action_class,
            'score': score,
            'win_prob': win_prob,
            
            'trigger_factors': trigger_factors,
            'veto_factors': veto_factors,
            'is_vetoed': len(veto_factors) > 0,
            'final_reason': final_reason,
            
            'extra': extra_info or {}
        }
        
        self.session_logs.append(log_entry)
        self._append_to_daily_log(log_entry)
    
    def log_why_not_buy(self,
                        ts_code: str,
                        stock_name: str,
                        reasons: List[str]) -> None:
        """
        记录为什么不买
        
        用于解释系统为何没有推荐某只股票
        """
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'ts_code': ts_code,
            'stock_name': stock_name,
            'action': 'NOT_BUY',
            'action_class': 'skip',
            'reasons': reasons,
            'final_reason': '; '.join(reasons)
        }
        
        self.session_logs.append(log_entry)
        self._append_to_daily_log(log_entry)
    
    def log_trade_result(self,
                         ts_code: str,
                         entry_price: float,
                         exit_price: float,
                         profit_pct: float,
                         failure_type: str = None) -> None:
        """
        记录交易结果（用于复盘）
        
        Args:
            ts_code: 股票代码
            entry_price: 入场价
            exit_price: 出场价
            profit_pct: 盈亏比例
            failure_type: 失败类型（如：假突破、情绪退潮、资金撤离）
        """
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'type': 'TRADE_RESULT',
            'ts_code': ts_code,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'profit_pct': profit_pct,
            'is_win': profit_pct > 0,
            'failure_type': failure_type
        }
        
        self._append_to_daily_log(log_entry)
    
    def _append_to_daily_log(self, entry: Dict) -> None:
        """追加到当日日志文件"""
        today = datetime.now().strftime('%Y%m%d')
        log_file = self.log_dir / f'decisions_{today}.jsonl'
        
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"日志写入失败：{e}")
    
    def get_session_summary(self) -> Dict:
        """获取当前会话摘要"""
        if not self.session_logs:
            return {'total': 0}
        
        total = len(self.session_logs)
        vetoed = sum(1 for log in self.session_logs if log.get('is_vetoed', False))
        by_class = {}
        
        for log in self.session_logs:
            cls = log.get('action_class', 'unknown')
            by_class[cls] = by_class.get(cls, 0) + 1
        
        return {
            'total': total,
            'vetoed_count': vetoed,
            'by_action_class': by_class,
            'recent_logs': self.session_logs[-5:]
        }
    
    def get_daily_stats(self, date: str = None) -> Dict:
        """
        获取每日统计
        
        Args:
            date: 日期，格式 YYYYMMDD，默认今天
        """
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        
        log_file = self.log_dir / f'decisions_{date}.jsonl'
        
        if not log_file.exists():
            return {'date': date, 'total': 0}
        
        logs = []
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        logs.append(json.loads(line))
        except Exception as e:
            return {'date': date, 'error': str(e)}
        
        # 统计
        total = len(logs)
        decisions = [l for l in logs if l.get('type') != 'TRADE_RESULT']
        trades = [l for l in logs if l.get('type') == 'TRADE_RESULT']
        
        vetoed = sum(1 for l in decisions if l.get('is_vetoed', False))
        wins = sum(1 for t in trades if t.get('is_win', False))
        
        # 失败类型统计
        failure_types = {}
        for t in trades:
            if not t.get('is_win', True):
                ft = t.get('failure_type', 'unknown')
                failure_types[ft] = failure_types.get(ft, 0) + 1
        
        return {
            'date': date,
            'total_decisions': len(decisions),
            'vetoed_count': vetoed,
            'total_trades': len(trades),
            'win_count': wins,
            'win_rate': wins / len(trades) if trades else 0,
            'failure_types': failure_types
        }
    
    def get_failure_analysis(self, days: int = 7) -> Dict:
        """
        失败模式分析
        
        统计最近N天的失败类型分布
        """
        all_failures = {}
        
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y%m%d')
            stats = self.get_daily_stats(date)
            
            for ft, count in stats.get('failure_types', {}).items():
                all_failures[ft] = all_failures.get(ft, 0) + count
        
        # 排序
        sorted_failures = sorted(all_failures.items(), key=lambda x: x[1], reverse=True)
        
        return {
            'period_days': days,
            'failure_types': dict(sorted_failures),
            'top_failure': sorted_failures[0] if sorted_failures else None,
            'total_failures': sum(all_failures.values())
        }


# 需要导入
from datetime import timedelta


# ====== 全局日志器 ======
_logger = None

def get_decision_logger() -> DecisionLogger:
    """获取日志器单例"""
    global _logger
    if _logger is None:
        _logger = DecisionLogger()
    return _logger


def log_decision(ts_code: str,
                 stock_name: str,
                 action: str,
                 trigger_factors: List[str],
                 veto_factors: List[str],
                 final_reason: str,
                 **kwargs) -> None:
    """便捷函数：记录决策"""
    logger = get_decision_logger()
    logger.log_decision(
        ts_code=ts_code,
        stock_name=stock_name,
        action=action,
        action_class=kwargs.get('action_class', 'watch'),
        trigger_factors=trigger_factors,
        veto_factors=veto_factors,
        final_reason=final_reason,
        score=kwargs.get('score', 0),
        win_prob=kwargs.get('win_prob', 0),
        extra_info=kwargs.get('extra_info')
    )
