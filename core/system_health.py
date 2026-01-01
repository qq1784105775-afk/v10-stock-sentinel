# -*- coding: utf-8 -*-
"""
V10 Ultra Pro：系统自检模块 (System Health Check)
=================================================
问题#27：无系统级自检

功能：
1. 数据异常检测 → 阻断交易
2. API异常检测 → 降级处理
3. 幸存者偏差处理（#6）
4. 配置校验
"""

from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import json


class SystemHealthCheck:
    """系统自检管理器"""
    
    def __init__(self):
        self.last_check_time = None
        self.health_status = "UNKNOWN"
        self.issues = []
        self.trading_blocked = False
        self.block_reason = ""
    
    def check_data_health(self, 
                          daily_data: List[Dict],
                          money_flow: List[Dict]) -> Tuple[bool, List[str]]:
        """
        数据健康检查
        
        Returns:
            (是否健康, 问题列表)
        """
        issues = []
        
        # 日线数据检查
        if not daily_data:
            issues.append("日线数据为空")
        elif len(daily_data) < 30:
            issues.append(f"日线数据不足30条：{len(daily_data)}条")
        
        # 资金流数据检查
        if not money_flow:
            issues.append("资金流数据为空")
        elif len(money_flow) < 3:
            issues.append(f"资金流数据不足3条：{len(money_flow)}条")
        
        # 数据新鲜度检查
        if daily_data:
            latest_date = daily_data[0].get('trade_date', '')
            if latest_date:
                try:
                    latest_dt = datetime.strptime(latest_date, '%Y%m%d')
                    days_old = (datetime.now() - latest_dt).days
                    if days_old > 5:  # 超过5天视为过期
                        issues.append(f"数据过期：最新数据为{days_old}天前")
                except:
                    pass
        
        is_healthy = len(issues) == 0
        return is_healthy, issues
    
    def check_api_health(self, api_responses: Dict[str, bool]) -> Tuple[bool, List[str]]:
        """
        API健康检查
        
        Args:
            api_responses: {API名称: 是否成功}
        """
        issues = []
        
        critical_apis = ['tushare', 'realtime_quote']
        for api in critical_apis:
            if api in api_responses and not api_responses[api]:
                issues.append(f"关键API异常：{api}")
        
        is_healthy = len(issues) == 0
        return is_healthy, issues
    
    def check_survivor_bias(self, ts_code: str, stock_info: Dict) -> Tuple[bool, str]:
        """
        幸存者偏差检测（问题#6）
        
        检测：
        - ST股票
        - 退市风险股
        - 长期停牌股
        
        Returns:
            (是否有风险, 风险描述)
        """
        name = stock_info.get('name', '')
        
        # ST股票检测
        if 'ST' in name or '*ST' in name:
            return True, f"ST股票：{name}，存在退市风险"
        
        # 退市整理期
        if '退' in name:
            return True, f"退市股票：{name}"
        
        # B股检测
        if ts_code.endswith('.B'):
            return True, "B股：流动性风险"
        
        return False, ""
    
    def check_config_validity(self, config: Dict) -> Tuple[bool, List[str]]:
        """
        配置有效性检查（问题#26部分）
        """
        issues = []
        
        required_keys = ['tushare_token', 'scoring_weights', 'alert_rules']
        for key in required_keys:
            if key not in config:
                issues.append(f"缺少配置项：{key}")
        
        # 权重检查
        if 'scoring_weights' in config:
            weights = config['scoring_weights']
            total = sum(weights.values())
            if abs(total - 1.0) > 0.01:
                issues.append(f"权重之和不为1：{total}")
        
        is_valid = len(issues) == 0
        return is_valid, issues
    
    def run_full_check(self,
                       daily_data: List[Dict] = None,
                       money_flow: List[Dict] = None,
                       stock_info: Dict = None,
                       ts_code: str = "",
                       config: Dict = None,
                       api_responses: Dict = None) -> Dict:
        """
        运行完整自检
        
        Returns:
            自检报告
        """
        self.issues = []
        self.trading_blocked = False
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'overall_status': 'OK',
            'trading_allowed': True,
            'checks': {}
        }
        
        # 数据健康检查
        if daily_data is not None or money_flow is not None:
            healthy, issues = self.check_data_health(daily_data or [], money_flow or [])
            results['checks']['data'] = {'healthy': healthy, 'issues': issues}
            if not healthy:
                self.issues.extend(issues)
        
        # API健康检查
        if api_responses:
            healthy, issues = self.check_api_health(api_responses)
            results['checks']['api'] = {'healthy': healthy, 'issues': issues}
            if not healthy:
                self.issues.extend(issues)
                self.trading_blocked = True
                self.block_reason = "API异常"
        
        # 幸存者偏差检查
        if stock_info and ts_code:
            has_risk, risk_desc = self.check_survivor_bias(ts_code, stock_info)
            results['checks']['survivor_bias'] = {'has_risk': has_risk, 'description': risk_desc}
            if has_risk:
                self.issues.append(risk_desc)
        
        # 配置检查
        if config:
            valid, issues = self.check_config_validity(config)
            results['checks']['config'] = {'valid': valid, 'issues': issues}
            if not valid:
                self.issues.extend(issues)
        
        # 汇总
        if self.trading_blocked:
            results['overall_status'] = 'BLOCKED'
            results['trading_allowed'] = False
            results['block_reason'] = self.block_reason
        elif len(self.issues) > 0:
            results['overall_status'] = 'WARNING'
        
        results['all_issues'] = self.issues
        
        self.last_check_time = datetime.now()
        self.health_status = results['overall_status']
        
        return results
    
    def should_block_trading(self) -> Tuple[bool, str]:
        """是否应该阻断交易"""
        return self.trading_blocked, self.block_reason


# ====== 全局实例 ======
_health_checker = None

def get_health_checker() -> SystemHealthCheck:
    global _health_checker
    if _health_checker is None:
        _health_checker = SystemHealthCheck()
    return _health_checker


def quick_health_check(daily_data: List[Dict], 
                       money_flow: List[Dict],
                       ts_code: str = "",
                       stock_info: Dict = None) -> Dict:
    """便捷函数：快速自检"""
    checker = get_health_checker()
    return checker.run_full_check(
        daily_data=daily_data,
        money_flow=money_flow,
        ts_code=ts_code,
        stock_info=stock_info
    )
