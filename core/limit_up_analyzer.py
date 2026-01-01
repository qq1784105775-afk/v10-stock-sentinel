"""
涨停板次日表现统计分析模块
基于历史数据的统计规律
"""

class LimitUpAnalyzer:
    """涨停板分析器"""
    
    def __init__(self):
        # 基于统计数据的涨停后表现
        self.stats = {
            'next_day_up_prob': 0.66,  # 次日上涨概率66%
            'next_day_limit_prob': 0.12,  # 继续涨停概率12%
            'avg_next_day_return': 2.07,  # 次日平均涨幅2.07%
            '5day_return': 2.56,  # 5日平均涨幅
            '10day_return': 2.41,  # 10日平均涨幅
            'pullback_risk': 0.5,  # 回调风险50%
        }
    
    def analyze_limit_up_strength(self, ts_code, current_data, history_data=None):
        """
        分析涨停板强度
        返回：强度评分和操作建议
        """
        result = {
            'strength': 0,
            'type': '',
            'next_day_forecast': '',
            'suggestion': '',
            'risk_level': '',
        }
        
        if not current_data:
            return result
        
        # 获取关键指标
        pct_change = current_data.get('pct_change', 0)
        volume_ratio = current_data.get('volume_ratio', 1)
        bid_ratio = current_data.get('bid_ratio', 1)  # 封单比例
        open_times = current_data.get('open_times', 0)  # 开板次数
        time_to_limit = current_data.get('time_to_limit', 300)  # 封板时间（分钟）
        net_inflow = current_data.get('net_inflow', 0)
        
        # 1. 判断涨停类型
        if pct_change >= 9.8:
            if open_times == 0 and time_to_limit < 30:
                result['type'] = '一字涨停'
                result['strength'] = 95
                result['next_day_forecast'] = '大概率高开，继续涨停概率30%'
                result['suggestion'] = '持有待连板，不要卖飞'
                
            elif open_times == 0 and time_to_limit < 60:
                result['type'] = '秒板涨停'
                result['strength'] = 90
                result['next_day_forecast'] = '高开3-5%，继续涨停概率20%'
                result['suggestion'] = '持有为主，可部分止盈'
                
            elif open_times <= 2:
                result['type'] = '换手涨停'
                result['strength'] = 75
                result['next_day_forecast'] = '平开或高开2%，震荡概率大'
                result['suggestion'] = '逢高减仓，锁定部分利润'
                
            elif open_times > 2:
                result['type'] = '烂板涨停'
                result['strength'] = 60
                result['next_day_forecast'] = '可能低开，回调风险较大'
                result['suggestion'] = '开盘即减仓，避免回吐'
                
            # 2. 根据封单强度调整
            if bid_ratio > 5:  # 封单强
                result['strength'] += 10
                result['risk_level'] = '低'
            elif bid_ratio > 2:
                result['strength'] += 5
                result['risk_level'] = '中'
            else:
                result['risk_level'] = '高'
                
            # 3. 根据资金流调整（修复：阈值单位改为万元）
            if net_inflow > 5000:  # 5000万元以上
                result['strength'] += 10
                result['next_day_forecast'] += '，主力锁仓意愿强'
            elif net_inflow < -3000:  # -3000万元
                result['strength'] -= 15
                result['next_day_forecast'] += '，注意主力出货风险'
                
        return result
    
    def get_limit_up_strategy(self, limit_type, market_sentiment='neutral'):
        """
        根据涨停类型和市场情绪获取操作策略
        """
        strategies = {
            '一字涨停': {
                'bull': {'hold': 0.9, 'sell': 0.1, 'add': 0},
                'neutral': {'hold': 0.7, 'sell': 0.3, 'add': 0},
                'bear': {'hold': 0.3, 'sell': 0.7, 'add': 0},
            },
            '秒板涨停': {
                'bull': {'hold': 0.8, 'sell': 0.2, 'add': 0},
                'neutral': {'hold': 0.6, 'sell': 0.4, 'add': 0},
                'bear': {'hold': 0.2, 'sell': 0.8, 'add': 0},
            },
            '换手涨停': {
                'bull': {'hold': 0.5, 'sell': 0.5, 'add': 0},
                'neutral': {'hold': 0.3, 'sell': 0.7, 'add': 0},
                'bear': {'hold': 0.1, 'sell': 0.9, 'add': 0},
            },
            '烂板涨停': {
                'bull': {'hold': 0.2, 'sell': 0.8, 'add': 0},
                'neutral': {'hold': 0.1, 'sell': 0.9, 'add': 0},
                'bear': {'hold': 0, 'sell': 1.0, 'add': 0},
            },
        }
        
        return strategies.get(limit_type, {}).get(market_sentiment, {
            'hold': 0.5, 'sell': 0.5, 'add': 0
        })
    
    def calculate_next_day_target(self, current_price, limit_type):
        """
        计算次日目标价
        基于统计数据
        """
        targets = {
            '一字涨停': {
                'high': current_price * 1.10,  # 继续涨停
                'likely': current_price * 1.05,  # 高开5%
                'low': current_price * 1.02,  # 高开2%
            },
            '秒板涨停': {
                'high': current_price * 1.08,
                'likely': current_price * 1.03,
                'low': current_price * 1.00,
            },
            '换手涨停': {
                'high': current_price * 1.05,
                'likely': current_price * 1.01,
                'low': current_price * 0.97,
            },
            '烂板涨停': {
                'high': current_price * 1.02,
                'likely': current_price * 0.98,
                'low': current_price * 0.95,
            }
        }
        
        return targets.get(limit_type, {
            'high': current_price * 1.02,
            'likely': current_price * 1.00,
            'low': current_price * 0.97,
        })
