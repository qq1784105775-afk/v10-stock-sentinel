# -*- coding: utf-8 -*-
"""
V10 Ultra Pro：数据有效性校验层 (Data Validator)
================================================
校验项：
- 缺失值检测
- 异常跳变检测
- 成交量为0检测
- 跨源一致性校验
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np


class DataValidationError(Exception):
    """数据校验异常"""
    pass


class DataValidator:
    """数据校验器"""
    
    # ====== 校验阈值 ======
    PRICE_JUMP_THRESHOLD = 0.11   # 涨跌停11%（含ST）
    VOLUME_ZERO_WARNING = True
    MIN_DATA_POINTS = 5           # 最少数据点
    MAX_MISSING_RATIO = 0.3       # 最大缺失比例
    
    def __init__(self, strict_mode: bool = False):
        """
        初始化校验器
        
        Args:
            strict_mode: 严格模式，校验失败抛异常
        """
        self.strict_mode = strict_mode
        self.validation_results: List[Dict] = []
    
    def validate_daily_data(self, daily: List[Dict]) -> Tuple[bool, List[str]]:
        """
        校验日线数据
        
        Returns:
            (是否通过, 问题列表)
        """
        issues = []
        
        if not daily:
            issues.append("日线数据为空")
            return False, issues
        
        if len(daily) < self.MIN_DATA_POINTS:
            issues.append(f"数据点不足：{len(daily)} < {self.MIN_DATA_POINTS}")
        
        # 检查缺失值
        required_fields = ['close', 'open', 'high', 'low', 'vol']
        for i, row in enumerate(daily[:10]):  # 只检查最近10条
            for field in required_fields:
                if field not in row or row[field] is None:
                    issues.append(f"第{i+1}条缺少{field}")
        
        # 检查异常跳变
        for i in range(len(daily) - 1):
            if i >= 10:
                break
            curr_close = daily[i].get('close', 0)
            prev_close = daily[i+1].get('close', 0)
            
            if prev_close > 0:
                change = abs(curr_close - prev_close) / prev_close
                if change > self.PRICE_JUMP_THRESHOLD:
                    issues.append(f"第{i+1}条价格跳变异常：{change*100:.1f}%")
        
        # 检查零成交量
        zero_vol_count = sum(1 for d in daily[:10] if d.get('vol', 0) == 0)
        if zero_vol_count > 3:
            issues.append(f"近期{zero_vol_count}天成交量为0")
        
        is_valid = len(issues) == 0
        self._log_result("daily_data", is_valid, issues)
        
        return is_valid, issues
    
    def validate_fund_flow(self, flow: List[Dict]) -> Tuple[bool, List[str]]:
        """
        校验资金流数据
        
        Returns:
            (是否通过, 问题列表)
        """
        issues = []
        
        if not flow:
            issues.append("资金流数据为空")
            return False, issues
        
        # 检查必要字段
        required_fields = ['main_net_inflow']
        for i, row in enumerate(flow[:5]):
            for field in required_fields:
                if field not in row:
                    issues.append(f"第{i+1}条缺少{field}")
        
        # 检查数值合理性
        for i, row in enumerate(flow[:5]):
            net_flow = row.get('main_net_inflow', 0) or 0
            # 单日资金流超过50亿可能异常
            if abs(net_flow) > 500000:  # 50亿 = 500000万
                issues.append(f"第{i+1}条资金流异常大：{net_flow/10000:.1f}亿")
        
        is_valid = len(issues) == 0
        self._log_result("fund_flow", is_valid, issues)
        
        return is_valid, issues
    
    def validate_realtime_data(self, realtime: Dict) -> Tuple[bool, List[str]]:
        """
        校验实时数据
        
        Returns:
            (是否通过, 问题列表)
        """
        issues = []
        
        if not realtime:
            issues.append("实时数据为空")
            return False, issues
        
        if not realtime.get('valid', False):
            issues.append("实时数据标记为无效")
        
        price = realtime.get('price', 0)
        if price <= 0:
            issues.append(f"价格无效：{price}")
        
        # 检查涨跌幅是否合理
        change_pct = realtime.get('change_pct', 0)
        if abs(change_pct) > 11:
            issues.append(f"涨跌幅异常：{change_pct}%")
        
        is_valid = len(issues) == 0
        self._log_result("realtime", is_valid, issues)
        
        return is_valid, issues
    
    def validate_cross_source(self, 
                              source1_data: Dict,
                              source2_data: Dict,
                              tolerance: float = 0.05) -> Tuple[bool, List[str]]:
        """
        跨源一致性校验
        
        Args:
            source1_data: 源1数据（包含price, change_pct等）
            source2_data: 源2数据
            tolerance: 容差比例
            
        Returns:
            (是否一致, 差异列表)
        """
        issues = []
        
        # 价格一致性
        price1 = source1_data.get('price', 0)
        price2 = source2_data.get('price', 0)
        
        if price1 > 0 and price2 > 0:
            diff = abs(price1 - price2) / price1
            if diff > tolerance:
                issues.append(f"价格不一致：{price1} vs {price2}（差异{diff*100:.2f}%）")
        
        # 涨跌幅一致性
        change1 = source1_data.get('change_pct', 0)
        change2 = source2_data.get('change_pct', 0)
        
        if abs(change1 - change2) > 1:  # 1个百分点差异
            issues.append(f"涨跌幅不一致：{change1}% vs {change2}%")
        
        is_valid = len(issues) == 0
        self._log_result("cross_source", is_valid, issues)
        
        return is_valid, issues
    
    def fill_missing_values(self, daily: List[Dict]) -> List[Dict]:
        """
        缺失值回填策略
        
        策略：
        1. 价格缺失用前一日收盘价
        2. 成交量缺失用近5日均值
        """
        if not daily:
            return daily
        
        filled = []
        for i, row in enumerate(daily):
            new_row = row.copy()
            
            # 价格回填
            for field in ['close', 'open', 'high', 'low']:
                if new_row.get(field) is None:
                    if i + 1 < len(daily):
                        new_row[field] = daily[i+1].get(field, 0)
            
            # 成交量回填
            if new_row.get('vol') is None or new_row.get('vol') == 0:
                # 用近5日均值
                vol_sum = 0
                vol_count = 0
                for j in range(i+1, min(i+6, len(daily))):
                    if daily[j].get('vol', 0) > 0:
                        vol_sum += daily[j]['vol']
                        vol_count += 1
                if vol_count > 0:
                    new_row['vol'] = vol_sum / vol_count
            
            filled.append(new_row)
        
        return filled
    
    def _log_result(self, data_type: str, is_valid: bool, issues: List[str]) -> None:
        """记录校验结果"""
        self.validation_results.append({
            'type': data_type,
            'valid': is_valid,
            'issues': issues,
            'timestamp': datetime.now().isoformat()
        })
    
    def get_validation_summary(self) -> Dict:
        """获取校验汇总"""
        total = len(self.validation_results)
        passed = sum(1 for r in self.validation_results if r['valid'])
        
        return {
            'total_validations': total,
            'passed': passed,
            'failed': total - passed,
            'pass_rate': passed / total if total > 0 else 0,
            'recent_issues': [
                r['issues'] for r in self.validation_results 
                if not r['valid']
            ][-5:]  # 最近5个失败
        }


# ====== 全局校验器 ======
_validator = None

def get_validator() -> DataValidator:
    """获取校验器单例"""
    global _validator
    if _validator is None:
        _validator = DataValidator()
    return _validator


def validate_stock_data(daily: List[Dict], 
                        flow: List[Dict] = None,
                        realtime: Dict = None) -> Tuple[bool, Dict]:
    """
    便捷函数：一次性校验所有数据
    
    Returns:
        (是否全部通过, 详细结果)
    """
    validator = get_validator()
    results = {}
    all_valid = True
    
    # 日线校验
    valid, issues = validator.validate_daily_data(daily)
    results['daily'] = {'valid': valid, 'issues': issues}
    if not valid:
        all_valid = False
    
    # 资金流校验
    if flow is not None:
        valid, issues = validator.validate_fund_flow(flow)
        results['fund_flow'] = {'valid': valid, 'issues': issues}
        if not valid:
            all_valid = False
    
    # 实时数据校验
    if realtime is not None:
        valid, issues = validator.validate_realtime_data(realtime)
        results['realtime'] = {'valid': valid, 'issues': issues}
        if not valid:
            all_valid = False
    
    return all_valid, results
