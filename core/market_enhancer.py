# -*- coding: utf-8 -*-
"""
V10新增：市场数据增强模块
========================
包含：龙虎榜、融资融券、板块联动分析

功能：
1. 龙虎榜数据获取与分析
2. 融资融券数据获取与分析
3. 板块联动分析
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import tushare as ts

class MarketDataEnhancer:
    """市场数据增强器"""
    
    def __init__(self, pro, db):
        """
        初始化
        
        Args:
            pro: Tushare pro接口
            db: DatabaseManager实例
        """
        self.pro = pro
        self.db = db
        self.famous_seats = self._init_famous_seats()
    
    def _init_famous_seats(self) -> Dict[str, str]:
        """初始化知名游资席位库"""
        return {
            '中信证券上海溧阳路': '赵老哥',
            '华泰证券深圳益田路': '章盟主', 
            '光大证券宁波解放南路': '涨停板敢死队',
            '银河证券绍兴': '孙哥',
            '国泰君安总部': '作手新一',
            '华鑫证券上海宛平南路': '小鳄鱼',
            '财通证券绍兴人民中路': '欢乐海岸',
            '西藏东方财富拉萨团结路': '拉萨天团',
            '东方财富拉萨东环路第一': '拉萨天团',
            '东方财富拉萨东环路第二': '拉萨天团',
        }
    
    # ==================== 龙虎榜模块 ====================
    
    def fetch_dragon_tiger(self, trade_date: str = None) -> List[Dict]:
        """
        获取龙虎榜数据
        
        Args:
            trade_date: 交易日期，默认最近一个交易日
            
        Returns:
            龙虎榜数据列表
        """
        try:
            if not trade_date:
                trade_date = datetime.now().strftime('%Y%m%d')
            
            # 获取龙虎榜数据
            df = self.pro.top_list(trade_date=trade_date, 
                                   fields='ts_code,trade_date,name,close,pct_change,turnover_rate,amount,l_buy,l_sell,net_amount,reason')
            
            if df is None or df.empty:
                return []
            
            result = []
            for _, row in df.iterrows():
                ts_code = row['ts_code']
                
                # 获取买卖明细
                detail = self._get_dragon_detail(ts_code, trade_date)
                
                item = {
                    'ts_code': ts_code,
                    'name': row['name'],
                    'trade_date': row['trade_date'],
                    'close': row['close'],
                    'pct_change': row['pct_change'],
                    'reason': row['reason'],
                    'buy_amount': row['l_buy'],
                    'sell_amount': row['l_sell'],
                    'net_amount': row['net_amount'],
                    'top_buyers': detail.get('buyers', []),
                    'top_sellers': detail.get('sellers', []),
                    'famous_buyers': detail.get('famous_buyers', []),
                }
                
                # 保存到数据库
                try:
                    self.db.save_dragon_tiger(
                        ts_code=ts_code,
                        trade_date=trade_date,
                        reason=row['reason'],
                        buy_amount=row['l_buy'],
                        sell_amount=row['l_sell'],
                        top_buyers=json.dumps(detail.get('buyers', []), ensure_ascii=False),
                        top_sellers=json.dumps(detail.get('sellers', []), ensure_ascii=False)
                    )
                except:
                    pass
                
                result.append(item)
            
            return result
            
        except Exception as e:
            print(f"获取龙虎榜失败: {e}")
            return []
    
    def _get_dragon_detail(self, ts_code: str, trade_date: str) -> Dict:
        """获取龙虎榜买卖明细"""
        try:
            df = self.pro.top_inst(ts_code=ts_code, trade_date=trade_date,
                                   fields='exalter,buy,sell,net_buy')
            
            if df is None or df.empty:
                return {}
            
            buyers = []
            sellers = []
            famous_buyers = []
            
            for _, row in df.iterrows():
                seat_name = row['exalter']
                buy = row['buy'] or 0
                sell = row['sell'] or 0
                net = row['net_buy'] or 0
                
                item = {'seat': seat_name, 'buy': buy, 'sell': sell, 'net': net}
                
                if buy > sell:
                    buyers.append(item)
                    # 检查是否是知名游资
                    for key, nickname in self.famous_seats.items():
                        if key in seat_name:
                            famous_buyers.append({'seat': seat_name, 'nickname': nickname, 'buy': buy})
                else:
                    sellers.append(item)
            
            return {
                'buyers': sorted(buyers, key=lambda x: x['buy'], reverse=True)[:5],
                'sellers': sorted(sellers, key=lambda x: x['sell'], reverse=True)[:5],
                'famous_buyers': famous_buyers
            }
            
        except Exception as e:
            return {}
    
    def analyze_dragon_signal(self, ts_code: str) -> Dict:
        """
        分析龙虎榜信号
        
        Returns:
            {signal: 信号, famous: 是否有知名游资, suggestion: 建议}
        """
        history = self.db.get_stock_dragon_tiger(ts_code, days=30)
        
        if not history:
            return {'signal': '无', 'has_famous': False, 'suggestion': '无龙虎榜记录'}
        
        latest = history[0]
        net = latest.get('net_amount', 0)
        
        # 检查知名游资
        top_buyers = json.loads(latest.get('top_buyers', '[]')) if latest.get('top_buyers') else []
        has_famous = False
        famous_names = []
        for buyer in top_buyers:
            seat = buyer.get('seat', '')
            for key, nickname in self.famous_seats.items():
                if key in seat:
                    has_famous = True
                    famous_names.append(nickname)
        
        # 生成信号
        if net > 50000000:  # 5000万净买入
            signal = '🔥 游资大举买入'
            suggestion = '短线可跟进，注意及时止盈'
        elif net > 20000000:  # 2000万
            signal = '📈 资金净买入'
            suggestion = '关注后续走势'
        elif net < -50000000:
            signal = '⚠️ 游资大举出货'
            suggestion = '规避风险，不宜追高'
        elif net < -20000000:
            signal = '📉 资金净卖出'
            suggestion = '谨慎观望'
        else:
            signal = '⚖️ 多空平衡'
            suggestion = '等待方向明确'
        
        if has_famous:
            signal += f" (知名游资: {','.join(set(famous_names))})"
        
        return {
            'signal': signal,
            'has_famous': has_famous,
            'famous_names': list(set(famous_names)),
            'net_amount': net,
            'suggestion': suggestion,
            'reason': latest.get('reason', '')
        }
    
    # ==================== 融资融券模块 ====================
    
    def fetch_margin_data(self, ts_code: str, days: int = 30) -> List[Dict]:
        """
        获取融资融券数据
        
        Args:
            ts_code: 股票代码
            days: 获取天数
            
        Returns:
            融资融券数据列表
        """
        try:
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
            
            df = self.pro.margin_detail(ts_code=ts_code, 
                                        start_date=start_date,
                                        end_date=end_date,
                                        fields='trade_date,rzye,rzmre,rzche,rqye,rqmcl,rqyl,rzrqye')
            
            if df is None or df.empty:
                return []
            
            result = []
            for _, row in df.iterrows():
                item = {
                    'trade_date': row['trade_date'],
                    'rzye': row.get('rzye', 0),          # 融资余额
                    'rzmre': row.get('rzmre', 0),        # 融资买入额
                    'rzche': row.get('rzche', 0),        # 融资偿还额
                    'rqye': row.get('rqye', 0),          # 融券余额
                    'rqmcl': row.get('rqmcl', 0),        # 融券卖出量
                    'rzrqye': row.get('rzrqye', 0),      # 融资融券余额
                }
                
                # 保存到数据库
                try:
                    self.db.save_margin_data(
                        ts_code=ts_code,
                        trade_date=row['trade_date'],
                        rzye=item['rzye'],
                        rzmre=item['rzmre'],
                        rzche=item['rzche'],
                        rqye=item['rqye'],
                        rqmcl=item['rqmcl'],
                        rzrqye=item['rzrqye']
                    )
                except:
                    pass
                
                result.append(item)
            
            return result
            
        except Exception as e:
            print(f"获取融资融券数据失败: {e}")
            return []
    
    def analyze_margin_signal(self, ts_code: str) -> Dict:
        """
        分析融资融券信号
        
        Returns:
            {trend: 趋势, signal: 信号, suggestion: 建议}
        """
        margin_data = self.db.get_margin_data(ts_code, days=10)
        
        if len(margin_data) < 2:
            return {'trend': '未知', 'signal': '数据不足', 'suggestion': '无法判断'}
        
        # 计算融资余额变化趋势
        latest_rzye = margin_data[0].get('rzye', 0) or 0
        prev_rzye = margin_data[-1].get('rzye', 0) or 0
        
        if prev_rzye > 0:
            rzye_change = (latest_rzye - prev_rzye) / prev_rzye * 100
        else:
            rzye_change = 0
        
        # 计算融券余额变化
        latest_rqye = margin_data[0].get('rqye', 0) or 0
        prev_rqye = margin_data[-1].get('rqye', 0) or 0
        
        if prev_rqye > 0:
            rqye_change = (latest_rqye - prev_rqye) / prev_rqye * 100
        else:
            rqye_change = 0
        
        # 判断趋势
        if rzye_change > 10:
            trend = '融资增加'
            signal = '📈 机构看多'
            suggestion = '融资余额增加，机构看好后市'
        elif rzye_change < -10:
            trend = '融资减少'
            signal = '📉 机构减仓'
            suggestion = '融资余额减少，机构谨慎'
        else:
            trend = '融资平稳'
            signal = '⚖️ 多空平衡'
            suggestion = '融资余额稳定'
        
        # 融券做空信号
        if rqye_change > 20:
            signal += ' + ⚠️做空增加'
            suggestion += '，但融券做空增加需警惕'
        
        return {
            'trend': trend,
            'signal': signal,
            'suggestion': suggestion,
            'rzye': latest_rzye,
            'rzye_change': round(rzye_change, 2),
            'rqye': latest_rqye,
            'rqye_change': round(rqye_change, 2)
        }
    
    # ==================== 板块联动模块 ====================
    
    def fetch_sector_linkage(self, trade_date: str = None) -> List[Dict]:
        """
        获取板块联动数据
        
        Args:
            trade_date: 交易日期
            
        Returns:
            板块联动数据
        """
        try:
            if not trade_date:
                trade_date = datetime.now().strftime('%Y%m%d')
            
            # 获取行业指数
            df = self.pro.index_daily(trade_date=trade_date)
            
            if df is None or df.empty:
                # 尝试通过申万行业获取
                df = self.pro.sw_daily(trade_date=trade_date)
            
            if df is None or df.empty:
                return []
            
            # 按涨幅排序取前10
            df = df.nlargest(10, 'pct_chg')
            
            result = []
            for _, row in df.iterrows():
                # 简化处理：用指数名作为板块名
                sector_name = row.get('name', row.get('index_name', ''))
                
                result.append({
                    'sector_name': sector_name,
                    'sector_pct': row['pct_chg'],
                    'trade_date': trade_date
                })
            
            return result
            
        except Exception as e:
            print(f"获取板块联动失败: {e}")
            return []
    
    def get_hot_sectors(self, days: int = 5) -> List[Dict]:
        """
        获取近期热门板块
        
        Returns:
            热门板块列表
        """
        try:
            recent = self.db.get_sector_linkage(datetime.now().strftime('%Y-%m-%d'))
            
            if not recent:
                # 实时获取
                recent = self.fetch_sector_linkage()
            
            return recent[:5]
            
        except:
            return []


# 工厂函数
def create_market_enhancer(config: Dict, db) -> Optional[MarketDataEnhancer]:
    """创建市场数据增强器"""
    try:
        ts.set_token(config.get('tushare_token', ''))
        pro = ts.pro_api()
        return MarketDataEnhancer(pro, db)
    except Exception as e:
        print(f"创建MarketDataEnhancer失败: {e}")
        return None
