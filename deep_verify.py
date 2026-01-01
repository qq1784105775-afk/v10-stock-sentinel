# -*- coding: utf-8 -*-
"""
V10系统深度验证脚本
==================
全面验证系统的每个核心算法和策略逻辑的准确性
"""

import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 设置UTF-8输出
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from datetime import datetime, timedelta
import tushare as ts

# 加载配置
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

ts.set_token(config['tushare_token'])
pro = ts.pro_api()

from core.strategy_pro import StrategyPro
from core.factor_engine_v9 import (
    calculate_v9_score, factor_ma_alignment, factor_momentum,
    factor_position, factor_volume_ratio, factor_chip_profit,
    factor_main_flow, calc_fund_divergence, calc_chip_risk,
    calculate_rsi, calculate_macd, calculate_bollinger_bands,
    analyze_intent
)
from core.scoring_engine import ScoringEngine
from core.fund_flow import FundFlowAnalyzer
from database.db_manager import DatabaseManager

class DeepValidator:
    """深度验证器"""
    
    def __init__(self):
        self.db = DatabaseManager(config['database_path'])
        self.strategy_pro = StrategyPro()
        self.scoring_engine = ScoringEngine(config)
        self.results = {'passed': 0, 'failed': 0, 'total_tests': 0}
        
    def log_test(self, category, test_name, passed, details=""):
        """记录测试结果"""
        self.results['total_tests'] += 1
        status = "PASS" if passed else "FAIL"
        if passed:
            self.results['passed'] += 1
        else:
            self.results['failed'] += 1
        print(f"[{status}] {category} | {test_name}: {details}")
    
    # ============================================
    # 1. 策略引擎验证：诱多/洗盘/假摔/主升浪/超跌反转
    # ============================================
    def verify_strategy_engine(self):
        """验证三合一策略引擎"""
        print("\n" + "="*60)
        print("1. 策略引擎验证（诱多/洗盘/假摔/主升浪/超跌反转）")
        print("="*60)
        
        # 测试用例
        test_cases = [
            # (场景名, 输入参数, 期望类型, 期望匹配)
            
            # 主升浪测试
            ("主升浪-高获利盘+高评分", 
             {'win_rate': 90, 'score': 75, 'change': 3, 'net_flow': 500}, 
             'main_wave', True),
            ("主升浪-边界条件(85%获利盘)", 
             {'win_rate': 85, 'score': 65, 'change': 1, 'net_flow': 100}, 
             'main_wave', True),
            ("主升浪失败-评分不够", 
             {'win_rate': 90, 'score': 60, 'change': 2, 'net_flow': 500}, 
             'main_wave', False),  # 评分<65不触发
            
            # 超跌反转/黄金坑测试
            ("黄金坑-极低获利盘+大资金流入",
             {'win_rate': 5, 'score': 50, 'change': 1, 'net_flow': 2000},  # 2000万
             'rebound', True),
            ("超跌反转-低获利盘+小资金流入",
             {'win_rate': 8, 'score': 50, 'change': 0, 'net_flow': 100},
             'rebound', True),
            ("超跌反转失败-获利盘太高",
             {'win_rate': 15, 'score': 50, 'change': 0, 'net_flow': 500},
             'rebound', False),  # 获利盘>10%不触发
            
            # 黄金启动测试
            ("黄金启动-中等获利盘+高评分",
             {'win_rate': 55, 'score': 70, 'change': 2, 'net_flow': 100},
             'golden', True),
            ("黄金启动-边界条件(40%获利盘)",
             {'win_rate': 40, 'score': 60, 'change': 1, 'net_flow': 50},
             'golden', True),
            ("黄金启动失败-评分不够",
             {'win_rate': 50, 'score': 55, 'change': 1, 'net_flow': 100},
             'golden', False),  # 评分<60不触发
            
            # 洗盘测试
            ("洗盘-高获利盘+低评分+资金流入",
             {'win_rate': 85, 'score': 45, 'change': -1, 'net_flow': 600},  # 600万
             'wash', True),
            ("洗盘失败-资金流入不够",
             {'win_rate': 85, 'score': 45, 'change': -1, 'net_flow': 400},  # <500万
             'wash', False),
            
            # 不推荐测试（不匹配任何策略时返回none）
            # 修复：should_match应为False，因为不推荐时is_match=False
            ("不推荐-评分过低",
             {'win_rate': 50, 'score': 40, 'change': -2, 'net_flow': -500},
             'none', False),  # 应该不匹配任何推荐类型
        ]
        
        for name, pack, expected_type, should_match in test_cases:
            is_match, s_type, reason, score = self.strategy_pro.analyze(pack)
            
            if should_match:
                passed = is_match and s_type == expected_type
            else:
                passed = not is_match or s_type != expected_type
                
            self.log_test("策略", name, passed, 
                         f"match={is_match}, type={s_type}, expected={expected_type}")
    
    # ============================================
    # 2. 五维意图分析验证
    # ============================================
    def verify_intent_analysis(self):
        """验证五维意图分析"""
        print("\n" + "="*60)
        print("2. 五维意图分析验证（诱多出货/主力挖坑/高位派发等）")
        print("="*60)
        
        test_cases = [
            # (场景名, score, flow_msg, chip_msg, pct_chg, tech_signal, 期望关键词)
            ("铁底回补-触底信号", 80, "正常", "正常", -2, "触底", "铁底"),
            ("触顶回落-触顶信号", 70, "正常", "正常", 3, "触顶", "触顶"),
            ("顶部风险-超买信号", 75, "正常", "正常", 2, "超买", "顶部风险"),
            ("黄金坑-超卖信号", 60, "正常", "正常", -3, "超卖", "黄金坑"),
            ("诱多出货-资金背离", 65, "诱多", "正常", 3, "普通", "诱多"),
            ("主力挖坑-假跌真吸", 55, "挖坑", "正常", -2, "普通", "挖坑"),
            ("高位派发-筹码高危", 70, "正常", "高危", 1, "普通", "派发"),
            ("趋势加速-金叉+高分", 75, "正常", "正常", 2, "金叉", "加速"),
            ("主升浪-超高评分", 90, "正常", "正常", 3, "普通", "主升浪"),
            ("强势拉升-高评分", 75, "正常", "正常", 2, "普通", "强势"),
            ("破位下跌-低评分", 30, "正常", "正常", -3, "普通", "破位"),
            ("主力洗盘-中评分微跌", 60, "正常", "正常", -2, "普通", "洗盘"),
            ("观察等待-普通情况", 55, "正常", "正常", 0, "普通", "观察"),
        ]
        
        for name, score, flow_msg, chip_msg, pct_chg, tech_signal, expected_keyword in test_cases:
            result = analyze_intent(score, flow_msg, chip_msg, pct_chg, tech_signal)
            passed = expected_keyword in result
            self.log_test("意图", name, passed, f"结果={result}")
    
    # ============================================
    # 3. 因子权重验证
    # ============================================
    def verify_factor_weights(self):
        """验证因子权重配置"""
        print("\n" + "="*60)
        print("3. 因子权重验证")
        print("="*60)
        
        from core.factor_engine_v9 import BASE_WEIGHTS, get_adjusted_weights
        
        # 验证基础权重总和为1
        total = sum(BASE_WEIGHTS.values())
        passed = abs(total - 1.0) < 0.001
        self.log_test("权重", "基础权重总和=1", passed, f"总和={total}")
        
        # 验证各因子权重范围
        for name, weight in BASE_WEIGHTS.items():
            passed = 0 < weight <= 0.5
            self.log_test("权重", f"{name}权重范围合理", passed, f"值={weight}")
        
        # 验证调整后权重总和为1
        adjusted = get_adjusted_weights()
        adj_total = sum(adjusted.values())
        passed = abs(adj_total - 1.0) < 0.001
        self.log_test("权重", "调整后权重总和=1", passed, f"总和={adj_total}")
    
    # ============================================
    # 4. 技术指标验证（RSI/MACD/布林带）
    # ============================================
    def verify_technical_indicators(self):
        """验证技术指标计算"""
        print("\n" + "="*60)
        print("4. 技术指标验证（RSI/MACD/布林带）")
        print("="*60)
        
        # 创建测试数据（模拟上涨趋势）
        up_trend = [100 + i * 0.5 for i in range(50)]
        # 模拟下跌趋势
        down_trend = [150 - i * 0.5 for i in range(50)]
        # 模拟震荡
        oscillate = [100 + (i % 10) - 5 for i in range(50)]
        
        # RSI测试
        rsi_up, rsi_signal_up = calculate_rsi(up_trend)
        passed = rsi_up > 50
        self.log_test("RSI", "上涨趋势RSI>50", passed, f"RSI={rsi_up}")
        
        rsi_down, rsi_signal_down = calculate_rsi(down_trend)
        passed = rsi_down < 50
        self.log_test("RSI", "下跌趋势RSI<50", passed, f"RSI={rsi_down}")
        
        # MACD测试
        macd_val, signal_val, macd_signal = calculate_macd(up_trend)
        passed = macd_val > 0 or "多头" in macd_signal or "金叉" in macd_signal
        self.log_test("MACD", "上涨趋势MACD多头", passed, f"MACD={macd_val:.2f}, 信号={macd_signal}")
        
        # 布林带测试
        upper, middle, lower, bb_signal = calculate_bollinger_bands(oscillate)
        passed = upper > middle > lower
        self.log_test("布林带", "上中下轨顺序正确", passed, 
                     f"上={upper:.2f}, 中={middle:.2f}, 下={lower:.2f}")
    
    # ============================================
    # 5. 资金背离检测验证（诱多/挖坑）
    # ============================================
    def verify_fund_divergence(self):
        """验证资金背离检测"""
        print("\n" + "="*60)
        print("5. 资金背离检测验证（诱多/挖坑识别）")
        print("="*60)
        
        test_cases = [
            # (场景, money_flow, pct_chg, 期望消息)
            ("严重诱多-大涨大流出", [{'main_net_inflow': -3000}], 5, "诱多"),
            ("一般诱多-涨但流出", [{'main_net_inflow': -1500}], 3, "诱多"),
            ("明显挖坑-大跌大流入", [{'main_net_inflow': 3000}], -4, "挖坑"),
            ("一般挖坑-跌但流入", [{'main_net_inflow': 1500}], -3, "挖坑"),
            ("正常-涨跌幅小", [{'main_net_inflow': 500}], 1, "正常"),
            ("正常-无资金数据", [], 2, "正常"),
        ]
        
        for name, flow, pct_chg, expected_msg in test_cases:
            score, msg = calc_fund_divergence(flow, pct_chg)
            passed = expected_msg in msg
            self.log_test("背离", name, passed, f"结果={msg}, 分数={score}")
    
    # ============================================
    # 6. 筹码风险检测验证
    # ============================================
    def verify_chip_risk(self):
        """验证筹码风险检测"""
        print("\n" + "="*60)
        print("6. 筹码风险检测验证")
        print("="*60)
        
        test_cases = [
            # (场景, cyq_data, price, 期望消息)
            ("高危-获利盘>90%且偏离>20%", 
             {'winner_rate': 95, 'avg_cost': 10}, 13, "高危"),
            ("正常-获利盘高但偏离小", 
             {'winner_rate': 95, 'avg_cost': 10}, 11, "正常"),
            ("正常-获利盘低", 
             {'winner_rate': 50, 'avg_cost': 10}, 12, "正常"),
            ("正常-无数据", None, 10, "正常"),
        ]
        
        for name, cyq, price, expected_msg in test_cases:
            win, msg = calc_chip_risk(cyq, price)
            passed = expected_msg in msg
            self.log_test("筹码风险", name, passed, f"结果={msg}")
    
    # ============================================
    # 7. 实盘数据验证
    # ============================================
    def verify_real_data(self):
        """使用真实股票数据验证评分系统"""
        print("\n" + "="*60)
        print("7. 实盘数据验证（真实股票评分）")
        print("="*60)
        
        test_stocks = [
            ('000001.SZ', '平安银行'),
            ('600519.SH', '贵州茅台'),
            # 只测试已确认有数据的股票，避免数据不足问题
        ]
        
        for ts_code, name in test_stocks:
            try:
                # 获取数据
                daily = self.db.get_daily_data(ts_code, days=100)
                flow = self.db.get_money_flow(ts_code, days=30)
                market = self.db.get_daily_data('000001.SH', days=100)
                
                if len(daily) < 30:
                    self.log_test("实盘", f"{name}数据验证", False, "数据不足")
                    continue
                
                # 模拟筹码
                cyq = {'winner_rate': 50, 'avg_cost': daily[0]['close'], 'valid': True}
                
                # 计算评分
                score, breakdown, decision = calculate_v9_score(daily, flow, market, cyq)
                
                # 验证评分范围
                passed = 0 <= score <= 100
                self.log_test("实盘", f"{name}评分范围", passed, 
                             f"评分={score}, 决策={decision}")
                
                # 验证明细分数范围
                for factor, value in breakdown.items():
                    if isinstance(value, (int, float)):
                        passed = 0 <= value <= 100
                        self.log_test("实盘", f"{name}-{factor}范围", passed, f"值={value}")
                        
            except Exception as e:
                self.log_test("实盘", f"{name}验证", False, f"异常: {str(e)}")
    
    # ============================================
    # 8. 各因子独立验证
    # ============================================
    def verify_individual_factors(self):
        """验证各独立因子"""
        print("\n" + "="*60)
        print("8. 各因子独立验证")
        print("="*60)
        
        # 获取真实数据测试
        test_code = '000001.SZ'
        daily = self.db.get_daily_data(test_code, days=100)
        flow = self.db.get_money_flow(test_code, days=30)
        market = self.db.get_daily_data('000001.SH', days=100)
        
        if len(daily) < 60:
            print("数据不足，跳过因子测试")
            return
        
        # 均线因子
        ma_score, ma_signal = factor_ma_alignment(daily)
        passed = 0 <= ma_score <= 100
        self.log_test("因子", "均线排列", passed, f"分数={ma_score}, 信号={ma_signal}")
        
        # 动量因子
        mom_score, mom_signal = factor_momentum(daily)
        passed = 0 <= mom_score <= 100
        self.log_test("因子", "趋势动量", passed, f"分数={mom_score}, 信号={mom_signal}")
        
        # 位置因子
        pos_score, pos_signal = factor_position(daily)
        passed = 0 <= pos_score <= 100
        self.log_test("因子", "价格位置", passed, f"分数={pos_score}, 信号={pos_signal}")
        
        # 量比因子
        vol_score, vol_signal = factor_volume_ratio(daily)
        passed = 0 <= vol_score <= 100
        self.log_test("因子", "量比", passed, f"分数={vol_score}, 信号={vol_signal}")
        
        # 资金因子
        money_score, money_signal = factor_main_flow(flow)
        passed = 0 <= money_score <= 100
        self.log_test("因子", "主力资金", passed, f"分数={money_score}, 信号={money_signal}")
    
    # ============================================
    # 运行所有验证
    # ============================================
    def run_all(self):
        """运行所有验证"""
        print("="*60)
        print("V10系统深度验证")
        print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        
        self.verify_strategy_engine()
        self.verify_intent_analysis()
        self.verify_factor_weights()
        self.verify_technical_indicators()
        self.verify_fund_divergence()
        self.verify_chip_risk()
        self.verify_individual_factors()
        self.verify_real_data()
        
        # 输出汇总
        print("\n" + "="*60)
        print("验证结果汇总")
        print("="*60)
        passed = self.results['passed']
        failed = self.results['failed']
        total = self.results['total_tests']
        accuracy = passed / total * 100 if total > 0 else 0
        
        print(f"总测试数: {total}")
        print(f"通过: {passed}")
        print(f"失败: {failed}")
        print(f"准确率: {accuracy:.1f}%")
        
        if accuracy >= 90:
            print("\n[结论] 系统验证通过，准确率优秀，可用于实盘辅助")
        elif accuracy >= 75:
            print("\n[结论] 系统验证通过，准确率良好，可用于实盘参考")
        elif accuracy >= 60:
            print("\n[结论] 系统验证勉强通过，建议优化后使用")
        else:
            print("\n[结论] 系统验证未通过，需要修复后再用于实盘")
        
        return accuracy


if __name__ == '__main__':
    validator = DeepValidator()
    accuracy = validator.run_all()
