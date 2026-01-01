from datetime import datetime, time

class MarketMonitor:
    def __init__(self, config):
        self.config = config
        self.thunder_rules = config['alert_rules']['thunder_scan']
        self.tail_rules = config['alert_rules']['tail_guard']
    
    def get_market_status(self):
        now = datetime.now()
        current_time = now.time()
        weekday = now.weekday()
        
        if weekday >= 5:
            return 'closed', '休市'
        
        morning_open = time(9, 30)
        morning_close = time(11, 30)
        afternoon_open = time(13, 0)
        afternoon_close = time(15, 0)
        
        if morning_open <= current_time <= morning_close:
            return 'trading', '交易中'
        elif afternoon_open <= current_time <= afternoon_close:
            return 'trading', '交易中'
        elif time(9, 15) <= current_time < morning_open:
            return 'call_auction', '集合竞价'
        else:
            return 'closed', '闭市'
    
    def is_thunder_scan_time(self):
        status, _ = self.get_market_status()
        if status != 'trading':
            return False
        
        now = datetime.now()
        current_time = now.time()
        morning_start = time(9, 30)
        morning_end = time(9, 45)
        afternoon_start = time(13, 0)
        afternoon_end = time(13, 15)
        
        return (morning_start <= current_time <= morning_end or 
                afternoon_start <= current_time <= afternoon_end)
    
    def is_tail_guard_time(self):
        status, _ = self.get_market_status()
        if status != 'trading':
            return False
        
        now = datetime.now()
        current_time = now.time()
        tail_time = time(14, 50)
        close_time = time(15, 0)
        
        return tail_time <= current_time <= close_time
    
    def check_thunder_alert(self, current_price, open_price, main_inflow):
        if not self.is_thunder_scan_time():
            return False, None
        
        if open_price == 0:
            return False, None
        
        rise_pct = (current_price - open_price) / open_price * 100
        
        if (rise_pct >= self.thunder_rules['min_rise_pct'] and 
            main_inflow >= self.thunder_rules['min_main_inflow']):
            return True, {
                'rise_pct': rise_pct,
                'main_inflow': main_inflow,
                'beep_count': self.thunder_rules['beep_count']
            }
        
        return False, None
    
    def check_tail_guard_alert(self, current_price, pre_close, main_outflow):
        if not self.is_tail_guard_time():
            return False, None
        
        if pre_close == 0:
            return False, None
        
        fall_pct = (current_price - pre_close) / pre_close * 100
        
        if (fall_pct <= -self.tail_rules['min_fall_pct'] and 
            main_outflow >= 0):
            return True, {
                'fall_pct': abs(fall_pct),
                'main_outflow': main_outflow,
                'beep_count': self.tail_rules['beep_count']
            }
        
        return False, None
    
    def calculate_market_sentiment(self, index_data):
        """
        V10 Ultra Pro: 情绪模块输出状态标签
        
        状态标签：
        - 情绪升温
        - 高位退潮
        - 冰点修复
        - 极度恐慌
        - 极度乐观
        """
        if len(index_data) < 5:
            return 'unknown', '数据不足', '无状态'
        
        recent_5 = index_data[:5]
        up_count = sum(1 for d in recent_5 if d['change_pct'] > 0)
        avg_change = sum(d['change_pct'] for d in recent_5) / 5
        
        latest_change = index_data[0]['change_pct']
        prev_change = index_data[1]['change_pct'] if len(index_data) > 1 else 0
        
        # V10新增：状态变化检测
        emotion_state = "中性"
        
        # 情绪升温：从跌转涨或连续上涨加速
        if prev_change < 0 and latest_change > 1:
            emotion_state = "⬆️ 情绪升温"
        elif prev_change > 0 and latest_change > prev_change and latest_change > 1:
            emotion_state = "🔥 加速升温"
        
        # 高位退潮：从涨转跌
        elif prev_change > 1 and latest_change < -0.5:
            emotion_state = "⬇️ 高位退潮"
        
        # 冰点修复：连续大跌后反弹
        elif avg_change < -2 and latest_change > 0:
            emotion_state = "💎 冰点修复"
        
        # 原有情绪判断
        if latest_change > 2 and up_count >= 4:
            return 'very_strong', '极强', emotion_state
        elif latest_change > 0.5 and up_count >= 3:
            return 'strong', '强势', emotion_state
        elif latest_change < -2 and up_count <= 1:
            return 'very_weak', '极弱', emotion_state
        elif latest_change < -0.5 and up_count <= 2:
            return 'weak', '弱势', emotion_state
        else:
            return 'neutral', '震荡', emotion_state

    
    def should_show_nuclear_button(self, sentiment_level):
        return sentiment_level == 'very_weak'
