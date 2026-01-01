# -*- coding: utf-8 -*-
"""
V10新增：盘中实时资金流监控模块
=============================
多数据源融合，提供实时资金流向

数据源：
1. 东方财富 - 实时资金流（主力/散户）
2. 新浪财经 - 分时成交
3. 腾讯财经 - 五档盘口

功能：
1. 实时资金流向监控
2. 主力买卖力度计算
3. 资金流入/流出预警
4. 盘中趋势变化检测
"""

import requests
import json
import re
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
from concurrent.futures import ThreadPoolExecutor, as_completed


class RealtimeFundFlow:
    """实时资金流监控器"""
    
    def __init__(self, cache_seconds: int = 30):
        """
        初始化
        
        Args:
            cache_seconds: 缓存时间（秒），避免频繁请求
        """
        self.cache = {}
        self.cache_seconds = cache_seconds
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://quote.eastmoney.com/'
        }
    
    def _is_cache_valid(self, key: str) -> bool:
        """检查缓存是否有效"""
        if key not in self.cache:
            return False
        cached_time = self.cache[key].get('_time', 0)
        return time.time() - cached_time < self.cache_seconds
    
    def _set_cache(self, key: str, data: Dict):
        """设置缓存"""
        data['_time'] = time.time()
        self.cache[key] = data
    
    # ==================== 东方财富数据源 ====================
    
    def fetch_eastmoney_realtime(self, ts_code: str) -> Dict:
        """
        从东方财富获取实时资金流
        
        Returns:
            {
                'main_inflow': 主力流入（万元）,
                'main_outflow': 主力流出（万元）,
                'main_net': 主力净流入（万元）,
                'retail_net': 散户净流入（万元）,
                'super_big_net': 超大单净流入,
                'big_net': 大单净流入,
                'mid_net': 中单净流入,
                'small_net': 小单净流入,
                'valid': True/False
            }
        """
        cache_key = f"em_{ts_code}"
        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]
        
        try:
            # 转换股票代码格式
            code = ts_code.split('.')[0]
            market = ts_code.split('.')[1]
            
            if market == 'SZ':
                secid = f"0.{code}"
            else:
                secid = f"1.{code}"
            
            # 东方财富实时资金流接口（修复：使用正确的列表接口）
            url = f"https://push2.eastmoney.com/api/qt/ulist.np/get"
            params = {
                'fltt': 2,
                'secids': secid,
                'fields': 'f62,f64,f65,f66,f69,f70,f71,f72,f75,f76,f77,f78,f184,f185,f186,f187',
            }
            
            resp = requests.get(url, params=params, headers=self.headers, timeout=5)
            data = resp.json()
            
            # 修复：正确解析返回数据结构 data.diff[0]
            if data.get('data') and data['data'].get('diff') and len(data['data']['diff']) > 0:
                d = data['data']['diff'][0]
                # f62=主力净流入, f64=主力流入, f65=主力流出, f66=超大单净, f72=大单净, f78=中单净
                main_net = d.get('f62', 0) / 10000  # 转万元
                result = {
                    'main_inflow': round(d.get('f64', 0) / 10000, 2),     # 主力流入（万元）
                    'main_outflow': round(d.get('f65', 0) / 10000, 2),    # 主力流出
                    'main_net': round(main_net, 2),                        # 主力净额
                    'super_big_net': round(d.get('f66', 0) / 10000, 2),   # 超大单净额
                    'big_net': round(d.get('f72', 0) / 10000, 2),         # 大单净额
                    'mid_net': round(d.get('f78', 0) / 10000, 2),         # 中单净额
                    'small_net': 0,
                    'retail_net': round(d.get('f78', 0) / 10000, 2),
                    'source': 'eastmoney',
                    'valid': True
                }
                self._set_cache(cache_key, result)
                return result
            
        except Exception as e:
            print(f"东方财富接口失败: {e}")
        
        return {'valid': False, 'source': 'eastmoney'}

    
    # ==================== 新浪财经数据源 ====================
    
    def fetch_sina_realtime(self, ts_code: str) -> Dict:
        """
        从新浪财经获取实时行情和资金
        
        Returns:
            {
                'price': 当前价,
                'open': 开盘价,
                'high': 最高,
                'low': 最低,
                'volume': 成交量,
                'amount': 成交额,
                'buy_volume': 内盘（卖方成交）,
                'sell_volume': 外盘（买方成交）,
                'bs_ratio': 买卖比,
                'valid': True/False
            }
        """
        cache_key = f"sina_{ts_code}"
        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]
        
        try:
            code = ts_code.split('.')[0]
            market = ts_code.split('.')[1].lower()
            sina_code = f"{market}{code}"
            
            url = f"https://hq.sinajs.cn/list={sina_code}"
            headers = {'Referer': 'https://finance.sina.com.cn'}
            
            resp = requests.get(url, headers=headers, timeout=3)
            resp.encoding = 'gbk'
            
            # 解析数据
            match = re.search(r'"(.+)"', resp.text)
            if match:
                parts = match.group(1).split(',')
                if len(parts) >= 32:
                    result = {
                        'name': parts[0],
                        'open': float(parts[1]),
                        'pre_close': float(parts[2]),
                        'price': float(parts[3]),
                        'high': float(parts[4]),
                        'low': float(parts[5]),
                        'volume': float(parts[8]),  # 成交量（股）
                        'amount': float(parts[9]),  # 成交额（元）
                        'buy_volume': float(parts[7]) if len(parts) > 7 else 0,   # 内盘
                        'sell_volume': float(parts[8]) - float(parts[7]) if len(parts) > 7 else 0,  # 外盘
                        'source': 'sina',
                        'valid': True
                    }
                    
                    # 计算买卖比
                    if result['buy_volume'] > 0:
                        result['bs_ratio'] = round(result['sell_volume'] / result['buy_volume'], 2)
                    else:
                        result['bs_ratio'] = 1.0
                    
                    self._set_cache(cache_key, result)
                    return result
        
        except Exception as e:
            print(f"新浪接口失败: {e}")
        
        return {'valid': False, 'source': 'sina'}
    
    # ==================== 腾讯财经数据源 ====================
    
    def fetch_tencent_realtime(self, ts_code: str) -> Dict:
        """
        从腾讯财经获取实时盘口数据
        
        Returns:
            五档盘口 + 买卖力量对比
        """
        cache_key = f"qq_{ts_code}"
        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]
        
        try:
            code = ts_code.split('.')[0]
            market = ts_code.split('.')[1].lower()
            tx_code = f"{market}{code}"
            
            url = f"http://qt.gtimg.cn/q={tx_code}"
            resp = requests.get(url, timeout=3)
            resp.encoding = 'gbk'
            
            if '="' in resp.text:
                data = resp.text.split('="')[1].split('~')
                if len(data) >= 40:
                    # 买盘力量 = 买一到买五量之和
                    buy_power = sum([float(data[i]) for i in [10, 12, 14, 16, 18] if i < len(data) and data[i]])
                    # 卖盘力量 = 卖一到卖五量之和
                    sell_power = sum([float(data[i]) for i in [20, 22, 24, 26, 28] if i < len(data) and data[i]])
                    
                    result = {
                        'price': float(data[3]),
                        'pct_change': float(data[32]),
                        'buy_power': buy_power,
                        'sell_power': sell_power,
                        'power_ratio': round(buy_power / sell_power, 2) if sell_power > 0 else 999,
                        'source': 'tencent',
                        'valid': True
                    }
                    self._set_cache(cache_key, result)
                    return result
        
        except Exception as e:
            print(f"腾讯接口失败: {e}")
        
        return {'valid': False, 'source': 'tencent'}
    
    # ==================== 融合分析 ====================
    
    def get_realtime_fund_analysis(self, ts_code: str) -> Dict:
        """
        获取实时资金流综合分析（多数据源融合）
        
        Returns:
            {
                'main_net': 主力净流入（万元）,
                'fund_trend': 资金趋势（'流入'/'流出'/'平衡'）,
                'power_ratio': 买卖力量比,
                'risk_signal': 风险信号,
                'suggestion': 操作建议,
                'confidence': 数据可信度(0-100),
                'sources': 数据来源列表,
                'valid': True/False
            }
        """
        # 并发获取多个数据源
        results = {}
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(self.fetch_eastmoney_realtime, ts_code): 'eastmoney',
                executor.submit(self.fetch_sina_realtime, ts_code): 'sina',
                executor.submit(self.fetch_tencent_realtime, ts_code): 'tencent'
            }
            for future in as_completed(futures, timeout=10):
                source = futures[future]
                try:
                    results[source] = future.result()
                except:
                    results[source] = {'valid': False}
        
        # 融合分析
        em = results.get('eastmoney', {})
        sina = results.get('sina', {})
        qq = results.get('tencent', {})
        
        sources = []
        confidence = 0
        
        # 主力资金（优先东方财富）
        main_net = 0
        if em.get('valid'):
            main_net = em.get('main_net', 0)
            sources.append('eastmoney')
            confidence += 40
        
        # 买卖力量（腾讯）
        power_ratio = 1.0
        if qq.get('valid'):
            power_ratio = qq.get('power_ratio', 1.0)
            sources.append('tencent')
            confidence += 30
        
        # 内外盘（新浪）
        bs_ratio = 1.0
        if sina.get('valid'):
            bs_ratio = sina.get('bs_ratio', 1.0)
            sources.append('sina')
            confidence += 30
        
        if not sources:
            return {'valid': False, 'message': '所有数据源均不可用'}
        
        # 判断资金趋势
        if main_net > 500:  # 500万以上净流入
            fund_trend = '大幅流入'
        elif main_net > 100:
            fund_trend = '流入'
        elif main_net < -500:
            fund_trend = '大幅流出'
        elif main_net < -100:
            fund_trend = '流出'
        else:
            fund_trend = '平衡'
        
        # 风险信号检测
        risk_signal = None
        suggestion = '观察'
        
        # 情况1：主力大幅流出 + 卖压重
        if main_net < -500 and power_ratio < 0.8:
            risk_signal = '⚠️ 主力出货'
            suggestion = '谨慎，考虑减仓'
        
        # 情况2：价格下跌但显示主力流入（数据滞后或诱多）
        if qq.get('valid') and qq.get('pct_change', 0) < -3:
            if main_net > 0:
                risk_signal = '⚠️ 数据背离'
                suggestion = '数据可能滞后，以实际走势为准'
            else:
                risk_signal = '🔴 持续流出'
                suggestion = '下跌中资金流出，不宜抄底'
        
        # 情况3：下跌但有资金接盘
        if qq.get('valid') and qq.get('pct_change', 0) < -2:
            if power_ratio > 1.5:
                risk_signal = '💎 可能洗盘'
                suggestion = '有资金接盘，可能是洗盘'
        
        # 情况4：主力大举流入
        if main_net > 1000 and power_ratio > 1.2:
            risk_signal = '🔥 主力抢筹'
            suggestion = '资金积极进场'
        
        return {
            'main_net': main_net,
            'main_net_text': self._format_amount(main_net),
            'fund_trend': fund_trend,
            'power_ratio': power_ratio,
            'bs_ratio': bs_ratio,
            'risk_signal': risk_signal or '✅ 资金正常',
            'suggestion': suggestion,
            'confidence': confidence,
            'sources': sources,
            'raw': {
                'eastmoney': em if em.get('valid') else None,
                'sina': sina if sina.get('valid') else None,
                'tencent': qq if qq.get('valid') else None
            },
            'valid': True,
            'update_time': datetime.now().strftime('%H:%M:%S')
        }
    
    def _format_amount(self, amount: float) -> str:
        """格式化金额显示"""
        if abs(amount) >= 10000:
            return f"{amount/10000:+.2f}亿"
        else:
            return f"{amount:+.0f}万"
    
    # ==================== 盘中变化检测 ====================
    
    def detect_intraday_change(self, ts_code: str, baseline_net: float = None) -> Dict:
        """
        检测盘中资金变化
        
        Args:
            ts_code: 股票代码
            baseline_net: 基准净流入（如昨日数据），用于对比
            
        Returns:
            变化情况和预警信号
        """
        current = self.get_realtime_fund_analysis(ts_code)
        
        if not current.get('valid'):
            return {'valid': False}
        
        current_net = current.get('main_net', 0)
        
        # 如果有基准值，计算变化
        if baseline_net is not None:
            change = current_net - baseline_net
            if change < -500:
                alert = '⚠️ 资金大幅转出！较昨日减少' + self._format_amount(abs(change))
            elif change < -100:
                alert = '📉 资金流出加剧'
            elif change > 500:
                alert = '🔥 资金大幅流入！较昨日增加' + self._format_amount(change)
            elif change > 100:
                alert = '📈 资金持续流入'
            else:
                alert = None
            
            current['baseline_net'] = baseline_net
            current['net_change'] = change
            current['change_alert'] = alert
        
        return current


# 工厂函数
def create_realtime_fund_flow(cache_seconds: int = 30) -> RealtimeFundFlow:
    """创建实时资金流监控器"""
    return RealtimeFundFlow(cache_seconds)
