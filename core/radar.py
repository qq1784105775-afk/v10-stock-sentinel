
import requests
from datetime import datetime

class RadarManager:
    def __init__(self):
        # 内存缓存：记录上一次扫描的价格
        # { '000001.SZ': {'price': 10.0, 'time': 1700000000} }
        self.cache = {}

    def scan(self, stock_list):
        anomalies = []
        if not stock_list: return []
        
        # 1. 构造腾讯接口代码
        tx_codes = []
        map_code = {} # sz000001 -> 000001.SZ
        for s in stock_list:
            code = s['ts_code']
            market, num = code.split('.')[1], code.split('.')[0] # Tushare: 000001.SZ
            tx_code = f"{market.lower()}{num}" # Tencent: sz000001
            tx_codes.append(tx_code)
            map_code[tx_code] = {'code': code, 'name': s['name']}
        
        # 2. 批量获取行情 (一次请求，极快)
        try:
            # 分批处理，防止URL过长，每批30个
            batch_size = 30
            for i in range(0, len(tx_codes), batch_size):
                batch = tx_codes[i:i+batch_size]
                url = f"http://qt.gtimg.cn/q={','.join(batch)}"
                resp = requests.get(url, timeout=2)
                
                if resp.status_code != 200: continue
                
                lines = resp.text.split(';')
                now_ts = datetime.now().timestamp()
                
                for line in lines:
                    if '="' not in line: continue
                    parts = line.split('="')
                    tx_c = parts[0].split('_')[-1] # sz000001
                    data = parts[1].split('~')
                    
                    if len(data) < 30: continue
                    
                    curr_price = float(data[3])
                    if curr_price == 0: continue
                    
                    ts_c = map_code.get(tx_c, {}).get('code')
                    name = map_code.get(tx_c, {}).get('name')
                    
                    if not ts_c: continue
                    
                    # 3. 异动判断逻辑
                    if ts_c in self.cache:
                        last_price = self.cache[ts_c]['price']
                        last_time = self.cache[ts_c]['time']
                        
                        # 只比较最近 30 秒内的变化，太久没刷新的不算急拉
                        if now_ts - last_time < 30: 
                            pct = (curr_price - last_price) / last_price * 100
                            
                            # 阈值：短时波动 > 1.0%
                            if pct > 1.0:
                                anomalies.append(f"🚀 {name} 急拉 +{pct:.2f}%")
                            elif pct < -1.0:
                                anomalies.append(f"📉 {name} 急跌 {pct:.2f}%")
                    
                    # 更新缓存
                    self.cache[ts_c] = {'price': curr_price, 'time': now_ts}
                    
        except:
            pass
            
        return anomalies

    # ====== V10新增：雷达反馈到策略权重（问题#21）======
    def get_strategy_adjustment(self, anomalies: list = None) -> dict:
        """
        根据雷达扫描结果输出策略权重调整建议
        
        问题#21：radar/limit_up_analyzer仅扫描，没有反馈到策略权重
        修复：输出权重调整系数
        
        Returns:
            {
                'action': 'boost' | 'reduce' | 'normal',
                'reason': str,
                'weight_multiplier': {factor: multiplier}
            }
        """
        if not anomalies:
            anomalies = []
        
        rush_count = sum(1 for a in anomalies if '急拉' in a)
        drop_count = sum(1 for a in anomalies if '急跌' in a)
        
        result = {
            'action': 'normal',
            'reason': '',
            'weight_multiplier': {}
        }
        
        # 多只急拉：市场活跃，提高资金/量能权重
        if rush_count >= 3:
            result['action'] = 'boost'
            result['reason'] = f"雷达检测到{rush_count}只急拉，市场活跃"
            result['weight_multiplier'] = {
                'money': 1.2,      # 资金权重提高
                'volume': 1.2,    # 量能权重提高
                'trend': 0.9      # 趋势权重略降
            }
        # 多只急跌：市场恐慌，提高风控权重
        elif drop_count >= 3:
            result['action'] = 'reduce'
            result['reason'] = f"雷达检测到{drop_count}只急跌，风险上升"
            result['weight_multiplier'] = {
                'money': 1.3,     # 资金权重大幅提高
                'chip': 1.2,      # 筹码权重提高
                'trend': 0.7      # 趋势权重降低
            }
        # 急拉急跌混合：市场震荡
        elif rush_count >= 1 and drop_count >= 1:
            result['action'] = 'normal'
            result['reason'] = "市场震荡，维持均衡权重"
            result['weight_multiplier'] = {
                'volume': 1.1
            }
        
        return result
    
    def get_market_heat(self) -> dict:
        """
        根据缓存数据判断市场热度
        
        Returns:
            {'level': 'hot'|'cold'|'normal', 'score': 0-100}
        """
        if not self.cache:
            return {'level': 'normal', 'score': 50}
        
        # 计算有价格更新的股票占比
        now_ts = datetime.now().timestamp()
        active_count = sum(1 for v in self.cache.values() 
                         if now_ts - v['time'] < 60)  # 1分钟内有更新
        
        total = len(self.cache)
        if total == 0:
            return {'level': 'normal', 'score': 50}
        
        active_ratio = active_count / total
        
        if active_ratio > 0.8:
            return {'level': 'hot', 'score': 80}
        elif active_ratio < 0.3:
            return {'level': 'cold', 'score': 30}
        else:
            return {'level': 'normal', 'score': int(active_ratio * 100)}
