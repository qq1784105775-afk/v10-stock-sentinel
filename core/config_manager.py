# -*- coding: utf-8 -*-
"""
V10 Ultra Pro：配置管理器 (Config Manager)
=========================================
问题#26：配置与逻辑耦合

修复：
1. 集中配置管理
2. 参数外置
3. 配置校验
4. 动态配置更新
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime


class ConfigManager:
    """配置管理器"""
    
    # 默认配置
    DEFAULT_CONFIG = {
        # ====== 评分权重 ======
        "scoring_weights": {
            "trend": 0.20,
            "volume": 0.15,
            "position": 0.15,
            "chip": 0.20,
            "money": 0.20,
            "market": 0.10
        },
        
        # ====== 否决阈值 ======
        "veto_thresholds": {
            "fund_outflow_max": -2000,      # 资金流出超此值否决（万元）
            "buy_sell_ratio_min": 0.5,      # 买卖力量比最低
            "max_drawdown": 0.15,           # 最大回撤
            "consecutive_loss_max": 3       # 连续亏损次数
        },
        
        # ====== 风控参数 ======
        "risk_control": {
            "stop_loss_pct": -5.0,          # 止损比例
            "take_profit_pct": 10.0,        # 止盈比例
            "trailing_stop_pct": 3.0,       # 移动止损
            "max_hold_days": 20,            # 最大持仓天数
            "max_position_pct": 0.3         # 单票最大仓位
        },
        
        # ====== 因子配置 ======
        "factor_config": {
            "ma_periods": [5, 10, 20, 60],  # 均线周期
            "rsi_period": 14,               # RSI周期
            "macd_params": [12, 26, 9],     # MACD参数
            "volume_ma_period": 5           # 量能均线周期
        },
        
        # ====== 市场状态调整 ======
        "regime_adjustments": {
            "bull": {"trend": 1.3, "chip": 0.8, "money": 1.2},
            "bear": {"money": 1.5, "chip": 1.2, "trend": 0.6},
            "shock": {"volume": 1.2, "chip": 1.1, "money": 1.3}
        },
        
        # ====== 告警规则 ======
        "alert_rules": {
            "thunder_scan": {
                "min_rise_pct": 5,
                "min_main_inflow": 1000,
                "beep_count": 3
            },
            "tail_guard": {
                "min_fall_pct": 3,
                "beep_count": 2
            }
        }
    }
    
    def __init__(self, config_path: str = None):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = Path(config_path) if config_path else None
        self.config = self.DEFAULT_CONFIG.copy()
        self.loaded_from_file = False
        
        if self.config_path and self.config_path.exists():
            self._load_from_file()
    
    def _load_from_file(self) -> None:
        """从文件加载配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
            self._merge_config(file_config)
            self.loaded_from_file = True
            print(f"✅ 配置加载成功：{self.config_path}")
        except Exception as e:
            print(f"⚠️ 配置加载失败，使用默认配置：{e}")
    
    def _merge_config(self, new_config: Dict) -> None:
        """合并配置（深度合并）"""
        def deep_merge(base: Dict, override: Dict) -> Dict:
            result = base.copy()
            for key, value in override.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = deep_merge(result[key], value)
                else:
                    result[key] = value
            return result
        
        self.config = deep_merge(self.config, new_config)
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项
        
        支持点号分隔的嵌套键，如 "risk_control.stop_loss_pct"
        """
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """设置配置项（支持嵌套键）"""
        keys = key.split('.')
        target = self.config
        
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]
        
        target[keys[-1]] = value
    
    def get_scoring_weights(self) -> Dict[str, float]:
        """获取评分权重"""
        return self.get('scoring_weights', self.DEFAULT_CONFIG['scoring_weights'])
    
    def get_veto_thresholds(self) -> Dict:
        """获取否决阈值"""
        return self.get('veto_thresholds', self.DEFAULT_CONFIG['veto_thresholds'])
    
    def get_risk_control(self) -> Dict:
        """获取风控参数"""
        return self.get('risk_control', self.DEFAULT_CONFIG['risk_control'])
    
    def get_regime_adjustment(self, regime: str) -> Dict:
        """获取市场状态调整系数"""
        adjustments = self.get('regime_adjustments', {})
        return adjustments.get(regime, {})
    
    def validate(self) -> tuple:
        """
        校验配置有效性
        
        Returns:
            (是否有效, 问题列表)
        """
        issues = []
        
        # 权重校验
        weights = self.get_scoring_weights()
        if weights:
            total = sum(weights.values())
            if abs(total - 1.0) > 0.01:
                issues.append(f"评分权重之和 {total:.2f} ≠ 1.0")
        
        # 风控参数校验
        risk = self.get_risk_control()
        if risk.get('stop_loss_pct', 0) >= 0:
            issues.append("止损比例应为负数")
        if risk.get('take_profit_pct', 0) <= 0:
            issues.append("止盈比例应为正数")
        
        return len(issues) == 0, issues
    
    def save(self, path: str = None) -> bool:
        """保存配置到文件"""
        save_path = Path(path) if path else self.config_path
        if not save_path:
            return False
        
        try:
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"配置保存失败：{e}")
            return False
    
    def to_dict(self) -> Dict:
        """导出为字典"""
        return self.config.copy()


# ====== 全局配置实例 ======
_config_manager = None

def get_config_manager(config_path: str = None) -> ConfigManager:
    """获取配置管理器单例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(config_path)
    return _config_manager


def get_config(key: str, default: Any = None) -> Any:
    """便捷函数：获取配置"""
    return get_config_manager().get(key, default)
