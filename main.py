# -*- coding: utf-8 -*-
"""
V10 Ultra Pro 终极版
====================
升级内容：
1. 修复北向资金（真实数据）
2. 新增市场情绪指标（涨跌停家数、炸板率）
3. 新增涨停板统计（连板数、封单额）
4. 东方财富数据源备用
5. 推荐准确率统计
6. 性能优化（批量+缓存）

作者：Claude
日期：2024-12-22
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import uvicorn
import json
import tushare as ts
from core.cyq_real import get_cyq_analysis as cyq_analyze
import requests
import pandas as pd
from datetime import datetime, timedelta, time as dt_time
import os
import concurrent.futures 
import threading
import time
import sqlite3

from database.db_manager import DatabaseManager
from core.scoring_engine import ScoringEngine
from core.market_monitor import MarketMonitor
from core.fund_flow import FundFlowAnalyzer
from core.backtest import BacktestEngine
from core.sector import SectorManager
from core.radar import RadarManager
from core.review import ReviewManager
from core.risk_control import RiskController
from core.strategy_pro import StrategyPro

# ====== V9升级模块 ======
from core.cache import cache as v9_cache
V9_CACHE_ENABLED = True

# V10升级：使用高级筹码算法（换手衰减模型）
try:
    from core.chip_engine_v9_advanced import get_cyq_analysis_v9
    print("✅ 使用V10高级筹码算法（TurnoverDecayModel）")
    V9_CHIP_ADVANCED = True
except:
    from core.chip_engine_v9 import get_cyq_analysis_v9
    print("⚠️ 回退到基础筹码算法")
    V9_CHIP_ADVANCED = False

V9_CHIP_ENABLED = True

from core.factor_engine_v9 import calculate_v9_score, set_market_regime
V9_FACTOR_ENABLED = True

# V10新增：增强风控模块
try:
    from core.risk_control_enhanced import EnhancedRiskControl, get_global_risk_state
    enhanced_risk = EnhancedRiskControl({})
    global_risk_state = get_global_risk_state()
    ENHANCED_RISK_ENABLED = True
except Exception as e:
    print(f"风控模块加载失败: {e}")

    enhanced_risk = None
    ENHANCED_RISK_ENABLED = False

# V10新增：回测引擎 - 延迟初始化（在config和db定义后进行）
BACKTEST_ENABLED = False
backtest_engine = None
try:
    from core.backtest import BacktestEngine
    BACKTEST_ENABLED = True  # 模块可用，稍后初始化
except Exception as e:
    print(f"回测模块不可用: {e}")

# V10新增：涨停板分析器
try:
    from core.limit_up_analyzer import LimitUpAnalyzer
    from core.wencai_fetcher import WencaiDataFetcher, LimitUpStatistics
    limit_analyzer = LimitUpAnalyzer()
    wencai_fetcher = WencaiDataFetcher()
    limit_stats = LimitUpStatistics()
    LIMIT_ANALYSIS_ENABLED = True
except Exception as e:
    print(f"涨停板分析模块加载失败: {e}")
    limit_analyzer = None
    LIMIT_ANALYSIS_ENABLED = False

try:
    from core.strategy_l2_pro import l2_monitor
except Exception:
    l2_monitor = None

# ====== V10 Ultra Pro：新增核心模块 ======
try:
    from core.decision_core import DecisionCore, Priority, Signal, quick_verdict
    from core.trading_state import get_state_manager, get_current_trading_state
    from core.win_rate_model import WinRateModel, quick_win_rate
    from core.data_validator import validate_stock_data, get_validator
    from core.decision_logger import log_decision, get_decision_logger
    from core.failure_tracker import get_failure_tracker
    # V10新增：系统健康/出场策略/配置管理/筹码决策
    from core.system_health import quick_health_check, get_health_checker
    from core.exit_strategy import should_exit_position, get_exit_strategy
    from core.config_manager import get_config_manager, get_config
    from core.chip_engine_v9 import get_chip_decision_signal, chip_affects_verdict
    ULTRA_PRO_ENABLED = True
    print("✅ V10 Ultra Pro 全模块加载成功")
except Exception as e:
    print(f"⚠️ V10 Ultra Pro 模块加载失败: {e}")
    ULTRA_PRO_ENABLED = False
    DecisionCore = None
    quick_verdict = None


app = FastAPI(title="V10 Ultra Pro Terminal")


with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

ts.set_token(config['tushare_token'])
pro = ts.pro_api()

db = DatabaseManager(config['database_path'])
scoring_engine = ScoringEngine(config)
market_monitor = MarketMonitor(config)
fund_analyzer = FundFlowAnalyzer(config['tushare_token'])

# 延迟初始化回测引擎（在config和db可用后）
if BACKTEST_ENABLED:
    try:
        backtest_engine = BacktestEngine(config, db)
    except Exception as e:
        print(f"回测引擎初始化失败: {e}")
        backtest_engine = None
        BACKTEST_ENABLED = False

sector_mgr = SectorManager(config['tushare_token'])
radar_mgr = RadarManager()
review_mgr = ReviewManager()
risk_mgr = RiskController()
strat_mgr = StrategyPro()

# ====== V10升级：市场数据增强和AI智能推送 ======
try:
    from core.market_enhancer import MarketDataEnhancer
    market_enhancer = MarketDataEnhancer(pro, db)
    MARKET_ENHANCER_ENABLED = True
    print("✅ 市场数据增强模块加载成功")
except Exception as e:
    print(f"⚠️ 市场数据增强模块加载失败: {e}")
    market_enhancer = None
    MARKET_ENHANCER_ENABLED = False

try:
    from core.ai_smart_push import AISmartPush
    ai_push = AISmartPush(db)
    AI_PUSH_ENABLED = True
    print("✅ AI智能推送模块加载成功")
except Exception as e:
    print(f"⚠️ AI智能推送模块加载失败: {e}")
    ai_push = None
    AI_PUSH_ENABLED = False

# ====== V10升级：盘中实时资金流监控 ======
try:
    from core.realtime_fund import RealtimeFundFlow
    realtime_fund = RealtimeFundFlow(cache_seconds=30)
    REALTIME_FUND_ENABLED = True
    print("✅ 盘中实时资金流模块加载成功")
except Exception as e:
    print(f"⚠️ 盘中实时资金流模块加载失败: {e}")
    realtime_fund = None
    REALTIME_FUND_ENABLED = False

templates = Jinja2Templates(directory="templates")
if not os.path.exists('static'): os.makedirs('static')
try: app.mount("/static", StaticFiles(directory="static"), name="static")
except: pass

# ====== V10新增：内存缓存系统 ======
class SimpleCache:
    def __init__(self, default_ttl=60):
        self._cache = {}
        self._timestamps = {}
        self._lock = threading.RLock()
        self.default_ttl = default_ttl
    
    def get(self, key):
        with self._lock:
            if key in self._cache:
                if time.time() - self._timestamps.get(key, 0) < self.default_ttl:
                    return self._cache[key]
                else:
                    del self._cache[key]
            return None
    
    def set(self, key, value, ttl=None):
        with self._lock:
            self._cache[key] = value
            self._timestamps[key] = time.time()

# 缓存实例
realtime_cache = SimpleCache(default_ttl=10)
cyq_cache = SimpleCache(default_ttl=300)
north_cache = SimpleCache(default_ttl=60)  # 北向资金缓存1分钟
sentiment_cache = SimpleCache(default_ttl=120)  # 市场情绪缓存2分钟

# ====== V10新增：北向资金（真实数据）======
def get_north_flow_real():
    """
    获取真实的北向资金数据
    数据来源：Tushare moneyflow_hsgt + 东方财富备用
    """
    # 检查缓存
    cached = north_cache.get("north_flow")
    if cached:
        return cached
    
    result = {'val': 0, 'hgt': 0, 'sgt': 0, 'date': '', 'valid': False}
    
    # 方法1：Tushare（5000积分可用）
    try:
        today = datetime.now().strftime('%Y%m%d')
        # 获取最近5天数据，找到最新的
        start = (datetime.now() - timedelta(days=5)).strftime('%Y%m%d')
        df = pro.moneyflow_hsgt(start_date=start, end_date=today)
        
        if df is not None and not df.empty:
            # 取最新一天
            latest = df.iloc[0]
            # north_money 单位是百万元，转换为亿元
            north_val = latest.get('north_money', 0) / 100 if pd.notna(latest.get('north_money')) else 0
            hgt_val = latest.get('hgt', 0) / 100 if pd.notna(latest.get('hgt')) else 0
            sgt_val = latest.get('sgt', 0) / 100 if pd.notna(latest.get('sgt')) else 0
            
            result = {
                'val': round(north_val, 2),
                'hgt': round(hgt_val, 2),  # 沪股通
                'sgt': round(sgt_val, 2),  # 深股通
                'date': latest.get('trade_date', ''),
                'valid': True
            }
            north_cache.set("north_flow", result)
            return result
    except Exception as e:
        print(f"Tushare北向资金获取失败: {e}")
    
    # 方法2：东方财富备用
    try:
        url = "https://push2.eastmoney.com/api/qt/kamt.rtmin/get"
        params = {
            "fields1": "f1,f2,f3,f4",
            "fields2": "f51,f52,f53,f54,f55,f56"
        }
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('data'):
                # 解析东方财富数据
                s2n = data['data'].get('s2n', [])  # 北向资金分时
                if s2n:
                    latest = s2n[-1].split(',')
                    if len(latest) >= 4:
                        north_val = float(latest[1]) / 10000 if latest[1] != '-' else 0  # 转换为亿
                        result = {
                            'val': round(north_val, 2),
                            'hgt': 0,
                            'sgt': 0,
                            'date': datetime.now().strftime('%Y%m%d'),
                            'valid': True,
                            'source': 'eastmoney'
                        }
                        north_cache.set("north_flow", result)
                        return result
    except Exception as e:
        print(f"东方财富北向资金获取失败: {e}")
    
    return result

# ====== V10新增：市场情绪指标 ======
def get_market_sentiment():
    """
    获取市场情绪指标
    包括：涨跌停家数、炸板率、连板股数量
    """
    cached = sentiment_cache.get("sentiment")
    if cached:
        return cached
    
    result = {
        'limit_up': 0,      # 涨停家数
        'limit_down': 0,    # 跌停家数
        'broken': 0,        # 炸板家数
        'broken_rate': 0,   # 炸板率
        'continuous': 0,    # 连板股数量
        'sentiment_score': 50,  # 情绪分数 0-100
        'sentiment_text': '中性',
        'valid': False
    }
    
    try:
        # 获取最近交易日
        today = datetime.now().strftime('%Y%m%d')
        target_date = None
        for i in range(5):
            d = (datetime.now() - timedelta(days=i)).strftime('%Y%m%d')
            try:
                check = pro.trade_cal(exchange='SSE', start_date=d, end_date=d)
                if not check.empty and check.iloc[0]['is_open'] == 1:
                    target_date = d
                    break
            except Exception:
                continue
        
        if not target_date:
            return result
        
        # 获取涨停统计（5000积分可用 limit_list_d）
        try:
            # 涨停
            df_up = pro.limit_list_d(trade_date=target_date, limit_type='U')
            if df_up is not None and not df_up.empty:
                result['limit_up'] = len(df_up)
                # 炸板数（open_times > 0 表示开过板）
                broken = len(df_up[df_up['open_times'] > 0])
                result['broken'] = broken
                result['broken_rate'] = round(broken / len(df_up) * 100, 1) if len(df_up) > 0 else 0
                # 连板股（limit_times >= 2）
                continuous = len(df_up[df_up['limit_times'] >= 2])
                result['continuous'] = continuous
            
            # 跌停
            df_down = pro.limit_list_d(trade_date=target_date, limit_type='D')
            if df_down is not None and not df_down.empty:
                result['limit_down'] = len(df_down)
            
            result['valid'] = True
            
        except Exception as e:
            print(f"涨跌停统计获取失败: {e}")
            # 降级方案：用 stk_limit 接口
            try:
                df_limit = pro.stk_limit(trade_date=target_date)
                if df_limit is not None and not df_limit.empty:
                    result['limit_up'] = len(df_limit[df_limit['up_limit'] > 0])
                    result['limit_down'] = len(df_limit[df_limit['down_limit'] > 0])
                    result['valid'] = True
            except Exception:
                pass
        
        # 计算情绪分数
        up = result['limit_up']
        down = result['limit_down']
        broken_rate = result['broken_rate']
        
        if up > 0 or down > 0:
            # 涨跌停比例
            ratio = up / (up + down) if (up + down) > 0 else 0.5
            # 炸板率惩罚
            broken_penalty = broken_rate / 100 * 20
            # 情绪分数
            score = ratio * 80 + 20 - broken_penalty
            score = max(0, min(100, score))
            result['sentiment_score'] = round(score)
            
            if score >= 70:
                result['sentiment_text'] = '🔥 极度亢奋'
            elif score >= 55:
                result['sentiment_text'] = '📈 偏多'
            elif score >= 45:
                result['sentiment_text'] = '⚖️ 中性'
            elif score >= 30:
                result['sentiment_text'] = '📉 偏空'
            else:
                result['sentiment_text'] = '❄️ 极度恐慌'
        
        sentiment_cache.set("sentiment", result)
        
    except Exception as e:
        print(f"市场情绪获取失败: {e}")
    
    return result

# ====== V10新增：热门板块（真实数据）======
def get_hot_sectors_real():
    """获取真实的热门板块数据"""
    try:
        # 使用同花顺概念指数
        today = datetime.now().strftime('%Y%m%d')
        # 获取最近交易日
        for i in range(5):
            d = (datetime.now() - timedelta(days=i)).strftime('%Y%m%d')
            try:
                df = pro.ths_daily(trade_date=d, fields='ts_code,name,pct_change')
                if df is not None and not df.empty:
                    # 按涨幅排序，取前5
                    df = df.sort_values('pct_change', ascending=False)
                    top5 = df.head(5)
                    sectors = []
                    for _, row in top5.iterrows():
                        name = row['name']
                        # 简化名称
                        if len(name) > 4:
                            name = name[:4]
                        sectors.append(name)
                    return sectors
            except Exception:
                continue
    except Exception as e:
        print(f"热门板块获取失败: {e}")
    
    # 降级返回默认值
    return sector_mgr.get_hot_sectors() if hasattr(sector_mgr, 'get_hot_sectors') else ['暂无数据']

# ====== 批量获取实时行情 ======
def get_realtime_batch(ts_codes):
    if not ts_codes:
        return {}
    
    result = {}
    uncached = []
    for code in ts_codes:
        cached = realtime_cache.get(f"rt_{code}")
        if cached:
            result[code] = cached
        else:
            uncached.append(code)
    
    if not uncached:
        return result
    
    tx_codes = []
    code_map = {}
    for ts_code in uncached:
        try:
            code, market = ts_code.split('.')
            tx_code = f"{market.lower()}{code}"
            tx_codes.append(tx_code)
            code_map[tx_code] = ts_code
        except Exception:
            pass
    
    if not tx_codes:
        return result
    
    try:
        url = f"http://qt.gtimg.cn/q={','.join(tx_codes)}"
        resp = requests.get(url, timeout=3)
        if resp.status_code == 200:
            for line in resp.text.strip().split('\n'):
                if '="' not in line:
                    continue
                try:
                    tx_code = line.split('v_')[1].split('=')[0]
                    data = line.split('="')[1].split('~')
                    if len(data) > 32 and tx_code in code_map:
                        ts_code = code_map[tx_code]
                        rt_data = {
                            'price': float(data[3]) if data[3] else 0,
                            'pre_close': float(data[4]) if data[4] else 0,
                            'open': float(data[5]) if data[5] else 0,
                            'change_pct': float(data[32]) if data[32] else 0,
                            'valid': True
                        }
                        result[ts_code] = rt_data
                        realtime_cache.set(f"rt_{ts_code}", rt_data)
                except Exception:
                    pass
    except Exception:
        pass
    
    for code in uncached:
        if code not in result:
            result[code] = {'price': 0, 'pre_close': 0, 'open': 0, 'change_pct': 0, 'valid': False}
    
    return result

def get_realtime_safe(ts_code):
    cached = realtime_cache.get(f"rt_{ts_code}")
    if cached:
        return cached
    
    try:
        code, market = ts_code.split('.')
        tx_code = f"{market.lower()}{code}"
        url = f"http://qt.gtimg.cn/q={tx_code}"
        resp = requests.get(url, timeout=1.5)
        if resp.status_code == 200 and '="' in resp.text:
            data = resp.text.split('="')[1].split('~')
            if len(data) > 30:
                rt_data = {'price': float(data[3]), 'pre_close': float(data[4]), 'open': float(data[5]), 'change_pct': float(data[32]), 'valid': True}
                realtime_cache.set(f"rt_{ts_code}", rt_data)
                return rt_data
    except: pass
    return {'price': 0, 'pre_close': 0, 'open': 0, 'change_pct': 0, 'valid': False}

def get_cyq_analysis(ts_code, daily_rows=None, current_price=0.0):
    if daily_rows and len(daily_rows) > 0:
        try:
            if V9_CHIP_ENABLED:
                return get_cyq_analysis_v9(ts_code, pro=pro, daily_rows=daily_rows, current_price=float(current_price or 0.0))
            else:
                return cyq_analyze(ts_code, pro=pro, daily_rows=daily_rows, current_price=float(current_price or 0.0))
        except Exception:
            return {'avg_cost': 0, 'winner_rate': 0, 'desc': '无数据', 'valid': False}
    
    cache_key = f"cyq_{ts_code}"
    cached = cyq_cache.get(cache_key)
    if cached:
        return cached
    
    try:
        if V9_CHIP_ENABLED:
            result = get_cyq_analysis_v9(ts_code, pro=pro, daily_rows=[], current_price=float(current_price or 0.0))
        else:
            result = cyq_analyze(ts_code, pro=pro, daily_rows=[], current_price=float(current_price or 0.0))
        
        if result.get('valid'):
            cyq_cache.set(cache_key, result)
        return result
    except Exception:
        return {'avg_cost': 0, 'winner_rate': 0, 'desc': '无数据', 'valid': False}

def get_north_flow():
    """兼容旧接口"""
    data = get_north_flow_real()
    return {'val': data['val']}

def check_dragon_tiger(ts_code):
    try:
        start = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')
        df = pro.top_list(ts_code=ts_code, start_date=start, end_date=(datetime.now().strftime('%Y%m%d')))
        if not df.empty: return {'on_list': True, 'desc': '🔥 近期登榜'}
    except: pass
    return {'on_list': False, 'desc': ''}

def check_dragon_tiger(ts_code):
    """检查龙虎榜（从V10移植）"""
    try:
        start = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')
        df = pro.top_list(ts_code=ts_code, start_date=start, end_date=(datetime.now().strftime('%Y%m%d')))
        if not df.empty: 
            return {'on_list': True, 'desc': '🔥 近期登榜'}
    except Exception:
        pass
    return {'on_list': False, 'desc': ''}

def check_finance_risk(ts_code):
    try:
        info = pro.stock_basic(ts_code=ts_code, fields='name')
        if not info.empty and ('ST' in info.iloc[0]['name']): return {'risk': True, 'msg': '退市风险(ST)'}
        now = datetime.now().strftime('%Y%m%d')
        df = pro.daily_basic(ts_code=ts_code, trade_date=now, fields='pe_ttm')
        if df.empty:
             prev = (datetime.now() - timedelta(days=3)).strftime('%Y%m%d')
             df = pro.daily_basic(ts_code=ts_code, trade_date=prev, fields='pe_ttm')
        if not df.empty:
            if df.iloc[0]['pe_ttm'] is not None and df.iloc[0]['pe_ttm'] < 0: return {'risk': True, 'msg': '业绩亏损'}
    except: pass
    return {'risk': False, 'msg': ''}

def ensure_history_data(ts_code):
    daily = db.get_daily_data(ts_code, days=60)
    if len(daily) < 30:
        try:
            end = datetime.now().strftime('%Y%m%d')
            start = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
            df = pro.daily(ts_code=ts_code, start_date=start, end_date=end)
            if not df.empty: db.save_daily_data(df)
            flow = pro.moneyflow(ts_code=ts_code, start_date=start, end_date=end)
            if not flow.empty: db.save_money_flow(flow)
        except: pass

# ====== V10新增：推荐准确率统计 ======
def init_recommend_tracking():
    """初始化推荐追踪表"""
    db_path = config['database_path']
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recommend_track (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT,
            name TEXT,
            recommend_date TEXT,
            recommend_price REAL,
            recommend_score INTEGER,
            recommend_type TEXT,
            day1_price REAL,
            day1_change REAL,
            day3_price REAL,
            day3_change REAL,
            day5_price REAL,
            day5_change REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_recommend_track(stocks):
    """保存推荐记录（V10升级：使用新的recommendation_history表）"""
    if not stocks:
        return
    
    for s in stocks:
        try:
            db.save_recommendation(
                ts_code=s['ts_code'],
                name=s['name'],
                price=s['price'],
                score=s['score'],
                rec_type=s['type'],
                reason=s.get('reason', '')
            )
        except Exception as e:
            print(f"保存推荐记录失败: {e}")

def get_recommend_accuracy():
    """获取推荐准确率统计"""
    db_path = config['database_path']
    try:
        conn = sqlite3.connect(db_path)
        # 获取有day3_change数据的记录
        df = pd.read_sql("""
            SELECT * FROM recommend_track 
            WHERE day3_change IS NOT NULL
            ORDER BY recommend_date DESC
            LIMIT 100
        """, conn)
        conn.close()
        
        if df.empty:
            return {'total': 0, 'win': 0, 'rate': 0, 'avg_return': 0}
        
        total = len(df)
        win = len(df[df['day3_change'] > 0])
        rate = round(win / total * 100, 1)
        avg_return = round(df['day3_change'].mean(), 2)
        
        return {
            'total': total,
            'win': win,
            'rate': rate,
            'avg_return': avg_return
        }
    except Exception:
        return {'total': 0, 'win': 0, 'rate': 0, 'avg_return': 0}

# 初始化推荐追踪表
try:
    init_recommend_tracking()
except Exception:
    pass

# ====== 路由 ======
@app.get("/")
async def index(request: Request): return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/search")
async def search(request: Request):
    data = await request.json()
    return JSONResponse({'stocks': db.get_stock_by_name(data.get('keyword','').strip())})

@app.get("/api/decision/{ts_code}")
async def get_decision(ts_code: str):
    """获取股票决策建议API"""
    stock = db.get_stock_by_code(ts_code)
    if not stock: 
        return JSONResponse({'error': 'Stock not found'}, status_code=404)
    
    ensure_history_data(ts_code)
    daily = db.get_daily_data(ts_code, 300)
    flow = db.get_money_flow(ts_code, 30)
    mkt = db.get_daily_data('000001.SH', 300)
    
    dec = scoring_engine.generate_decision(ts_code, stock, daily, flow, mkt)
    rt = get_realtime_safe(ts_code)
    if rt['valid']:
        dec['current_price'] = rt['price']
        dec['change_pct'] = rt['change_pct']
    elif daily:
        dec['current_price'] = daily[0]['close']
        dec['change_pct'] = daily[0]['change_pct']
    
    cyq = get_cyq_analysis(ts_code, daily_rows=daily, current_price=dec.get('current_price', 0))
    fina = check_finance_risk(ts_code)
    
    # V9评分
    if V9_FACTOR_ENABLED and daily and len(daily) > 0:
        try:
            v9_score, v9_breakdown, v9_decision = calculate_v9_score(daily, flow, mkt, cyq)
            dec['v9_score'] = v9_score
            dec['v9_breakdown'] = v9_breakdown
            dec['v9_decision'] = v9_decision
            dec['score'] = v9_score
        except:
            pass
    
    # 应用修复后的决策逻辑
    win = cyq['winner_rate'] if cyq.get('valid') else 0
    avg = cyq['avg_cost'] if cyq.get('valid') else 0
    curr = dec.get('current_price', 0)
    score = dec.get('score', 50)
    net_flow = flow[0]['main_net_inflow'] if flow else 0
    # net_flow 单位已经是万元（Tushare返回），直接使用
    flow_val = round(net_flow, 2) if net_flow else 0
    
    cmd_pos = "0成"; cmd_loss = 0; cmd_target = 0
    human_talk = ""
    
    # 涨跌停特殊处理（优先级最高）
    change_pct = 0
    if daily and len(daily) > 0:
        change_pct = daily[0].get('change_pct', 0)
    
    if change_pct >= 9.8:
        # 修复：阈值单位改为万元（Tushare返回万元）
        if net_flow > 1000:  # 1000万元
            dec['action'] = "涨停强势"; dec['action_class'] = "go"
            human_talk = f"🚀 涨停板：主力流入{flow_val}万，封单坚决！"
        elif net_flow < -3000:  # -3000万元
            dec['action'] = "涨停出货"; dec['action_class'] = "watch"
            human_talk = f"⚠️ 涨停出货：主力流出{abs(flow_val)}万，封单不稳！"
        else:
            dec['action'] = "涨停观察"; dec['action_class'] = "watch"
            human_talk = "📈 涨停板：封单稳定，继续持有观察。"
    elif change_pct <= -9.8:
        if net_flow > 3000:  # 3000万元
            dec['action'] = "跌停抄底"; dec['action_class'] = "fake-drop"
            human_talk = f"💎 跌停抄底：主力抄底{flow_val}万，可能反转！"
        else:
            dec['action'] = "跌停逃命"; dec['action_class'] = "run"
            human_talk = "💀 跌停板：资金夺路而逃！"
    elif change_pct >= 8.0:
        dec['action'] = "冲击涨停"; dec['action_class'] = "go"
        human_talk = f"🔥 冲击涨停：涨幅{change_pct:.1f}%，有望封板！"
    elif change_pct >= 5.0:
        if score >= 70:
            dec['action'] = "强势上涨"; dec['action_class'] = "go"
            human_talk = f"💪 强势上涨：涨幅{change_pct:.1f}%，趋势良好！"
        else:
            dec['action'] = "涨幅过大"; dec['action_class'] = "watch"
            human_talk = f"⚠️ 涨幅过大：涨{change_pct:.1f}%但技术面不佳。"
    elif change_pct <= -5.0:
        if net_flow > 1000:  # 1000万元
            dec['action'] = "超跌反弹"; dec['action_class'] = "fake-drop"
            human_talk = f"🎯 超跌反弹：跌{abs(change_pct):.1f}%但主力抄底！"
        else:
            dec['action'] = "加速下跌"; dec['action_class'] = "run"
            human_talk = f"📉 加速下跌：跌{abs(change_pct):.1f}%且资金流出！"
    else:
        # 普通情况使用原有逻辑
        if win > 90 and score < 55:
            if net_flow > 0:
                dec['action'] = "洗盘"; dec['action_class'] = "fake-drop"
                human_talk = f"⚖️ 高位洗盘：主力流入{flow_val}万"
            else:
                dec['action'] = "高位减仓"; dec['action_class'] = "watch"
                human_talk = f"⚖️ 高位震荡：可适当减仓"
        elif win > 60:
            dec['action'] = "持有"; dec['action_class'] = "watch"
            human_talk = "📈 趋势健康，继续持有"
        elif win < 10:
            if net_flow > 0:
                dec['action'] = "抄底"; dec['action_class'] = "fake-drop"
                human_talk = f"💎 超跌反弹：主力流入{flow_val}万"
            else:
                dec['action'] = "观望"; dec['action_class'] = "watch"
                human_talk = "⚖️ 底部震荡，暂时观望"
        else:
            dec['action'] = "震荡"; dec['action_class'] = "watch"
            human_talk = "⚖️ 区间震荡，高抛低吸"
    
    if fina['risk']:
        human_talk = f"💣 {fina['msg']}！" + human_talk
    
    dec['explanation'] = human_talk
    dec['stock_info'] = stock
    
    return JSONResponse(dec)

@app.get("/api/stock/{ts_code}")
async def stock_detail(ts_code: str):
    stock = db.get_stock_by_code(ts_code)
    if not stock: raise HTTPException(404)
    ensure_history_data(ts_code)
    daily = db.get_daily_data(ts_code, 300)
    flow = db.get_money_flow(ts_code, 30)
    mkt = db.get_daily_data('000001.SH', 300)
    
    dec = scoring_engine.generate_decision(ts_code, stock, daily, flow, mkt)
    rt = get_realtime_safe(ts_code)
    if rt['valid']:
        dec['current_price'] = rt['price']
        dec['change_pct'] = rt['change_pct']
        if flow:
            is_thun, _ = market_monitor.check_thunder_alert(rt['price'], rt['open'], flow[0]['main_net_inflow'])
            dec['thunder_alert'] = is_thun
    elif daily:
        dec['current_price'] = daily[0]['close']
        dec['change_pct'] = daily[0]['change_pct']
        
    cyq = get_cyq_analysis(ts_code, daily_rows=daily, current_price=dec.get('current_price', 0))
    dec['cyq_data'] = cyq
    dec['dragon_tiger'] = check_dragon_tiger(ts_code)
    fina = check_finance_risk(ts_code)
    dec['finance'] = fina

    # ====== V10修复：先获取实时资金数据，再计算评分 ======
    realtime_fund_data = None
    if REALTIME_FUND_ENABLED and realtime_fund:
        try:
            realtime_fund_data = realtime_fund.get_realtime_fund_analysis(ts_code)
        except Exception as e:
            print(f"实时资金流获取失败: {e}")

    if V9_FACTOR_ENABLED:
        try:
            # V10修复：传入实时资金数据给评分引擎
            v9_score, v9_breakdown, v9_decision = calculate_v9_score(daily, flow, mkt, cyq, realtime_fund_data)
            dec['v9_score'] = v9_score
            dec['v9_breakdown'] = v9_breakdown
            dec['v9_decision'] = v9_decision
            dec['score'] = v9_score

            if v9_decision in ['搞！', '主升浪', '抄底']:
                dec['action'] = v9_decision
                dec['action_class'] = 'go'
            elif v9_decision in ['回避', '止盈']:
                dec['action'] = v9_decision
                dec['action_class'] = 'run'
            elif v9_decision == '洗盘':
                dec['action'] = v9_decision
                dec['action_class'] = 'fake-drop'
        except Exception as e:
            dec['v9_error'] = str(e)

    mkt_dict = {'index_change': 0} 
    risk_res = risk_mgr.analyze(daily, flow, mkt_dict, dec['score'])
    dec['risk_radar'] = risk_res['text']
    
    # V10新增：增强风控分析
    if ENHANCED_RISK_ENABLED and enhanced_risk and daily:
        try:
            # 计算ATR用于动态止损
            atr = enhanced_risk.calculate_atr(daily)
            dec['atr'] = round(atr, 2)
            
            # 市场状态识别
            if mkt and len(mkt) >= 200:
                market_regime = enhanced_risk.detect_market_regime(mkt)
                dec['market_regime'] = market_regime['regime']
                dec['market_confidence'] = market_regime['confidence']
        except Exception:
            pass

    win = cyq.get('winner_rate', 0) if cyq.get('valid', False) else 0
    avg = cyq.get('avg_cost', 0) if cyq.get('valid', False) else 0
    curr = dec.get('current_price', 0)
    score = dec.get('score', 50)
    net_flow = flow[0]['main_net_inflow'] if flow else 0
    # net_flow 单位是万元（Tushare moneyflow接口返回万元）
    flow_val = round(net_flow, 2)  # 直接使用，无需转换
    
    # ====== V10：使用之前获取的实时资金数据 ======
    realtime_warning = None
    if realtime_fund_data and realtime_fund_data.get('valid'):
        # 用实时数据覆盖历史数据
        realtime_net = realtime_fund_data.get('main_net', 0)
        dec['realtime_fund'] = realtime_fund_data
        dec['main_inflow_text'] = f"{'🔴' if realtime_net < 0 else '🟢'} 实时主力 {realtime_fund_data.get('main_net_text', '0万')}"
        
        # 检测数据背离（历史数据是正的，但实时是负的）
        if net_flow > 100 and realtime_net < -100:
            realtime_warning = "⚠️ 资金背离警告：昨日流入但今日转为流出！"
            dec['realtime_warning'] = realtime_warning
        
        # 检测实时大幅流出
        if realtime_net < -500:
            realtime_warning = "🔴 盘中资金大幅流出！谨慎操作"
            dec['realtime_warning'] = realtime_warning
        
        # 检测下跌中的资金流出
        change_pct_today = dec.get('change_pct', 0)
        if change_pct_today < -3 and realtime_net < 0:
            realtime_warning = f"🆘 下跌{abs(change_pct_today):.1f}%+资金流出，不宜抄底！"
            dec['realtime_warning'] = realtime_warning
            # 同时修改决策
            if score > 60:
                dec['v9_decision'] = '⚠️ 盘中走弱'
                dec['action'] = '观望'
                dec['action_class'] = 'watch'
        
        # 更新资金流数据为实时数据
        net_flow = realtime_net
        flow_val = realtime_net

    cmd_pos = "0成"; cmd_loss = 0; cmd_target = 0

    human_talk = ""
    
    # ====== V10修复：涨跌停板特殊处理 ======
    # 关键修复：使用实时涨幅，而非历史数据
    # 注意：必须检查key是否存在，而不是检查值是否为0（0%是有效的实时数据）
    if 'change_pct' in dec:
        change_pct = dec['change_pct']  # 使用实时数据
    elif daily:
        change_pct = daily[0].get('change_pct', 0)  # 没有实时数据才用历史
    else:
        change_pct = 0
    


    # 涨停板逻辑（优先级最高）
    if change_pct >= 9.8:
        # 使用涨停板分析器进行深度分析
        if LIMIT_ANALYSIS_ENABLED and limit_analyzer:
            # 修复：先计算vol，避免变量未定义错误
            latest_vol = daily[0].get('vol', 0) if daily else 0
            avg_vol_20 = sum([d.get('vol', 0) for d in daily[:20]]) / 20 if daily and len(daily) >= 20 else 1
            vol_ratio = latest_vol / avg_vol_20 if avg_vol_20 > 0 else 1
            
            limit_data = {
                'pct_change': change_pct,
                'volume_ratio': vol_ratio,
                'net_inflow': net_flow,
                'bid_ratio': 1,  # 需要实时数据计算封单比
                'open_times': 0,  # 需要分时数据
                'time_to_limit': 60,  # 需要分时数据
            }
            
            analysis = limit_analyzer.analyze_limit_up_strength('', limit_data)
            limit_type = analysis.get('type', '涨停')
            strength = analysis.get('strength', 70)
            next_day_forecast = analysis.get('next_day_forecast', '')
            
            # 根据涨停强度调整策略
            if strength >= 90:  # 超强涨停
                dec['action'] = "涨停强势"; dec['action_class'] = "go"
                human_talk = f"🚀 **{limit_type}**：封单坚决，明日{next_day_forecast}！\n👉 **持有待连板，不要卖飞！**"
                cmd_pos = "8成"; cmd_loss = curr * 0.95; cmd_target = curr * 1.2
            elif strength >= 70:  # 正常涨停
                dec['action'] = "涨停观察"; dec['action_class'] = "watch"
                human_talk = f"📈 **{limit_type}**：涨停封住，{next_day_forecast}。\n👉 **持有为主，高开可减仓！**"
                cmd_pos = "5成"; cmd_loss = curr * 0.96; cmd_target = curr * 1.1
            else:  # 弱势涨停
                dec['action'] = "涨停谨慎"; dec['action_class'] = "watch"
                human_talk = f"⚠️ **{limit_type}**：封单不稳，{next_day_forecast}。\n👉 **见好就收，不要贪心！**"
                cmd_pos = "3成"; cmd_loss = curr * 0.97; cmd_target = curr * 1.05
        else:
            # 原有逻辑作为后备（修复：阈值单位改为万元）
            if net_flow > 1000:  # 1000万元
                dec['action'] = "涨停强势"; dec['action_class'] = "go"
                human_talk = f"🚀 **涨停板**：主力流入{flow_val}万，封单坚决！\n👉 **持有待连板，不要卖飞！**"
                cmd_pos = "8成"; cmd_loss = curr * 0.95; cmd_target = curr * 1.2
            elif net_flow < -3000:  # -3000万元
                dec['action'] = "涨停出货"; dec['action_class'] = "watch"
                human_talk = f"⚠️ **涨停出货**：主力流出{abs(flow_val)}万，封单不稳！\n👉 **谨慎持有，随时准备撤！**"
                cmd_pos = "3成"; cmd_loss = curr * 0.97; cmd_target = curr * 1.05
            else:
                dec['action'] = "涨停观察"; dec['action_class'] = "watch"
                human_talk = "📈 **涨停板**：封单稳定，继续持有观察。\n👉 **不追高，持有者继续拿！**"
                cmd_pos = "5成"; cmd_loss = curr * 0.96; cmd_target = curr * 1.15
    
    # 跌停板逻辑
    elif change_pct <= -9.8:
        if net_flow > 2000:  # 跌停但有2000万以上资金抄底（单位：万元）
            dec['action'] = "跌停抄底"; dec['action_class'] = "fake-drop"
            human_talk = f"💎 **跌停抄底**：主力抄底{flow_val}万，可能反转！\n👉 **激进者小仓试探！**"
            cmd_pos = "1成"; cmd_loss = curr * 0.95; cmd_target = curr * 1.1
        elif net_flow > 0:  # 有资金流入就提示关注
            dec['action'] = "跌停观察"; dec['action_class'] = "watch"
            human_talk = f"👀 **跌停观察**：有资金流入{flow_val}万，关注反弹。\n👉 **暂时观望，等待企稳！**"
            cmd_pos = "0成"; cmd_loss = 0; cmd_target = 0
        else:
            dec['action'] = "跌停逃命"; dec['action_class'] = "run"
            human_talk = "💀 **跌停板**：资金夺路而逃！\n👉 **立即止损，不要幻想！**"
            cmd_pos = "0成"; cmd_loss = 0; cmd_target = 0
    
    # 准涨停板（8%-9.8%）
    elif change_pct >= 8.0 and change_pct < 9.8:
        dec['action'] = "冲击涨停"; dec['action_class'] = "go"
        human_talk = f"🔥 **冲击涨停**：涨幅{change_pct:.1f}%，有望封板！\n👉 **持有为主，不要获利了结！**"
        cmd_pos = "6成"; cmd_loss = curr * 0.94; cmd_target = curr * 1.1
    
    # 主升浪（7%-8%） - 新增：涨幅>7%直接显示主升
    elif change_pct >= 7.0 and change_pct < 8.0:
        dec['action'] = "主升浪"; dec['action_class'] = "go"
        human_talk = f"🚀 **主升浪**：涨幅{change_pct:.1f}%，强势突破！\n👉 **持有待涨停，不要卖飞！**"
        cmd_pos = "7成"; cmd_loss = curr * 0.94; cmd_target = curr * 1.1
    
    # 大涨（5%-7%）
    elif change_pct >= 5.0 and change_pct < 7.0:
        if score >= 70:
            dec['action'] = "强势上涨"; dec['action_class'] = "go"
            human_talk = f"💪 **强势上涨**：涨幅{change_pct:.1f}%，趋势良好！\n👉 **持有为主，可适当加仓！**"
            cmd_pos = "5成"; cmd_loss = curr * 0.95; cmd_target = curr * 1.08
        elif net_flow > 5000:  # 资金流入5000万以上，不建议减仓
            dec['action'] = "资金推动"; dec['action_class'] = "go"
            human_talk = f"🔥 **资金推动**：涨{change_pct:.1f}%且主力流入{flow_val:.0f}万！\n👉 **资金说了算，跟着主力走！**"
            cmd_pos = "5成"; cmd_loss = curr * 0.95; cmd_target = curr * 1.1
        elif net_flow > 1000:  # 1000-5000万资金流入
            dec['action'] = "谨慎持有"; dec['action_class'] = "watch"
            human_talk = f"📊 **谨慎持有**：涨{change_pct:.1f}%技术面弱但资金流入{flow_val:.0f}万。\n👉 **观察为主，有支撑！**"
            cmd_pos = "4成"; cmd_loss = curr * 0.96; cmd_target = curr * 1.05
        else:
            dec['action'] = "涨幅过大"; dec['action_class'] = "watch"
            human_talk = f"⚠️ **涨幅过大**：涨{change_pct:.1f}%但技术面不佳且资金不强。\n👉 **逢高减仓，锁定利润！**"
            cmd_pos = "3成"; cmd_loss = curr * 0.97; cmd_target = curr * 1.03
    

    # 小幅下跌（-2% ~ 0%）洗盘判断
    elif -2 <= change_pct < 0:
        if net_flow > 100 and score >= 55:  # 资金流入100万以上且评分合格（单位：万元）
            dec['action'] = "主力洗盘"; dec['action_class'] = "fake-drop"
            human_talk = f"💎 **主力洗盘**：小跌{abs(change_pct):.1f}%但资金流入{flow_val}万。\n👉 **假跌真吸，敢于低吸！**"
            cmd_pos = "5成"; cmd_loss = curr * 0.96; cmd_target = curr * 1.08
        elif score >= 65:
            dec['action'] = "技术调整"; dec['action_class'] = "watch"
            human_talk = f"📊 **技术调整**：小幅回调{abs(change_pct):.1f}%，技术面尚可。\n👉 **持股待涨，轻仓可补！**"
            cmd_pos = "3成"; cmd_loss = curr * 0.97; cmd_target = curr * 1.05
        else:
            dec['action'] = "震荡调整"; dec['action_class'] = "watch"
            human_talk = f"😐 **震荡调整**：缩量调整{abs(change_pct):.1f}%。\n👉 **观望为主，等待方向！**"
            cmd_pos = "2成"; cmd_loss = curr * 0.98; cmd_target = curr * 1.02
    
    # 大跌（-5%以下）
    elif change_pct <= -5.0 and change_pct > -9.8:
        if net_flow > 1000:  # 1000万以上资金抄底（单位：万元）
            dec['action'] = "超跌反弹"; dec['action_class'] = "fake-drop"
            human_talk = f"🎯 **超跌反弹**：跌{abs(change_pct):.1f}%但主力抄底{flow_val}万！\n👉 **可以试探性买入！**"
            cmd_pos = "2成"; cmd_loss = curr * 0.95; cmd_target = curr * 1.05
        else:
            dec['action'] = "加速下跌"; dec['action_class'] = "run"
            human_talk = f"📉 **加速下跌**：跌{abs(change_pct):.1f}%且资金流出！\n👉 **立即止损，别接飞刀！**"
            cmd_pos = "0成"; cmd_loss = 0; cmd_target = 0
    
    # 普通情况才进入原有的获利盘判断逻辑
    elif win > 90:
        if score < 55:
            if net_flow > 0:
                dec['action']="洗盘"; dec['action_class']="fake-drop"
                human_talk = f"⚖️ **资金仲裁**：评分低但主力**逆势流入{flow_val}万**！\n👉 高位洗盘，**拿住别卖飞！**"
                cmd_pos="3成"; cmd_loss=avg*0.95; cmd_target=curr*1.1
            else:
                dec['action']="止盈"; dec['action_class']="run"
                human_talk = f"⚖️ **资金仲裁**：评分低且主力**流出{abs(flow_val)}万**！\n👉 **快跑！落袋为安！**"
                cmd_pos="0成"; cmd_loss=curr; cmd_target=0
        elif avg > 0 and curr < avg:
            dec['action']="假摔"; dec['action_class']="fake-drop"
            human_talk = "⚡ **主力护盘**：跌破成本线但资金流入，诱空陷阱。"
            cmd_pos="5成"; cmd_loss=curr*0.95; cmd_target=avg*1.1
        else:
            dec['action']="主升浪"; dec['action_class']="go"
            human_talk = "🚀 **天空才是极限**：上方无抛压，主力完全控盘。\n**闭眼买，坐等抬轿！**"
            cmd_pos="8成"; cmd_loss=curr*0.92; cmd_target=curr*1.3

    elif win > 60:
        if score < 50:
            dec['action']="减仓"; dec['action_class']="run"
            human_talk = "📉 **趋势转弱**：均线破位，建议防守。"
            cmd_pos="0成"
        else:
            dec['action']="持有"; dec['action_class']="watch"
            human_talk = "📈 **良性上涨**：多方占优，趋势健康。只要不破位，就耐心持有。"
            cmd_pos="5成"; cmd_loss=curr*0.95; cmd_target=curr*1.1
    
    # 中等获利盘(15%-40%)需要更精细判断（修复：阈值单位改为万元）
    elif 15 <= win <= 40:
        if score >= 70 and net_flow > 1000:  # 1000万元
            dec['action'] = "趋势良好"; dec['action_class'] = "go"
            human_talk = f"📊 **趋势良好**：获利盘{win:.0f}%但资金持续流入{flow_val}万。\n👉 **持有为主，趋势未破！**"
            cmd_pos = "6成"; cmd_loss = curr * 0.95; cmd_target = curr * 1.08
        elif score >= 60 and change_pct > 0:
            dec['action'] = "震荡上行"; dec['action_class'] = "watch"
            human_talk = f"📈 **震荡上行**：获利盘{win:.0f}%，短期有压力。\n👉 **高抛低吸，波段操作！**"
            cmd_pos = "4成"; cmd_loss = curr * 0.96; cmd_target = curr * 1.05
        elif score < 50 or net_flow < -1000:  # -1000万元
            dec['action'] = "见顶风险"; dec['action_class'] = "run"  
            human_talk = f"⚠️ **见顶风险**：获利盘{win:.0f}%且技术走弱。\n👉 **逐步减仓，保住利润！**"
            cmd_pos = "2成"; cmd_loss = curr * 0.98; cmd_target = curr * 1.02
        else:
            dec['action'] = "谨慎持有"; dec['action_class'] = "watch"
            human_talk = f"👀 **谨慎持有**：获利盘{win:.0f}%，进入敏感区。\n👉 **密切关注，随时应变！**"
            cmd_pos = "3成"; cmd_loss = curr * 0.97; cmd_target = curr * 1.04

    elif win < 10:
        if net_flow > 0:
            dec['action']="抄底"; dec['action_class']="fake-drop"
            human_talk = "💎 **遍地黄金**：极度超跌且主力回流，**博反弹！**"
            cmd_pos="2成"; cmd_loss=curr*0.93; cmd_target=avg
        else:
            dec['action']="阴跌"; dec['action_class']="run"
            human_talk = "❌ **深不见底**：主力也没买，别接飞刀。"
            cmd_pos="0成"
    
    else:
        # 默认情况：根据资金流判断
        if net_flow > 2000:  # 资金流入2000万以上
            dec['action']="资金托底"; dec['action_class']="watch"
            human_talk = f"📊 **资金托底**：走势平淡但主力净流入{flow_val:.0f}万。\n👉 **有资金支撑，可持有观察！**"
            cmd_pos="3成"
        elif net_flow < -2000:  # 资金流出2000万以上
            dec['action']="资金撤离"; dec['action_class']="watch"
            human_talk = f"⚠️ **资金撤离**：主力净流出{abs(flow_val):.0f}万。\n👉 **谨慎为主，轻仓观望！**"
            cmd_pos="1成"
        else:
            dec['action']="震荡"; dec['action_class']="watch"
            human_talk = "⚖️ **鸡肋行情**：方向不明，建议观望。"
            cmd_pos="0成"

    if fina['risk']: human_talk = f"💣 **{fina['msg']}**\n" + human_talk
    
    if dec['action_class'] == 'run' or dec['action_class'] == 'watch' or cmd_pos == "0成":
        dec['explanation'] = human_talk
    else:
        tactics_html = f"""<div class="t-mini-row"><div class="t-mini-item">⚖️ <span class="t-mini-val">{cmd_pos}</span></div><div class="t-mini-item">🛑 <span class="t-mini-val" style="color:var(--red)">{cmd_loss:.2f}</span></div><div class="t-mini-item">🚩 <span class="t-mini-val" style="color:var(--gold)">{cmd_target:.2f}</span></div></div>"""
        dec['explanation'] = human_talk + tactics_html

    # ====== V10 Ultra Pro：统一裁决检查（防止UI矛盾）======
    if ULTRA_PRO_ENABLED and DecisionCore:
        try:
            decision_core = DecisionCore()
            
            # 检查全局风控（核按钮）
            if ENHANCED_RISK_ENABLED and global_risk_state:
                trading_allowed, kill_reason = global_risk_state.is_trading_allowed()
                if not trading_allowed:
                    decision_core.add_judgment(Priority.P0_ACCOUNT_RISK, Signal.VETO,
                                              kill_reason, 1.0, "global_risk")
            
            # P2: 实时资金
            realtime_net = realtime_fund_data.get('main_net', 0) if realtime_fund_data else net_flow
            if realtime_net < -2000:  # 大幅流出
                decision_core.add_judgment(Priority.P2_REALTIME_FUND, Signal.SELL,
                                          f"主力净流出{abs(realtime_net):.0f}万", 0.8, "realtime_fund")
            elif realtime_net > 2000:  # 大幅流入
                decision_core.add_judgment(Priority.P2_REALTIME_FUND, Signal.BUY,
                                          f"主力净流入{realtime_net:.0f}万", 0.7, "realtime_fund")
            
            # P3: 评分
            if score >= 70:
                decision_core.add_judgment(Priority.P3_TREND_CHIP, Signal.BUY,
                                          f"综合评分{score:.0f}分", 0.6, "score")
            elif score <= 35:
                decision_core.add_judgment(Priority.P3_TREND_CHIP, Signal.SELL,
                                          f"综合评分{score:.0f}分", 0.6, "score")
            
            # 生成裁决
            verdict = decision_core.make_verdict()
            dec['ultra_verdict'] = {
                'action': verdict.action,
                'is_vetoed': verdict.is_vetoed,
                'veto_reasons': verdict.veto_reasons,
                'confidence': verdict.confidence
            }
            
            # 如果被否决，覆盖看多信号（防止UI矛盾）
            if verdict.is_vetoed and dec['action_class'] == 'go':
                # 被否决但原本是看多，强制改为观望
                dec['action'] = verdict.action
                dec['action_class'] = 'watch'
                veto_summary = "、".join(verdict.veto_reasons[:2])
                dec['explanation'] = f"🚨 **裁决否决**：{veto_summary}\n原建议已被否决，请谨慎操作。"
            
            # 计算胜率
            win_rate_result = quick_win_rate(realtime_net, score, 
                                            dec.get('market_regime', 'shock'))
            dec['win_rate'] = win_rate_result
            
            # 记录决策日志
            log_decision(
                ts_code=ts_code,
                stock_name=stock.get('name', ''),
                action=dec['action'],
                action_class=dec['action_class'],
                trigger_factors=[f"score:{score:.0f}", f"fund:{realtime_net:.0f}万"],
                veto_factors=verdict.veto_reasons if verdict.is_vetoed else [],
                final_reason=verdict.primary_reason,
                score=score,
                win_prob=win_rate_result.get('win_prob', 0.5)
            )
        except Exception as e:
            print(f"DecisionCore处理异常: {e}")

    # 主力资金判断（单位：万元）
    # 修复：如果已有实时数据，不要用历史数据覆盖
    if 'main_inflow_text' not in dec or not realtime_fund_data or not realtime_fund_data.get('valid'):
        # 只有在没有实时数据时才使用历史数据
        l2_inflow = flow[0]['main_net_inflow'] if flow else 0

        if l2_inflow > 1000: dec['main_inflow_text'] = f"🔥 主力大买 {int(l2_inflow)}万(昨日)"
        elif l2_inflow > 0: dec['main_inflow_text'] = f"🔴 小幅流入 {int(l2_inflow)}万(昨日)"
        else: dec['main_inflow_text'] = f"💚 主力流出 {int(abs(l2_inflow))}万(昨日)"


    dec['stock_info'] = stock
    return JSONResponse(dec)

# ====== V10升级：市场状态接口 ======
@app.get("/api/market/status")
async def market():
    """V10升级：真实的北向资金 + 市场情绪"""
    st, desc = market_monitor.get_market_status()
    sh = get_realtime_safe('000001.SH')
    
    # V10：真实的北向资金
    north = get_north_flow_real()
    
    # V10：真实的热门板块
    hot = get_hot_sectors_real()
    
    # V10：市场情绪
    sentiment = get_market_sentiment()
    
    return JSONResponse({
        'status': st, 
        'index_point': sh['price'], 
        'index_change': sh['change_pct'], 
        'north_money': north['val'],
        'north_detail': {
            'hgt': north.get('hgt', 0),
            'sgt': north.get('sgt', 0),
            'date': north.get('date', '')
        },
        'hot_sector': hot,
        'sentiment': sentiment
    })


# ====== V10新增：市场情绪接口 ======
@app.get("/api/market/sentiment")
async def market_sentiment():
    """获取详细的市场情绪数据"""
    sentiment = get_market_sentiment()
    north = get_north_flow_real()
    
    return JSONResponse({
        'success': True,
        'data': {
            'sentiment': sentiment,
            'north': north
        }
    })

# ====== V10新增：实时资金流API ======
@app.get("/api/realtime/fund/{ts_code}")
async def realtime_fund_api(ts_code: str):
    """获取实时资金流分析数据"""
    if not REALTIME_FUND_ENABLED or not realtime_fund:
        return JSONResponse({
            "success": False,
            "error": "实时资金流模块未启用"
        })
    
    try:
        data = realtime_fund.get_realtime_fund_analysis(ts_code)
        return JSONResponse({
            "success": True,
            "data": data
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        })

@app.get("/api/radar/scan")

async def radar_scan():
    targets = db.get_watchlist() + db.get_all_positions()
    unique_targets = {v['ts_code']:v for v in targets}.values()
    return JSONResponse({'alerts': radar_mgr.scan(list(unique_targets))})

@app.get("/api/review/daily")
async def daily_review():
    mkt_res = await market()
    mkt = json.loads(mkt_res.body)
    pos_res = await pos_list()
    pos = json.loads(pos_res.body)['positions']
    hot = get_hot_sectors_real()
    return JSONResponse({'html': review_mgr.generate(mkt, pos, hot)})

@app.get("/api/monitor/check")
def monitor_check():
    alerts = []
    alarm = False
    now = datetime.now().time()
    if l2_monitor and (dt_time(9, 24) <= now <= dt_time(9, 31)):
        watchlist = db.get_watchlist()
        for item in watchlist:
            r = l2_monitor.check_call_auction(item['ts_code'])
            if r: alarm = True; alerts.append(r)
    positions = db.get_all_positions()
    for p in positions:
        if l2_monitor:
             r = l2_monitor.check_limit_break(p['ts_code'], p['cost_price'])
             if r: alarm = True; alerts.append(r)
        else:
             rt = get_realtime_safe(p['ts_code'])
             if rt['valid'] and rt['price'] < p['cost_price'] * 0.95:
                 alarm = True; alerts.append(f"🆘 {p['name']} 跌破止损位！")
    return JSONResponse({'alarm':alarm, 'message':" | ".join(alerts) if alerts else "安全"})

# ====== 智能选股 ======
recommend_cache_store = SimpleCache(default_ttl=60)

@app.get("/api/recommend")
async def recommend():
    cached = recommend_cache_store.get("recommend_result")
    if cached:
        return JSONResponse(cached)
    
    try:
        now = datetime.now()
        target_date = None
        for i in range(5):
            d = (now - timedelta(days=i)).strftime('%Y%m%d')
            try: 
                check = pro.daily_basic(trade_date=d, limit=1)
            except: 
                continue
            if not check.empty: 
                target_date = d
                break
        
        if not target_date: 
            return JSONResponse({'success':False, 'stocks':[]})
        
        df = pro.daily_basic(trade_date=target_date, fields='ts_code,close,turnover_rate,volume_ratio,circ_mv', limit=3000)
        pool = df[(df['turnover_rate']>2) & (df['volume_ratio']>0.8) & (df['circ_mv']>300000) & (df['circ_mv']<8000000)]
        
        if len(pool) > 30: 
            candidates = pool.sample(n=30)
        else: 
            candidates = pool
        
        codes = candidates['ts_code'].tolist()
        rt_batch = get_realtime_batch(codes)
        
        final_picks = []
        
        def process_pick(row):
            code = row['ts_code']
            rt = rt_batch.get(code, {'valid': False})
            if not rt.get('valid'): 
                return None
            
            cyq = get_cyq_analysis(code)
            
            try:
                flow_df = pro.moneyflow(ts_code=code, trade_date=target_date)
                net_flow = flow_df.iloc[0]['net_mf_amount']*10000 if not flow_df.empty else 0
            except:
                net_flow = 0
            
            pack = {
                'price': rt['price'], 
                'change': rt['change_pct'], 
                'win_rate': cyq.get('winner_rate', 0), 
                'cost_50': cyq.get('avg_cost', 0), 
                'net_flow': net_flow, 
                'trend_score': 60, 
                'chip_score': cyq.get('winner_rate', 0), 
                'pos_score': 60, 
                'money_score': 60, 
                'env_score': 60, 
                'price_above_ma': 1
            }
            
            is_match, s_type, reason, score = strat_mgr.analyze(pack)
            
            try:
                info = pro.stock_basic(ts_code=code, fields='name')
                name = info.iloc[0]['name'] if not info.empty else code
            except:
                name = code
            
            if 'ST' in name: 
                return None
            
            if is_match: 
                return {
                    'ts_code': code, 
                    'name': name, 
                    'price': rt['price'], 
                    'change': rt['change_pct'], 
                    'score': score, 
                    'type': s_type, 
                    'reason': reason
                }
            return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            results = list(executor.map(process_pick, [row for _, row in candidates.iterrows()]))
        
        for res in results:
            if res: 
                final_picks.append(res)
            if len(final_picks) >= 6: 
                break
            
        final_picks.sort(key=lambda x: x['score'], reverse=True)
        result = {'success': True, 'stocks': final_picks}
        
        # V10：保存推荐记录用于统计准确率
        try:
            save_recommend_track(final_picks)
        except:
            pass
        
        recommend_cache_store.set("recommend_result", result)
        
        return JSONResponse(result)
    except Exception as e:
        print(f"Recommend error: {e}")
        return JSONResponse({'success': False, 'stocks': []})

# ====== V10新增：推荐准确率接口 ======
@app.get("/api/recommend/accuracy")
async def recommend_accuracy():
    """获取推荐准确率统计"""
    acc = get_recommend_accuracy()
    return JSONResponse({
        'success': True,
        'accuracy': acc
    })

# ====== 自选列表 ======
@app.get("/api/watchlist")
async def wl():
    l = db.get_watchlist()
    if not l:
        return JSONResponse({'watchlist': []})
    
    codes = [item['ts_code'] for item in l]
    rt_batch = get_realtime_batch(codes)
    
    res = []
    for item in l:
        rt = rt_batch.get(item['ts_code'], {'price': 0, 'change_pct': 0, 'valid': False})
        res.append({
            **item, 
            'current_price': rt.get('price', 0), 
            'change_pct': rt.get('change_pct', 0),
            'strategy_type': ''
        })
    
    res.sort(key=lambda x: x['change_pct'], reverse=True)
    return JSONResponse({'watchlist': res})

@app.post("/api/watchlist/add")
async def wl_add(r: Request):
    d=await r.json()
    db.add_to_watchlist(d['ts_code'], d['name'], d.get('price',0))
    return JSONResponse({'success':True})

@app.post("/api/watchlist/remove")
async def wl_remove(r: Request):
    d=await r.json()
    db.remove_from_watchlist(d['ts_code'])
    return JSONResponse({'success':True})

# ====== 持仓列表 ======
@app.get("/api/positions")
async def get_positions():
    """获取持仓列表API（兼容路由）"""
    return await pos_list()

@app.get("/api/position/list")
async def pos_list():
    pos = db.get_all_positions()
    if not pos:
        return JSONResponse({'positions': [], 'summary': {'val': 0, 'pnl': 0}})
    
    codes = [p['ts_code'] for p in pos]
    rt_batch = get_realtime_batch(codes)
    
    res = []
    tv = 0
    tp = 0
    for p in pos:
        rt = rt_batch.get(p['ts_code'], {'price': 0, 'valid': False})
        curr = rt['price'] if rt.get('valid') else p['cost_price']
        m_val = curr * p['total_qty']
        f_pnl = (curr - p['cost_price']) * p['total_qty']
        ratio = (f_pnl/(p['cost_price']*p['total_qty'])*100) if (p['cost_price']>0 and p['total_qty']>0) else 0
        res.append({**p, 'current_price':curr, 'market_value':m_val, 'float_pnl':f_pnl, 'float_pnl_ratio':ratio})
        tv += m_val
        tp += f_pnl
    return JSONResponse({'positions':res, 'summary':{'val':tv, 'pnl':tp}})

@app.get("/api/position/summary")
async def pos_sum(): return await pos_list()

@app.post("/api/position/buy")
async def buy(r: Request):
    d=await r.json()
    db.buy_stock(d['ts_code'], d['name'], int(d['qty']), float(d['price']))
    return JSONResponse({'success':True})

@app.post("/api/position/sell")
async def sell(r: Request):
    d=await r.json()
    try:
        pnl = db.sell_stock(d['ts_code'], int(d['qty']), float(d['price']))
        return JSONResponse({'success':True, 'pnl': pnl})
    except Exception as e: return JSONResponse({'success':False, 'error': str(e)})

@app.get("/api/trade/list")
async def trade_list():
    return JSONResponse({'trades': db.get_trade_history()})

@app.post("/api/backtest/{ts_code}")
async def bt(ts_code: str):
    ensure_history_data(ts_code)
    return JSONResponse(backtest_engine.run_backtest(ts_code))

@app.post("/api/sync/stocks")
async def sync():
    try:
        df = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name')
        if df is None or df.empty:
            return JSONResponse({'success': False, 'error': 'stock_basic 无返回/无数据'})
        db.save_stocks(df)
        return JSONResponse({'success': True, 'count': int(len(df))})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)})

# ====== V10 系统信息API ======
@app.get("/api/v10/info")
async def v10_info():
    """V10系统信息"""
    return JSONResponse({
        'version': '10.0.0',
        'name': 'V10 Ultra Pro Terminal',
        'features': {
            'north_money_real': True,
            'market_sentiment': True,
            'recommend_tracking': True,
            'batch_realtime': True,
            'multi_cache': True
        },
        'modules': {
            'cache': V9_CACHE_ENABLED,
            'chip_engine': V9_CHIP_ENABLED,
            'factor_engine': V9_FACTOR_ENABLED
        }
    })

@app.post("/api/v9/regime")
async def set_regime(request: Request):
    if not V9_FACTOR_ENABLED:
        return JSONResponse({'success': False, 'error': 'V9 factor engine not enabled'})
    data = await request.json()
    regime = data.get('regime', 'shock')
    set_market_regime(regime)
    return JSONResponse({'success': True, 'regime': regime})

# ====== 回测功能 (从V10移植) ======
@app.post("/api/backtest/{ts_code}")
async def run_backtest(ts_code: str):
    """运行策略回测"""
    if not BACKTEST_ENABLED or not backtest_engine:
        return JSONResponse({'success': False, 'message': '回测引擎未启用'})
    
    try:
        result = backtest_engine.run_backtest(ts_code)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)})

# ====== 涨停板分析 (新增) ======
@app.get("/api/limitup/daily")
async def get_daily_limitup():
    """获取每日涨停板统计"""
    if not LIMIT_ANALYSIS_ENABLED:
        return JSONResponse({'success': False, 'message': '涨停分析未启用'})
    
    try:
        summary = limit_stats.daily_limit_up_summary()
        return JSONResponse(summary)
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)})

@app.get("/api/limitup/analysis/{ts_code}")
async def analyze_limitup(ts_code: str):
    """分析股票涨停板情况"""
    if not LIMIT_ANALYSIS_ENABLED:
        return JSONResponse({'success': False, 'message': '涨停分析未启用'})
    
    try:
        # 获取股票数据
        daily = db.get_daily_data(ts_code, days=1)
        if not daily:
            return JSONResponse({'success': False, 'message': '无数据'})
        
        current = daily[0]
        if current.get('change_pct', 0) < 9.8:
            return JSONResponse({'success': False, 'message': '未涨停'})
        
        # 分析涨停强度
        analysis = limit_analyzer.analyze_limit_up_strength(ts_code, current)
        
        # 获取统计数据
        stats = wencai_fetcher.get_next_day_performance('')
        
        result = {
            'success': True,
            'analysis': analysis,
            'statistics': stats,
            'suggestion': limit_analyzer.get_limit_up_strategy(
                analysis.get('type', '涨停'),
                'neutral'
            )
        }
        
        return JSONResponse(result)
        
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)})

# ====== V10新增API接口 ======

@app.get("/api/dragon/today")
async def get_dragon_tiger_today():
    """获取今日龙虎榜"""
    if not MARKET_ENHANCER_ENABLED:
        return JSONResponse({'success': False, 'message': '市场增强模块未启用'})
    
    try:
        data = market_enhancer.fetch_dragon_tiger()
        return JSONResponse({'success': True, 'data': data})
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)})

@app.get("/api/dragon/{ts_code}")
async def get_stock_dragon(ts_code: str):
    """获取股票龙虎榜分析"""
    if not MARKET_ENHANCER_ENABLED:
        return JSONResponse({'success': False, 'message': '市场增强模块未启用'})
    
    try:
        analysis = market_enhancer.analyze_dragon_signal(ts_code)
        history = db.get_stock_dragon_tiger(ts_code, days=30)
        return JSONResponse({
            'success': True,
            'analysis': analysis,
            'history': history[:10]  # 最近10次
        })
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)})

@app.get("/api/margin/{ts_code}")
async def get_margin_analysis(ts_code: str):
    """获取融资融券分析"""
    if not MARKET_ENHANCER_ENABLED:
        return JSONResponse({'success': False, 'message': '市场增强模块未启用'})
    
    try:
        # 尝试获取最新数据
        market_enhancer.fetch_margin_data(ts_code, days=10)
        analysis = market_enhancer.analyze_margin_signal(ts_code)
        history = db.get_margin_data(ts_code, days=10)
        return JSONResponse({
            'success': True,
            'analysis': analysis,
            'history': history
        })
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)})

@app.get("/api/ai/morning")
async def get_ai_morning_report():
    """获取AI智能早盘播报"""
    if not AI_PUSH_ENABLED:
        return JSONResponse({'success': False, 'message': 'AI推送模块未启用'})
    
    try:
        # 获取市场状态和情绪
        market_status = get_market_status()
        sentiment = market_status.get('sentiment', {})
        
        # 获取热门板块
        hot_sectors = []
        if MARKET_ENHANCER_ENABLED:
            hot_sectors = market_enhancer.get_hot_sectors()
        
        report = ai_push.generate_morning_report(market_status, sentiment, hot_sectors)
        return JSONResponse({'success': True, 'report': report})
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)})

@app.get("/api/ai/diagnosis")
async def get_ai_position_diagnosis():
    """获取AI持仓诊断"""
    if not AI_PUSH_ENABLED:
        return JSONResponse({'success': False, 'message': 'AI推送模块未启用'})
    
    try:
        positions = db.get_all_positions()
        
        # 为每个持仓获取评分和决策
        enriched = []
        for pos in positions:
            ts_code = pos['ts_code']
            rt = get_realtime_safe(ts_code)
            if rt['valid']:
                pos['current_price'] = rt['price']
            
            try:
                daily = db.get_daily_data(ts_code, 60)
                flow = db.get_money_flow(ts_code, 30)
                mkt = db.get_daily_data('000001.SH', 60)
                cyq = get_cyq_analysis(ts_code, daily_rows=daily, current_price=pos.get('current_price', pos['cost_price']))
                
                v9_score, v9_breakdown, v9_decision = calculate_v9_score(daily, flow, mkt, cyq)
                pos['score'] = v9_score
                pos['decision'] = v9_decision
            except:
                pos['score'] = 50
                pos['decision'] = '观察'
            
            enriched.append(pos)
        
        report = ai_push.generate_position_diagnosis(enriched)
        return JSONResponse({'success': True, 'report': report, 'positions': enriched})
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)})

@app.get("/api/ai/review")
async def get_ai_daily_review():
    """获取AI智能复盘"""
    if not AI_PUSH_ENABLED:
        return JSONResponse({'success': False, 'message': 'AI推送模块未启用'})
    
    try:
        stats = db.get_recommendation_stats(days=30)
        report = ai_push.generate_daily_review(stats)
        return JSONResponse({'success': True, 'report': report, 'stats': stats})
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)})

@app.get("/api/recommend/stats")
async def get_recommendation_stats():
    """获取推荐统计数据"""
    try:
        stats = db.get_recommendation_stats(days=30)
        pending = db.get_pending_recommendations(days_ago=3)
        return JSONResponse({
            'success': True,
            'stats': stats,
            'pending_count': len(pending)
        })
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)})

@app.post("/api/recommend/verify")
async def verify_recommendations():
    """验证待验证的推荐"""
    try:
        pending = db.get_pending_recommendations(days_ago=3)
        results = []
        
        for rec in pending:
            ts_code = rec['ts_code']
            rt = get_realtime_safe(ts_code)
            
            if rt['valid']:
                verify_result = db.verify_recommendation(rec['id'], rt['price'])
                if verify_result:
                    results.append({
                        'ts_code': ts_code,
                        'name': rec['name'],
                        'recommend_price': rec['recommend_price'],
                        'verify_price': rt['price'],
                        'profit_pct': verify_result['profit_pct'],
                        'result': verify_result['result']
                    })
        
        return JSONResponse({
            'success': True,
            'verified_count': len(results),
            'results': results
        })
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)})

@app.get("/api/realtime/fund/{ts_code}")
async def get_realtime_fund_flow(ts_code: str):
    """获取股票实时资金流（多数据源融合）"""
    if not REALTIME_FUND_ENABLED:
        return JSONResponse({'success': False, 'message': '实时资金流模块未启用'})
    
    try:
        data = realtime_fund.get_realtime_fund_analysis(ts_code)
        return JSONResponse({'success': True, 'data': data})
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)})

if __name__ == "__main__":
    uvicorn.run(app, host=config['server']['host'], port=9000, log_level="info")
