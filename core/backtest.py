from datetime import datetime, timedelta
from core.scoring_engine import ScoringEngine

# V10 Ultra Pro: 统一信号生成逻辑
try:
    from core.decision_core import DecisionCore, Priority, Signal
    from core.factor_engine_v9 import calculate_v9_score
    UNIFIED_SIGNAL_ENABLED = True
except:
    UNIFIED_SIGNAL_ENABLED = False
    DecisionCore = None


class BacktestEngine:
    """
    V10 Ultra Pro 回测引擎
    
    修复：与实盘使用相同的信号逻辑（DecisionCore）
    """
    def __init__(self, config, db_manager):
        self.config = config
        self.db = db_manager
        self.scoring_engine = ScoringEngine(config)
    
    def _generate_unified_signal(self, decision: dict, main_net_flow: float) -> tuple:
        """
        使用DecisionCore生成统一信号
        
        与实盘逻辑一致，返回 (是否买入, 原因)
        """
        if not UNIFIED_SIGNAL_ENABLED or not DecisionCore:
            # 降级到旧逻辑
            return decision['action'] in ['搞！', '假摔敢买！'], decision['action']
        
        core = DecisionCore()
        score = decision.get('score', 50)
        
        # P2: 资金流
        if main_net_flow < -2000:
            core.add_judgment(Priority.P2_REALTIME_FUND, Signal.SELL,
                            f"主力净流出{abs(main_net_flow):.0f}万", 0.8, "fund")
        elif main_net_flow > 2000:
            core.add_judgment(Priority.P2_REALTIME_FUND, Signal.BUY,
                            f"主力净流入{main_net_flow:.0f}万", 0.7, "fund")
        
        # P3: 评分
        if score >= 70:
            core.add_judgment(Priority.P3_TREND_CHIP, Signal.BUY,
                            f"评分{score:.0f}", 0.6, "score")
        elif score <= 35:
            core.add_judgment(Priority.P3_TREND_CHIP, Signal.SELL,
                            f"评分{score:.0f}", 0.6, "score")
        
        verdict = core.make_verdict()
        
        # 只有未被否决且是看多信号才买入
        is_buy = not verdict.is_vetoed and verdict.action_class == 'go'
        return is_buy, verdict.primary_reason
    
    def run_backtest(self, ts_code, years=10):
        end_date = datetime.now()
        start_date = end_date - timedelta(days=years*365)
        
        start_str = start_date.strftime('%Y%m%d')
        end_str = end_date.strftime('%Y%m%d')
        
        daily_data = self.db.get_daily_data(ts_code, days=years*365)
        money_flow_data = self.db.get_money_flow(ts_code, days=years*365)
        
        if len(daily_data) < 100:
            return {
                'success': False,
                'message': '历史数据不足，无法回测'
            }
        
        market_data = self.db.get_daily_data('000001.SH', days=years*365)
        
        signals = []
        for i in range(60, len(daily_data)):
            historical_daily = daily_data[:i+1]
            historical_flow = [f for f in money_flow_data if f['trade_date'] <= daily_data[i]['trade_date']]
            
            if len(historical_flow) < 3:
                continue
            
            stock_info = self.db.get_stock_by_code(ts_code)
            
            decision = self.scoring_engine.generate_decision(
                ts_code, stock_info, historical_daily, 
                historical_flow[:30], market_data[:i+1]
            )
            
            # V10修复：使用统一信号逻辑
            main_flow = historical_flow[0].get('main_net_inflow', 0) if historical_flow else 0
            is_buy, reason = self._generate_unified_signal(decision, main_flow)
            
            if is_buy:

                signals.append({
                    'date': daily_data[i]['trade_date'],
                    'action': decision['action'],
                    'price': daily_data[i]['close'],
                    'score': decision['score']
                })
        
        if len(signals) == 0:
            return {
                'success': False,
                'message': '回测期间未产生任何买入信号'
            }
        
        trades = []
        for signal in signals:
            entry_price = signal['price']
            entry_date = signal['date']
            
            hold_days = 0
            exit_price = None
            exit_date = None
            
            signal_idx = next(i for i, d in enumerate(daily_data) if d['trade_date'] == entry_date)
            
            for j in range(signal_idx-1, max(signal_idx-21, -1), -1):
                hold_days += 1
                future_data = daily_data[j]
                
                change_from_entry = (future_data['close'] - entry_price) / entry_price * 100
                
                if change_from_entry >= 8 or change_from_entry <= -5 or hold_days >= 20:
                    exit_price = future_data['close']
                    exit_date = future_data['trade_date']
                    break
            
            if exit_price:
                profit_pct = (exit_price - entry_price) / entry_price * 100
                trades.append({
                    'entry_date': entry_date,
                    'entry_price': entry_price,
                    'exit_date': exit_date,
                    'exit_price': exit_price,
                    'hold_days': hold_days,
                    'profit_pct': profit_pct,
                    'result': 'win' if profit_pct > 0 else 'lose'
                })
        
        if len(trades) == 0:
            return {
                'success': False,
                'message': '无完整交易记录'
            }
        
        total_signals = len(signals)
        win_count = sum(1 for t in trades if t['result'] == 'win')
        lose_count = sum(1 for t in trades if t['result'] == 'lose')
        win_rate = win_count / len(trades) * 100 if len(trades) > 0 else 0
        
        avg_return = sum(t['profit_pct'] for t in trades) / len(trades)
        max_return = max(t['profit_pct'] for t in trades)
        max_loss = min(t['profit_pct'] for t in trades)
        
        avg_hold_days = sum(t['hold_days'] for t in trades) / len(trades)
        
        result = {
            'success': True,
            'total_signals': total_signals,
            'completed_trades': len(trades),
            'win_count': win_count,
            'lose_count': lose_count,
            'win_rate': round(win_rate, 2),
            'avg_return': round(avg_return, 2),
            'max_return': round(max_return, 2),
            'max_loss': round(max_loss, 2),
            'avg_hold_days': round(avg_hold_days, 1),
            'trades': trades[-20:]
        }
        
        self.db.save_backtest_result(
            ts_code, start_str, end_str, result
        )
        
        return result
