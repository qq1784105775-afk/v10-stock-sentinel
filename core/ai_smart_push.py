# -*- coding: utf-8 -*-
"""
V10新增：AI智能推送模块
======================
让推送机器人更智能、更有价值

功能：
1. 智能早盘播报
2. 智能持仓诊断
3. 智能复盘总结
4. 智能选股推荐

V10规则（阶段3）：
- AI文案必须绑定decision_core结果
- 禁止输出与决策矛盾的文案
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# V10新增：禁止的乐观词汇（当decision=AVOID时不能出现）
FORBIDDEN_BULLISH_WORDS = [
    '主升浪', '闭眼买', '抄底', '强势拉升', '涨停板', '坐等抬轿',
    '黄金坑', '铁底', '满仓干', '牛股', '龙头', '起飞'
]

# V10新增：允许的观望词汇
ALLOWED_HOLD_WORDS = [
    '观望', '等待确认', '谨慎', '注意风险', '控制仓位', '精选'
]


class AISmartPush:
    """AI智能推送器"""
    
    def __init__(self, db, api_base: str = "http://127.0.0.1:9000"):
        """
        初始化
        
        Args:
            db: DatabaseManager实例
            api_base: API基础地址
        """
        self.db = db
        self.api_base = api_base
    
    def _filter_text_by_decision(self, text: str, decision: str) -> str:
        """
        V10新增：根据decision过滤文案
        
        规则（阶段3.1）：
        - decision == AVOID: 禁止乐观词汇
        - decision == HOLD: 只能观望词汇
        - decision == BUY: 允许乐观表述
        """
        if not decision:
            return text
        
        decision = decision.upper()
        
        if decision == 'AVOID' or decision == 'RUN':
            # 禁止所有乐观词汇
            for word in FORBIDDEN_BULLISH_WORDS:
                if word in text:
                    text = text.replace(word, f'[风险警告]')
            # 添加风险前缀
            if not text.startswith('⚠️'):
                text = f'⚠️ {text}'
        
        elif decision == 'HOLD' or decision == 'WATCH':
            # 替换过度乐观词汇为观望
            for word in FORBIDDEN_BULLISH_WORDS:
                if word in text:
                    text = text.replace(word, '观望为主')
        
        return text
    
    # ==================== 智能早盘播报 ====================
    
    def generate_morning_report(self, market_status: Dict, sentiment: Dict,
                                hot_sectors: List = None) -> str:
        """
        生成智能早盘播报
        
        Args:
            market_status: 市场状态数据
            sentiment: 市场情绪数据
            hot_sectors: 热门板块
            
        Returns:
            早盘播报文本
        """
        now = datetime.now()
        today = now.strftime('%m月%d日')
        
        # 大盘信息
        index_point = market_status.get('index_point', 0)
        index_change = market_status.get('index_change', 0)
        index_emoji = '📈' if index_change > 0 else ('📉' if index_change < 0 else '➡️')
        
        # 情绪信息
        limit_up = sentiment.get('limit_up', 0)
        limit_down = sentiment.get('limit_down', 0)
        sentiment_score = sentiment.get('sentiment_score', 50)
        sentiment_text = sentiment.get('sentiment_text', '中性')
        
        # 北向资金
        north = market_status.get('north_money', 0)
        if isinstance(north, dict):
            north = north.get('hgt', 0) + north.get('sgt', 0)
        north_text = f"+{north/100:.1f}亿" if north > 0 else f"{north/100:.1f}亿"
        north_emoji = '🔴' if north > 0 else '🟢'
        
        # 热门板块
        if hot_sectors:
            top3_sectors = hot_sectors[:3]
            sector_text = "、".join([s.get('sector_name', '')[:4] for s in top3_sectors])
        else:
            sector_text = market_status.get('hot_sector', '暂无')
        
        # 生成策略建议
        strategy = self._generate_strategy_suggestion(sentiment_score, index_change, north)
        
        # 组装播报
        lines = [
            f"🌅 {today} 早盘播报",
            "",
            f"📊 大盘：{index_point:.0f}点 {index_emoji}{index_change:+.2f}%",
            f"🌡️ 情绪：{sentiment_text}（{sentiment_score}分）",
            f"🔢 涨停{limit_up}家 / 跌停{limit_down}家",
            f"{north_emoji} 北向：{north_text}",
            f"🔥 热点：{sector_text}",
            "",
            f"💡 今日策略",
            strategy
        ]
        
        return "\n".join(lines)
    
    def _generate_strategy_suggestion(self, sentiment: int, index_change: float, 
                                      north: float) -> str:
        """
        生成策略建议
        
        V10规则：禁止在市场偏弱时输出乐观建议
        """
        suggestions = []
        
        # 根据情绪判断（V10：保守策略）
        if sentiment >= 80:
            suggestions.append("市场极度亢奋，注意追高风险")
            suggestions.append("可适当减仓锁利")
        elif sentiment >= 65:
            suggestions.append("市场偏多，可关注强势股")
            suggestions.append("控制仓位，设好止盈")
        elif sentiment >= 45:
            suggestions.append("市场震荡，观望为主")
            suggestions.append("控制仓位，精选个股")
        elif sentiment >= 30:
            suggestions.append("市场偏弱，谨慎操作")
            suggestions.append("持币观望为主")
        else:
            # V10修正：恐慌市场不再建议抄底
            suggestions.append("市场恐慌，风险极高")
            suggestions.append("空仓观望，不要抄底")
        
        # 根据北向资金
        if north > 5000:  # 50亿以上
            suggestions.append("外资大举买入，跟随布局")
        elif north < -5000:
            suggestions.append("外资流出，需警惕风险")
        
        return "\n".join([f"  • {s}" for s in suggestions[:2]])
    
    # ==================== 智能持仓诊断 ====================
    
    def generate_position_diagnosis(self, positions: List[Dict], 
                                    stock_analysis: Dict = None) -> str:
        """
        生成智能持仓诊断报告
        
        Args:
            positions: 持仓列表，每个包含 {ts_code, name, cost_price, qty, current_price, score, decision}
            stock_analysis: 股票分析数据字典
            
        Returns:
            诊断报告文本
        """
        if not positions:
            return "💼 持仓诊断\n\n暂无持仓"
        
        lines = ["💼 持仓诊断报告", ""]
        
        total_value = 0
        total_pnl = 0
        
        for pos in positions:
            ts_code = pos.get('ts_code', '')
            name = pos.get('name', '')
            cost = pos.get('cost_price', 0)
            qty = pos.get('total_qty', 0)
            current = pos.get('current_price', cost)
            score = pos.get('score', 50)
            decision = pos.get('decision', '观察')
            
            # 计算盈亏
            pnl = (current - cost) * qty
            pnl_pct = (current - cost) / cost * 100 if cost > 0 else 0
            value = current * qty
            
            total_value += value
            total_pnl += pnl
            
            # 盈亏emoji
            pnl_emoji = '🟢' if pnl > 0 else ('🔴' if pnl < 0 else '⚪')
            
            # 评分判断
            if score >= 75:
                status = '✅ 强势'
                suggestion = '持有待涨'
            elif score >= 60:
                status = '📈 健康'
                suggestion = '继续持有'
            elif score >= 45:
                status = '⚖️ 一般'
                suggestion = '观察为主'
            else:
                status = '⚠️ 走弱'
                suggestion = '考虑减仓'
            
            lines.append(f"{pnl_emoji} {name} | {status}")
            lines.append(f"   成本{cost:.2f} → 现价{current:.2f} ({pnl_pct:+.1f}%)")
            lines.append(f"   评分{score:.0f}分 | {decision}")
            lines.append(f"   👉 {suggestion}")
            lines.append("")
        
        # 汇总
        pnl_emoji = '🟢' if total_pnl > 0 else ('🔴' if total_pnl < 0 else '⚪')
        lines.append("━━━━━━━━━━━━━━")
        lines.append(f"💰 总市值：{total_value:.0f}元")
        lines.append(f"{pnl_emoji} 总浮盈：{total_pnl:+.0f}元")
        
        return "\n".join(lines)
    
    # ==================== 智能复盘总结 ====================
    
    def generate_daily_review(self, recommendation_stats: Dict,
                              market_summary: Dict = None,
                              trade_summary: Dict = None) -> str:
        """
        生成智能复盘总结
        
        Args:
            recommendation_stats: 推荐统计数据
            market_summary: 市场总结
            trade_summary: 交易总结
            
        Returns:
            复盘报告文本
        """
        today = datetime.now().strftime('%m月%d日')
        
        lines = [f"📈 {today} 复盘总结", ""]
        
        # 推荐回顾
        lines.append("📋 推荐回顾")
        overall = recommendation_stats.get('overall', {})
        total = overall.get('total', 0)
        wins = overall.get('wins', 0) or 0
        loses = overall.get('loses', 0) or 0
        avg_profit = overall.get('avg_profit', 0) or 0
        
        if total > 0:
            verified = wins + loses
            win_rate = wins / verified * 100 if verified > 0 else 0
            lines.append(f"  • 总推荐：{total}只")
            lines.append(f"  • 已验证：{verified}只")
            lines.append(f"  • 胜率：{win_rate:.1f}%")
            lines.append(f"  • 平均收益：{avg_profit:+.2f}%")
        else:
            lines.append("  • 暂无推荐数据")
        
        lines.append("")
        
        # 各策略表现
        by_type = recommendation_stats.get('by_type', [])
        if by_type:
            lines.append("📊 策略表现")
            for item in by_type[:5]:
                rec_type = item.get('recommend_type', '')
                type_wins = item.get('wins', 0) or 0
                type_total = item.get('total', 0) or 1
                type_profit = item.get('avg_profit', 0) or 0
                type_rate = type_wins / type_total * 100 if type_total > 0 else 0
                
                # 翻译策略类型
                type_name = {
                    'main_wave': '主升浪',
                    'rebound': '超跌反弹',
                    'golden': '黄金启动',
                    'wash': '洗盘'
                }.get(rec_type, rec_type)
                
                lines.append(f"  • {type_name}：胜率{type_rate:.0f}% 收益{type_profit:+.1f}%")
            lines.append("")
        
        # 市场总结
        if market_summary:
            lines.append("🌍 市场规律")
            hot_sectors = market_summary.get('hot_sectors', [])
            if hot_sectors:
                lines.append(f"  • 热门板块：{', '.join(hot_sectors[:3])}")
            lines.append("")
        
        # 明日展望
        lines.append("🔮 明日展望")
        if avg_profit > 2:
            lines.append("  • 策略表现优秀，继续执行")
        elif avg_profit > 0:
            lines.append("  • 策略表现正常，可继续使用")
        else:
            lines.append("  • 策略需优化，建议谨慎")
        
        return "\n".join(lines)
    
    # ==================== 智能选股推荐 ====================
    
    def generate_smart_recommendation(self, candidates: List[Dict],
                                      market_sentiment: int = 50) -> str:
        """
        生成智能选股推荐
        
        Args:
            candidates: 候选股票列表
            market_sentiment: 市场情绪分
            
        Returns:
            推荐文本
        """
        if not candidates:
            return "🎯 今日推荐\n\n暂无符合条件的股票"
        
        lines = ["🎯 今日精选推荐", ""]
        
        # 根据情绪调整推荐数量
        if market_sentiment >= 70:
            max_picks = 5
            lines.append("📈 市场活跃，可积极参与")
        elif market_sentiment >= 50:
            max_picks = 3
            lines.append("⚖️ 市场平稳，精选操作")
        else:
            max_picks = 2
            lines.append("📉 市场偏弱，严格筛选")
        
        lines.append("")
        
        # 按评分排序
        sorted_candidates = sorted(candidates, key=lambda x: x.get('score', 0), reverse=True)
        
        for i, stock in enumerate(sorted_candidates[:max_picks]):
            name = stock.get('name', '')
            ts_code = stock.get('ts_code', '')
            score = stock.get('score', 0)
            price = stock.get('price', 0)
            reason = stock.get('reason', '')
            rec_type = stock.get('type', '')
            
            # 翻译类型
            type_emoji = {
                'main_wave': '🚀',
                'rebound': '💎',
                'golden': '🌟',
                'wash': '🛁'
            }.get(rec_type, '📌')
            
            type_name = {
                'main_wave': '主升浪',
                'rebound': '超跌反弹',
                'golden': '黄金启动',
                'wash': '洗盘'
            }.get(rec_type, '推荐')
            
            lines.append(f"{type_emoji} {name}（{ts_code[:6]}）")
            lines.append(f"   评分：{score:.0f}分 | 现价：{price:.2f}")
            lines.append(f"   类型：{type_name}")
            if reason:
                lines.append(f"   理由：{reason[:30]}...")
            lines.append("")
        
        # 风险提示
        lines.append("⚠️ 风险提示")
        lines.append("  • 以上仅供参考，不构成投资建议")
        lines.append("  • 投资有风险，入市需谨慎")
        
        return "\n".join(lines)
    
    # ==================== 异动播报 ====================
    
    def generate_alert_message(self, alert_type: str, stock: Dict, 
                               extra_info: Dict = None) -> str:
        """
        生成异动播报消息
        
        Args:
            alert_type: 异动类型 (limit_up/limit_down/surge/plunge/golden_pit/trap)
            stock: 股票信息
            extra_info: 额外信息
            
        Returns:
            播报文本
        """
        name = stock.get('name', '')
        ts_code = stock.get('ts_code', '')
        price = stock.get('price', 0)
        pct = stock.get('pct_change', 0)
        score = stock.get('score', 50)
        
        templates = {
            'limit_up': {
                'emoji': '🚀',
                'title': '涨停播报',
                'action': '封涨停板',
                'suggestion': '注意明日高开风险，勿盲目追高'
            },
            'limit_down': {
                'emoji': '💀',
                'title': '跌停警报',
                'action': '封跌停板',
                'suggestion': '注意风险，切勿抄底'
            },
            'surge': {
                'emoji': '📈',
                'title': '异动拉升',
                'action': f'快速拉升{pct:.1f}%',
                'suggestion': '关注成交量变化'
            },
            'plunge': {
                'emoji': '📉',
                'title': '异动下跌',
                'action': f'快速下跌{abs(pct):.1f}%',
                'suggestion': '注意风险控制'
            },
            'golden_pit': {
                'emoji': '💎',
                'title': '黄金坑机会',
                'action': '下跌中有资金抢筹',
                'suggestion': '可能是洗盘，关注后续走势'
            },
            'trap': {
                'emoji': '⚠️',
                'title': '诱多警告',
                'action': '上涨中资金流出',
                'suggestion': '可能是出货陷阱，谨慎'
            }
        }
        
        template = templates.get(alert_type, templates['surge'])
        
        lines = [
            f"{template['emoji']} {name} {template['title']}",
            "",
            f"💵 现价：{price:.2f} ({pct:+.1f}%)",
            f"⭐ 评分：{score:.0f}分",
            f"📌 动态：{template['action']}",
            "",
            f"💡 建议：{template['suggestion']}"
        ]
        
        # 添加额外信息
        if extra_info:
            if extra_info.get('rush_ratio'):
                lines.append(f"🔢 抢筹比：{extra_info['rush_ratio']:.1f}倍")
            if extra_info.get('main_inflow'):
                inflow = extra_info['main_inflow']
                lines.append(f"💰 主力：{'+' if inflow > 0 else ''}{inflow:.0f}万")
        
        return "\n".join(lines)


# 工厂函数
def create_ai_push(db) -> AISmartPush:
    """创建AI智能推送器"""
    return AISmartPush(db)
