import numpy as np
from datetime import datetime, timedelta

class FactorEngine:
    def __init__(self, config):
        self.config = config
    
    def calculate_ma(self, prices, period):
        if len(prices) < period:
            return None
        return sum(prices[:period]) / period
    
    def calculate_trend_score(self, daily_data):
        if len(daily_data) < 60:
            return 0, "数据不足"
        
        closes = [d['close'] for d in daily_data]
        closes.reverse()
        
        ma5 = self.calculate_ma(closes[-5:], 5)
        ma10 = self.calculate_ma(closes[-10:], 10)
        ma20 = self.calculate_ma(closes[-20:], 20)
        ma60 = self.calculate_ma(closes[-60:], 60)
        
        if not all([ma5, ma10, ma20, ma60]):
            return 0, "均线计算失败"
        
        score = 0
        signals = []
        
        if ma5 > ma10:
            score += 30
            signals.append("短期向上")
        if ma10 > ma20:
            score += 25
            signals.append("中期走强")
        if ma20 > ma60:
            score += 20
            signals.append("长期趋势向上")
        
        recent_3 = closes[-3:]
        if len(recent_3) == 3 and recent_3[0] < recent_3[1] < recent_3[2]:
            score += 15
            signals.append("连续上涨")
        
        recent_5_high = max(closes[-5:])
        recent_5_low = min(closes[-5:])
        amplitude = (recent_5_high - recent_5_low) / recent_5_low * 100
        
        if amplitude < 8:
            score += 10
            signals.append("振幅温和")
        elif amplitude > 15:
            score -= 10
            signals.append("振幅过大")
        
        return min(score, 100), " | ".join(signals) if signals else "趋势不明"
    
    def calculate_volume_score(self, daily_data):
        if len(daily_data) < 10:
            return 0, "数据不足"
        
        volumes = [d['vol'] for d in daily_data]
        volumes.reverse()
        
        current_vol = volumes[-1]
        avg_vol_5 = sum(volumes[-6:-1]) / 5
        
        if avg_vol_5 == 0:
            return 0, "成交量数据异常"
        
        volume_ratio = current_vol / avg_vol_5
        
        score = 0
        signals = []
        
        if volume_ratio >= 2.0:
            score += 50
            signals.append("巨量放出")
        elif volume_ratio >= 1.5:
            score += 35
            signals.append("明显放量")
        elif volume_ratio >= 1.2:
            score += 20
            signals.append("温和放量")
        elif volume_ratio < 0.8:
            score -= 10
            signals.append("缩量")
        
        recent_3_vols = volumes[-3:]
        if len(recent_3_vols) == 3 and recent_3_vols[0] < recent_3_vols[1] < recent_3_vols[2]:
            score += 30
            signals.append("量能递增")
        
        amounts = [d['amount'] for d in daily_data]
        amounts.reverse()
        current_amount = amounts[-1]
        
        if current_amount > 100000:
            score += 20
            signals.append("交投活跃")
        
        return min(score, 100), " | ".join(signals) if signals else "量能一般"
    
    def calculate_position_score(self, daily_data):
        if len(daily_data) < 60:
            return 0, "数据不足"
        
        closes = [d['close'] for d in daily_data]
        closes.reverse()
        
        current_price = closes[-1]
        ma60 = self.calculate_ma(closes[-60:], 60)
        
        if not ma60:
            return 0, "均线计算失败"
        
        low_threshold = ma60 * self.config['position_rules']['low_position_multiplier']
        
        score = 0
        signals = []
        
        if current_price <= low_threshold:
            score += 80
            signals.append("低位盘整")
        elif current_price <= ma60 * 1.2:
            score += 50
            signals.append("相对低位")
        elif current_price <= ma60 * 1.3:
            score += 30
            signals.append("中低位置")
        else:
            score += 10
            signals.append("偏高位置")
        
        high_60 = max(closes[-60:])
        retracement = (high_60 - current_price) / high_60 * 100
        
        if retracement >= 30:
            score += 20
            signals.append("深度回调")
        elif retracement >= 20:
            score += 15
            signals.append("充分调整")
        
        return min(score, 100), " | ".join(signals) if signals else "位置适中"
    
    def calculate_market_sync_score(self, stock_data, market_data):
        if len(stock_data) < 5 or len(market_data) < 5:
            return 50, "对比数据不足"
        
        stock_changes = [d['change_pct'] for d in stock_data[:5]]
        market_changes = [d['change_pct'] for d in market_data[:5]]
        
        stock_changes.reverse()
        market_changes.reverse()
        
        sync_count = 0
        for sc, mc in zip(stock_changes, market_changes):
            if (sc > 0 and mc > 0) or (sc < 0 and mc < 0):
                sync_count += 1
        
        if sync_count >= 4:
            return 80, "高度同步大盘"
        elif sync_count >= 3:
            return 60, "跟随大盘"
        else:
            return 40, "独立走势"
    
    def calculate_theme_heat_score(self, money_flow_data):
        if len(money_flow_data) < 3:
            return 0, "资金数据不足"
        
        consecutive_inflow = 0
        for flow in money_flow_data[:3]:
            if flow['main_net_inflow'] > 0:
                consecutive_inflow += 1
            else:
                break
        
        if consecutive_inflow >= 3:
            return 100, "主力连续3天流入"
        elif consecutive_inflow >= 2:
            return 70, "主力连续2天流入"
        elif money_flow_data[0]['main_net_inflow'] > 10000000:
            return 40, "主力大额流入"
        else:
            return 0, "主力未明显介入"
    
    def detect_fake_drop(self, daily_data, money_flow_data):
        if len(daily_data) < 1 or len(money_flow_data) < 2:
            return False, None
        
        latest_change = daily_data[0]['change_pct']
        min_fall = self.config['fake_drop_rules']['min_fall_pct']
        
        if latest_change > -min_fall:
            return False, None
        
        consecutive_days = self.config['fake_drop_rules']['min_consecutive_days']
        inflow_count = 0
        
        for flow in money_flow_data[:consecutive_days]:
            if flow['main_net_inflow'] > 0:
                inflow_count += 1
        
        if inflow_count >= consecutive_days:
            total_inflow = sum([f['main_net_inflow'] for f in money_flow_data[:consecutive_days]])
            return True, {
                'fall_pct': abs(latest_change),
                'consecutive_days': consecutive_days,
                'total_inflow': total_inflow
            }
        
        return False, None
    
    def check_consecutive_main_force(self, money_flow_data):
        if len(money_flow_data) < 2:
            return False, 0
        
        min_days = self.config['main_force_rules']['min_consecutive_days']
        threshold = self.config['main_force_rules']['single_day_threshold']
        
        consecutive_count = 0
        for flow in money_flow_data:
            if flow['main_net_inflow'] >= threshold:
                consecutive_count += 1
            else:
                break
            
            if consecutive_count >= min_days:
                return True, consecutive_count
        
        return False, consecutive_count
