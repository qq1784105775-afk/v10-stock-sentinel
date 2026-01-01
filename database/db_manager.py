import sqlite3
import json
import os
from datetime import datetime, timedelta
from contextlib import contextmanager

class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def init_database(self):
        schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_sql = f.read()
        with self.get_connection() as conn:
            conn.executescript(schema_sql)
    
    def save_stocks(self, stocks_df):
        with self.get_connection() as conn:
            for _, row in stocks_df.iterrows():
                conn.execute("INSERT OR REPLACE INTO stocks (ts_code, symbol, name, industry, list_date, updated_at) VALUES (?, ?, ?, ?, ?, ?)", 
                (row['ts_code'], row['symbol'], row['name'], row.get('industry', ''), row.get('list_date', ''), datetime.now()))
    
    def save_daily_data(self, daily_df):
        with self.get_connection() as conn:
            for _, row in daily_df.iterrows():
                conn.execute("INSERT OR REPLACE INTO daily_data (ts_code, trade_date, open, high, low, close, pre_close, change_pct, vol, amount) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
                (row['ts_code'], row['trade_date'], row['open'], row['high'], row['low'], row['close'], row['pre_close'], row['pct_chg'], row['vol'], row['amount']))
    
    def save_money_flow(self, flow_df):
        with self.get_connection() as conn:
            for _, row in flow_df.iterrows():
                inf = (row.get('buy_lg_amount', 0) + row.get('buy_elg_amount', 0) - row.get('sell_lg_amount', 0) - row.get('sell_elg_amount', 0))
                conn.execute("INSERT OR REPLACE INTO money_flow (ts_code, trade_date, buy_sm_amount, buy_md_amount, buy_lg_amount, buy_elg_amount, sell_sm_amount, sell_md_amount, sell_lg_amount, sell_elg_amount, net_mf_amount, main_net_inflow) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
                (row['ts_code'], row['trade_date'], 0,0,0,0,0,0,0,0, row.get('net_mf_amount', 0), inf))
    
    def get_stock_by_name(self, name):
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM stocks WHERE name LIKE ? LIMIT 20", (f'%{name}%',))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_stock_by_code(self, ts_code):
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM stocks WHERE ts_code = ?", (ts_code,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_daily_data(self, ts_code, days=300):
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM daily_data WHERE ts_code = ? ORDER BY trade_date DESC LIMIT ?", (ts_code, days))
            return [dict(row) for row in cursor.fetchall()]

    def get_money_flow(self, ts_code, days=30):
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM money_flow WHERE ts_code = ? ORDER BY trade_date DESC LIMIT ?", (ts_code, days))
            return [dict(row) for row in cursor.fetchall()]
    
    def add_to_watchlist(self, ts_code, name, add_price):
        with self.get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO watchlist (ts_code, name, add_price, add_date) VALUES (?, ?, ?, ?)", (ts_code, name, add_price, datetime.now().strftime('%Y-%m-%d')))
    
    def remove_from_watchlist(self, ts_code):
        with self.get_connection() as conn:
            conn.execute("DELETE FROM watchlist WHERE ts_code = ?", (ts_code,))
    
    def get_watchlist(self):
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM watchlist ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]
            
    def save_backtest_result(self, ts_code, start_date, end_date, results):
        with self.get_connection() as conn:
            conn.execute("INSERT INTO backtest_results (ts_code, start_date, end_date, total_signals, win_count, lose_count, win_rate, avg_return, max_return, max_loss) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
            (ts_code, start_date, end_date, results['total_signals'], results['win_count'], results['lose_count'], results['win_rate'], results['avg_return'], results['max_return'], results['max_loss']))
    
    def get_all_stocks(self):
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT ts_code, name FROM stocks ORDER BY ts_code")
            return [dict(row) for row in cursor.fetchall()]

    # --- 交易核心逻辑 (修复版：返回 PNL) ---
    
    def buy_stock(self, ts_code, name, qty, price, fee=0):
        with self.get_connection() as conn:
            trade_date = datetime.now().strftime('%Y-%m-%d')
            conn.execute("INSERT INTO trades (ts_code, name, direction, qty, price, fee, trade_date, created_at) VALUES (?, ?, 'BUY', ?, ?, ?, ?, ?)", (ts_code, name, qty, price, fee, trade_date, datetime.now()))
            
            cursor = conn.execute("SELECT * FROM positions WHERE ts_code = ?", (ts_code,))
            old_pos = cursor.fetchone()
            if old_pos:
                old_qty = old_pos['total_qty']
                old_cost = old_pos['cost_price']
                new_total = old_qty + qty
                new_cost = ((old_qty * old_cost) + (qty * price) + fee) / new_total if new_total > 0 else 0
                conn.execute("UPDATE positions SET total_qty=?, available_qty=available_qty+?, cost_price=?, last_update=? WHERE ts_code=?", (new_total, qty, new_cost, datetime.now(), ts_code))
            else:
                new_cost = (price * qty + fee) / qty if qty > 0 else 0
                conn.execute("INSERT INTO positions (ts_code, name, total_qty, available_qty, cost_price, realized_pnl, last_update) VALUES (?, ?, ?, ?, ?, 0, ?)", (ts_code, name, qty, qty, new_cost, datetime.now()))
                
    def sell_stock(self, ts_code, qty, price, fee=0):
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM positions WHERE ts_code = ?", (ts_code,))
            pos = cursor.fetchone()
            if not pos or pos['available_qty'] < qty:
                raise ValueError("持仓不足")
            
            # 计算盈亏 (核心)
            pnl = (price - pos['cost_price']) * qty - fee
            
            conn.execute("INSERT INTO trades (ts_code, name, direction, qty, price, fee, pnl, trade_date, created_at) VALUES (?, ?, 'SELL', ?, ?, ?, ?, ?, ?)", (ts_code, pos['name'], qty, price, fee, pnl, datetime.now().strftime('%Y-%m-%d'), datetime.now()))
            
            new_total = pos['total_qty'] - qty
            new_avail = pos['available_qty'] - qty
            new_cost = pos['cost_price'] if new_total > 0 else 0
            
            conn.execute("UPDATE positions SET total_qty=?, available_qty=?, cost_price=?, realized_pnl=realized_pnl+?, last_update=? WHERE ts_code=?", (new_total, new_avail, new_cost, pnl, datetime.now(), ts_code))
            
            if new_total == 0:
                conn.execute("UPDATE positions SET cost_price=0, market_value=0, float_pnl=0 WHERE ts_code=?", (ts_code,))
            
            return pnl # 返回盈亏金额

    def get_all_positions(self):
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM positions WHERE total_qty > 0 ORDER BY last_update DESC")
            return [dict(row) for row in cursor.fetchall()]
            
    def get_position_summary(self):
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM positions")
            all_pos = [dict(row) for row in cursor.fetchall()]
            realized_pnl = sum(p['realized_pnl'] for p in all_pos)
            return all_pos, realized_pnl

    def get_trade_history(self):
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM trades ORDER BY created_at DESC LIMIT 50")
            return [dict(row) for row in cursor.fetchall()]

    # ==================== V10新增：推荐准确率统计 ====================
    
    def save_recommendation(self, ts_code: str, name: str, price: float, score: float, 
                           rec_type: str, reason: str = ""):
        """保存推荐记录"""
        with self.get_connection() as conn:
            today = datetime.now().strftime('%Y-%m-%d')
            # 检查今日是否已推荐过该股票
            cursor = conn.execute(
                "SELECT id FROM recommendation_history WHERE ts_code=? AND recommend_date=?",
                (ts_code, today)
            )
            if cursor.fetchone():
                return False  # 今日已推荐
            
            conn.execute("""
                INSERT INTO recommendation_history 
                (ts_code, name, recommend_date, recommend_price, recommend_score, recommend_type, recommend_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (ts_code, name, today, price, score, rec_type, reason))
            return True
    
    def get_pending_recommendations(self, days_ago: int = 3):
        """获取N天前待验证的推荐"""
        with self.get_connection() as conn:
            target_date = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m-%d')
            cursor = conn.execute("""
                SELECT * FROM recommendation_history 
                WHERE result='pending' AND recommend_date <= ?
                ORDER BY recommend_date
            """, (target_date,))
            return [dict(row) for row in cursor.fetchall()]
    
    def verify_recommendation(self, rec_id: int, verify_price: float):
        """验证推荐结果"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT recommend_price FROM recommendation_history WHERE id=?", 
                (rec_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            
            recommend_price = row['recommend_price']
            profit_pct = (verify_price - recommend_price) / recommend_price * 100
            result = 'win' if profit_pct > 0 else 'lose'
            
            today = datetime.now().strftime('%Y-%m-%d')
            conn.execute("""
                UPDATE recommendation_history 
                SET verify_date=?, verify_price=?, profit_pct=?, result=?
                WHERE id=?
            """, (today, verify_price, profit_pct, result, rec_id))
            
            return {'profit_pct': profit_pct, 'result': result}
    
    def get_recommendation_stats(self, days: int = 30):
        """获取推荐统计数据"""
        with self.get_connection() as conn:
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            
            # 总体统计
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN result='lose' THEN 1 ELSE 0 END) as loses,
                    AVG(CASE WHEN result!='pending' THEN profit_pct ELSE NULL END) as avg_profit
                FROM recommendation_history
                WHERE recommend_date >= ?
            """, (start_date,))
            overall = dict(cursor.fetchone())
            
            # 按类型统计
            cursor = conn.execute("""
                SELECT 
                    recommend_type,
                    COUNT(*) as total,
                    SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
                    AVG(CASE WHEN result!='pending' THEN profit_pct ELSE NULL END) as avg_profit
                FROM recommendation_history
                WHERE recommend_date >= ? AND result != 'pending'
                GROUP BY recommend_type
            """, (start_date,))
            by_type = [dict(row) for row in cursor.fetchall()]
            
            return {
                'overall': overall,
                'by_type': by_type,
                'win_rate': (overall['wins'] / (overall['wins'] + overall['loses']) * 100) 
                           if (overall['wins'] or 0) + (overall['loses'] or 0) > 0 else 0
            }
    
    # ==================== V10新增：龙虎榜数据 ====================
    
    def save_dragon_tiger(self, ts_code: str, trade_date: str, reason: str,
                         buy_amount: float, sell_amount: float, 
                         top_buyers: str = "", top_sellers: str = ""):
        """保存龙虎榜数据"""
        with self.get_connection() as conn:
            net_amount = buy_amount - sell_amount
            conn.execute("""
                INSERT OR REPLACE INTO dragon_tiger 
                (ts_code, trade_date, reason, buy_amount, sell_amount, net_amount, top_buyers, top_sellers)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (ts_code, trade_date, reason, buy_amount, sell_amount, net_amount, top_buyers, top_sellers))
    
    def get_dragon_tiger_by_date(self, trade_date: str):
        """获取某日龙虎榜"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM dragon_tiger WHERE trade_date=? ORDER BY net_amount DESC",
                (trade_date,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_stock_dragon_tiger(self, ts_code: str, days: int = 30):
        """获取某股票龙虎榜历史"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM dragon_tiger WHERE ts_code=? ORDER BY trade_date DESC LIMIT ?",
                (ts_code, days)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    # ==================== V10新增：融资融券数据 ====================
    
    def save_margin_data(self, ts_code: str, trade_date: str, rzye: float, 
                        rzmre: float, rzche: float, rqye: float, 
                        rqmcl: float, rzrqye: float):
        """保存融资融券数据"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO margin_data 
                (ts_code, trade_date, rzye, rzmre, rzche, rqye, rqmcl, rzrqye)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (ts_code, trade_date, rzye, rzmre, rzche, rqye, rqmcl, rzrqye))
    
    def get_margin_data(self, ts_code: str, days: int = 30):
        """获取融资融券数据"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM margin_data WHERE ts_code=? ORDER BY trade_date DESC LIMIT ?",
                (ts_code, days)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    # ==================== V10新增：板块联动数据 ====================
    
    def save_sector_linkage(self, trade_date: str, sector_name: str, sector_pct: float,
                           leader_code: str, leader_name: str, leader_pct: float,
                           follower_count: int):
        """保存板块联动数据"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO sector_linkage 
                (trade_date, sector_name, sector_pct, leader_code, leader_name, leader_pct, follower_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (trade_date, sector_name, sector_pct, leader_code, leader_name, leader_pct, follower_count))
    
    def get_sector_linkage(self, trade_date: str):
        """获取某日板块联动"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM sector_linkage WHERE trade_date=? ORDER BY sector_pct DESC",
                (trade_date,)
            )
            return [dict(row) for row in cursor.fetchall()]

