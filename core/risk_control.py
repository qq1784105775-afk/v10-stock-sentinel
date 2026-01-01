
import numpy as np

class RiskController:
    def __init__(self):
        pass

    def analyze(self, daily_data, flow_data, market_data, current_score):
        # 默认状态 (这就是你要的“生效证明”)
        momentum_msg = "✅ 动能平稳"
        behavior_msg = "✅ 资金正常"
        rri_msg = "✅ 环境安全"
        
        momentum_bonus = 0
        behavior_bonus = 0
        
        if not daily_data or len(daily_data) < 10:
            return {'bonus': 0, 'text': '⏳ 数据同步中...', 'rri': 0}

        # 1. 动能检测 (Momentum)
        closes = [x['close'] for x in daily_data[:5]]
        if len(closes) >= 3:
            delta_now = closes[0] - closes[1]
            delta_pre = closes[2] - closes[3]
            
            # 高位滞涨
            if delta_pre > 0 and delta_now <= 0 and current_score > 60:
                momentum_msg = "⚠️ 动能衰竭"
                momentum_bonus = -10
            # 低位止跌
            elif delta_pre < 0 and delta_now >= 0 and current_score < 40:
                momentum_msg = "✨ 止跌迹象"
                momentum_bonus = 5

        # 2. 行为检测 (Behavior)
        if len(flow_data) >= 3:
            flows = [x['main_net_inflow'] for x in flow_data[:3]]
            prices = [x['close'] for x in daily_data[:3]]
            
            # 出货嫌疑
            if sum(flows) < -50000000 and prices[0] < prices[2]:
                behavior_msg = "💀 主力出逃"
                behavior_bonus = -15
            # 吸筹嫌疑
            elif sum(flows) > 20000000 and abs(prices[0] - prices[2])/prices[2] < 0.05:
                behavior_msg = "🏦 主力吸筹"
                behavior_bonus = 10
                
        # 3. 环境检测 (RRI)
        rri = 0
        idx_chg = market_data.get('index_change', 0) if market_data else 0
        if idx_chg < -1.0: rri += 40
        if current_score < 40: rri += 30
        
        if rri > 70: rri_msg = "⛔ 环境高危"
        elif rri > 50: rri_msg = "☂️ 建议防守"

        # 组合文案
        final_text = f"{behavior_msg} | {momentum_msg} | {rri_msg}"
        
        return {
            'bonus': momentum_bonus + behavior_bonus,
            'text': final_text,
            'rri': rri
        }
