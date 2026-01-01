from core.factor_engine import FactorEngine

# V10 Ultra Pro: 否决机制
try:
    from core.decision_core import DecisionCore, Priority, Signal
    VETO_ENABLED = True
except:
    VETO_ENABLED = False
    DecisionCore = None


class ScoringEngine:
    """
    V10 Ultra Pro 评分引擎
    
    修复：不再仅靠加权求和决定买入
    新增：否决机制 - 高危因子一票否决
    """
    def __init__(self, config):
        self.config = config
        self.weights = config['scoring_weights']
        self.factor_engine = FactorEngine(config)
        
        # V10新增：否决阈值
        self.veto_thresholds = {
            'fund_outflow_max': -2000,   # 资金流出超2000万否决
            'buy_sell_ratio_min': 0.5,   # 买卖力量比低于0.5否决
        }
    
    def _check_veto_conditions(self, money_flow_data: list) -> tuple:
        """
        检查否决条件
        
        Returns:
            (是否否决, 否决原因列表)
        """
        if not money_flow_data:
            return False, []
        
        veto = False
        reasons = []
        
        main_flow = money_flow_data[0].get('main_net_inflow', 0) or 0
        
        # 资金大幅流出否决
        if main_flow < self.veto_thresholds['fund_outflow_max']:
            veto = True
            reasons.append(f"主力净流出{abs(main_flow):.0f}万")
        
        return veto, reasons
    
    def generate_decision(self, ts_code, stock_info, daily_data, money_flow_data, market_data):
        trend_score, _ = self.factor_engine.calculate_trend_score(daily_data)
        volume_score, _ = self.factor_engine.calculate_volume_score(daily_data)
        position_score, _ = self.factor_engine.calculate_position_score(daily_data)
        market_sync_score, _ = self.factor_engine.calculate_market_sync_score(daily_data, market_data)
        theme_score, _ = self.factor_engine.calculate_theme_heat_score(money_flow_data)
        
        is_fake_drop, _ = self.factor_engine.detect_fake_drop(daily_data, money_flow_data)
        has_main_force, main_force_days = self.factor_engine.check_consecutive_main_force(money_flow_data)
        
        weighted_score = (trend_score * 0.4 + volume_score * 0.25 + position_score * 0.2 + market_sync_score * 0.1 + theme_score * 0.05)
        
        # ====== V10新增：否决机制 ======
        is_vetoed, veto_reasons = self._check_veto_conditions(money_flow_data)
        
        action = "观望"
        action_class = "watch"
        
        # V10优化：提高准确性
        # 1. GO阈值提高到80（原75）
        # 2. 要求趋势因子为正
        # 3. RUN阈值降低到40（原45）
        trend_positive = trend_score >= 55  # 趋势因子需要正向
        
        if is_vetoed:
            # 被否决：无论评分多高都不能看多
            action = "⚠️ 被否决"
            action_class = "run" if veto_reasons and "流出" in veto_reasons[0] else "watch"
        elif weighted_score >= 80 and trend_positive:
            # V10：提高阈值 + 要求趋势确认
            action = "搞！"
            action_class = "go"
        elif weighted_score >= 70 and trend_positive:
            # 中等分数但趋势正向 → 谨慎看多
            action = "可关注"
            action_class = "watch"
        elif weighted_score <= 40:
            # V10：降低RUN阈值
            action = "跑！"
            action_class = "run"
        
        explanation = ""
        if is_vetoed:
            explanation = f"否决因子：{'、'.join(veto_reasons)}"
        
        # 资金判断（单位：万元）
        main_inflow_text = "资金平淡"
        if len(money_flow_data) > 0:
            inflow = money_flow_data[0].get('main_net_inflow', 0) or 0
            if inflow > 1000: main_inflow_text = f"🔥 主力大买 {int(inflow)}万"
            elif inflow > 0: main_inflow_text = f"🔴 小幅流入 {int(inflow)}万"
            else: main_inflow_text = f"💚 主力流出 {int(abs(inflow))}万"

        return {
            'action': action, 
            'action_class': action_class, 
            'score': round(weighted_score, 0),
            'is_vetoed': is_vetoed,           # V10新增
            'veto_reasons': veto_reasons,     # V10新增
            'explanation': explanation, 
            'main_inflow_text': main_inflow_text,
            'thunder_alert': False,
            'details': {
                'trend': {'score': trend_score}, 
                'volume': {'score': volume_score}, 
                'position': {'score': position_score}, 
                'theme': {'score': theme_score}
            }
        }
