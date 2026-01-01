
import tushare as ts
import pandas as pd
from datetime import datetime

class SectorManager:
    def __init__(self, token):
        ts.set_token(token)
        self.pro = ts.pro_api()
        # 简单的行业缓存
        self.industry_map = {}

    def _load_industries(self):
        # 预加载所有股票行业信息 (只做一次)
        if not self.industry_map:
            try:
                # 获取上市股票基本信息
                df = self.pro.stock_basic(exchange='', list_status='L', fields='ts_code,industry')
                if not df.empty:
                    self.industry_map = df.set_index('ts_code')['industry'].to_dict()
            except: pass

    def get_hot_sectors(self):
        try:
            self._load_industries()
            if not self.industry_map:
                return "数据初始化中..."

            # 1. 聪明的日期定位：先查一下大盘(000001.SH)最近一天的日期
            # 这样能保证那天一定有数据，哪怕今天是周末
            df_cal = self.pro.index_daily(ts_code='000001.SH', limit=1)
            if df_cal.empty:
                return "等待开盘..."
            
            target_date = df_cal.iloc[0]['trade_date']
            
            # 2. 获取那天涨幅榜前 60 名的股票
            # 我们不查全市场（太慢），只查涨幅 > 5% 的活跃股
            # 但为了省流，我们直接查 daily，取前 100 条（Tushare daily 默认不排序，我们尽量多取点自己排）
            # 更好的方法：直接取 daily，limit=500，然后内存排序
            
            df_daily = self.pro.daily(trade_date=target_date)
            
            if df_daily.empty:
                return "数据同步中..."
                
            # 3. 内存筛选：涨幅 > 5% 的
            df_strong = df_daily[df_daily['pct_chg'] > 5]
            
            if df_strong.empty:
                return "市场极度低迷"
                
            # 4. 统计行业
            sector_counts = {}
            for code in df_strong['ts_code']:
                ind = self.industry_map.get(code)
                if ind:
                    sector_counts[ind] = sector_counts.get(ind, 0) + 1
            
            # 5. 排序取前三
            sorted_sectors = sorted(sector_counts.items(), key=lambda x: x[1], reverse=True)
            top3 = sorted_sectors[:3]
            
            if not top3:
                return "热点散乱"
                
            # 格式化输出：软件服务(8)、元器件(6)
            res_str = "、".join([f"{k}" for k, v in top3])
            return f"🔥 {res_str}"
            
        except Exception as e:
            print(f"Sector Error: {e}")
            return "计算超时"
