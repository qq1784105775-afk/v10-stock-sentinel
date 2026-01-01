import tushare as ts
from datetime import datetime, timedelta

class FundFlowAnalyzer:
    def __init__(self, token):
        ts.set_token(token)
        self.pro = ts.pro_api()
    
    def fetch_money_flow(self, ts_code, start_date, end_date):
        try:
            df = self.pro.moneyflow(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )
            return df
        except Exception as e:
            print(f"获取资金流失败 {ts_code}: {str(e)}")
            return None
    
    def analyze_main_force_behavior(self, money_flow_data):
        if not money_flow_data or len(money_flow_data) == 0:
            return {
                'status': 'unknown',
                'description': '暂无资金数据'
            }
        
        sorted_data = sorted(money_flow_data, key=lambda x: x['trade_date'], reverse=True)
        
        recent_3 = sorted_data[:3]
        recent_5 = sorted_data[:5]
        recent_10 = sorted_data[:10]
        
        inflow_3 = sum(1 for d in recent_3 if d['main_net_inflow'] > 0)
        inflow_5 = sum(1 for d in recent_5 if d['main_net_inflow'] > 0)
        
        total_inflow_10 = sum(d['main_net_inflow'] for d in recent_10)
        avg_inflow_10 = total_inflow_10 / 10
        
        if inflow_3 == 3:
            status = 'strong_inflow'
            description = '主力连续3天强势流入，积极建仓'
        elif inflow_3 >= 2:
            status = 'moderate_inflow'
            description = '主力近期持续流入，关注度提升'
        elif inflow_5 >= 4:
            status = 'gentle_inflow'
            description = '主力温和流入，缓慢吸筹'
        # 资金判断（单位：万元，Tushare moneyflow接口返回万元）
        elif avg_inflow_10 > 1000:  # 1000万以上
            status = 'accumulating'
            description = '主力整体在吸筹，耐心布局'
        elif avg_inflow_10 < -1000:  # 流出1000万以上
            status = 'strong_outflow'
            description = '主力持续出货，谨慎观望'
        else:
            status = 'neutral'
            description = '主力资金观望，未有明确动作'
        
        return {
            'status': status,
            'description': description,
            'inflow_days_3': inflow_3,
            'inflow_days_5': inflow_5,
            'avg_inflow_10': avg_inflow_10,
            'total_inflow_10': total_inflow_10
        }
    
    def get_realtime_flow_estimate(self, current_amount, historical_avg):
        if historical_avg == 0:
            return 0
        
        ratio = current_amount / historical_avg
        
        if ratio >= 2.0:
            estimated_inflow = current_amount * 0.3
        elif ratio >= 1.5:
            estimated_inflow = current_amount * 0.2
        elif ratio >= 1.0:
            estimated_inflow = current_amount * 0.1
        else:
            estimated_inflow = 0
        
        return estimated_inflow
