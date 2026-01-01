# -*- coding: utf-8 -*-
"""V10 Ultra Pro 核心逻辑验证"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

print("===== V10 Ultra Pro 核心逻辑验证 =====")

# 1. 测试DecisionCore裁判逻辑
from core.decision_core import DecisionCore, Priority, Signal
core = DecisionCore()
core.add_judgment(Priority.P3_TREND_CHIP, Signal.BUY, "评分70分", 0.7, "score")
core.add_judgment(Priority.P2_REALTIME_FUND, Signal.SELL, "主力流出3000万", 0.8, "fund")
verdict = core.make_verdict()
print(f"1. DecisionCore裁判: {verdict.action}")
print(f"   P2否决P3: is_vetoed={verdict.is_vetoed} (应为True)")

# 2. 测试胜率模型
from core.win_rate_model import quick_win_rate
wr = quick_win_rate(-3000, 70, "shock")
print(f"2. WinRate模型: prob={wr['win_prob']:.2f} (资金流出时应<0.5)")

# 3. 测试风控核按钮
from core.risk_control_enhanced import GlobalRiskState
risk = GlobalRiskState()
risk.consecutive_losses = 0  # 重置
risk.kill_switch_active = False
risk.record_trade_result(False, -0.05)
risk.record_trade_result(False, -0.03)
risk.record_trade_result(False, -0.02)
allowed, reason = risk.is_trading_allowed()
print(f"3. 核按钮: 连续3次亏损后 allowed={allowed} (应为False)")
risk.deactivate_kill_switch()

# 4. 测试出场逻辑
from core.exit_strategy import should_exit_position
exit_r = should_exit_position(10.0, 9.4, 10.2, hold_days=5)
print(f"4. 出场策略: should_exit={exit_r['should_exit']} reason={exit_r['reason']} (应为stop_loss)")

# 5. 测试筹码决策闭环
from core.chip_engine_v9 import get_chip_decision_signal
cyq_high = {"winner_rate": 96, "avg_cost": 80, "valid": True}
chip_sig = get_chip_decision_signal(cyq_high, 100)
print(f"5. 筹码决策: signal={chip_sig['signal']} (获利盘96%+溢价应为VETO)")

# 6. 测试雷达反馈
from core.radar import RadarManager
radar = RadarManager()
adj = radar.get_strategy_adjustment(["急跌A", "急跌B", "急跌C"])
print(f"6. 雷达反馈: action={adj['action']} (多只急跌应为reduce)")

# 7. 测试情绪状态
from core.market_monitor import MarketMonitor
mm = MarketMonitor({"alert_rules": {"thunder_scan": {"min_rise_pct":5, "min_main_inflow":1000, "beep_count":3}, "tail_guard": {"min_fall_pct":3, "beep_count":2}}})
index_data = [{"change_pct": -2.5}, {"change_pct": 1.2}, {"change_pct": -0.5}, {"change_pct": -1.0}, {"change_pct": -1.5}]
level, text, emotion = mm.calculate_market_sentiment(index_data)
print(f"7. 情绪识别: level={level} emotion={emotion}")

print("===== 验证完成 =====")
