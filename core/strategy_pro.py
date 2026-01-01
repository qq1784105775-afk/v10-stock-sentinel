# -*- coding: utf-8 -*-
"""
V9 策略引擎 (融合版)
=====================
融合了两个版本的优点：
1. 旧版本的 analyze() 三合一策略（主升浪/超跌反转/黄金启动）
2. 新版本的 analyze_intent() 五维意图分析
"""

class StrategyPro:
    def __init__(self):
        pass

    # ============================================
    # 旧版本的三合一策略（用于智能选股 /api/recommend）
    # ============================================
    def analyze(self, pack):
        """
        三合一策略逻辑 - 用于选股推荐
        
        参数 pack 包含:
        - win_rate: 获利盘比例 (0-100)
        - score: 基础评分 (0-100)
        - change: 涨跌幅 (%)
        - net_flow: 主力净流入 (可选)
        
        返回: (是否匹配, 策略类型, 理由, 调整后评分)
        """
        win_rate = pack.get('win_rate', 0)
        score = pack.get('score', 60)
        change = pack.get('change', 0)
        net_flow = pack.get('net_flow', 0)
        
        # --- 1. 红色：主升浪 (Main Wave) ---
        # 逻辑：大家都赚钱(>85%) + 趋势良好(>65分)
        if win_rate >= 85 and score >= 65:
            return True, "main_wave", f"🚀 主升浪：获利盘{win_rate:.0f}%，主力完全控盘", score + 10

        # --- 2. 蓝色：超跌反转 (Rebound) ---
        # 修复：条件收紧到10%，且需要评分及格
        # 资金流单位：万元（Tushare moneyflow接口返回万元）
        if win_rate <= 10 and change > -9.5 and score >= 45:
            if net_flow > 1000:  # 提高抄底门槛到1000万（单位：万元）
                return True, "rebound", f"💎 黄金坑：获利盘仅{win_rate:.0f}%，主力抄底中", score + 15
            elif net_flow > 0:
                return True, "rebound", f"💎 超跌反转：获利盘仅{win_rate:.0f}%，博反弹", score + 5

        # --- 3. 黄色：黄金启动 (Golden) ---
        # 修复：评分要求提高到60分
        if 40 <= win_rate < 85 and score >= 60:
            return True, "golden", f"🌟 黄金启动：筹码稳定{win_rate:.0f}%", score

        # --- 4. 洗盘识别 ---
        # 高获利盘 + 低评分 + 资金流入 = 洗盘（修复：阈值单位改为万元）
        if win_rate >= 80 and score < 55 and net_flow > 500:  # 500万元
            return True, "wash", f"🛁 主力洗盘：获利盘{win_rate:.0f}%但资金逆势流入", score + 5

        # 其他区间不推荐
        return False, "none", "", 0

    # ============================================
    # 你昨天新增的五维意图分析（用于详情页展示）
    # ============================================
    def analyze_intent(self, score, flow_msg, chip_msg, pct_chg, tech_signal):
        """
        五维意图分析 - 用于股票详情页
        
        参数:
        - score: 综合评分
        - flow_msg: 资金信号 ("正常"/"诱多"/"挖坑")
        - chip_msg: 筹码信号 ("正常"/"高危")
        - pct_chg: 涨跌幅
        - tech_signal: 技术信号 ("触底"/"触顶"/"超买"/"超卖"/"金叉"/"普通")
        
        返回: 意图描述字符串
        """
        # 技术信号优先
        if "触底" in tech_signal:
            return "💎铁底回补"
        if "触顶" in tech_signal:
            return "⚠️触顶回落"
        if "超买" in tech_signal:
            return "⚠️顶部风险"
        if "超卖" in tech_signal:
            return "💎黄金坑"
        
        # 资金信号
        if "诱多" in flow_msg:
            return "⚠️诱多出货"
        if "挖坑" in flow_msg:
            return "💎主力挖坑"
        
        # 筹码信号
        if "高危" in chip_msg:
            return "💣高位派发"
        
        # 趋势信号
        if "金叉" in tech_signal and score > 65:
            return "🚀趋势加速"
        
        # 评分信号
        if score > 85:
            return "🚀主升浪"
        if score > 70:
            return "✨强势拉升"
        if score < 35:
            return "🌧破位下跌"
        
        # 洗盘识别
        if 50 < score < 75 and -5 < pct_chg < 0:
            return "🛁主力洗盘"
        
        return "☁️观察等待"

    # ============================================
    # 综合分析（新增：结合两种方法）
    # ============================================
    def full_analyze(self, pack, flow_msg="正常", chip_msg="正常", tech_signal="普通"):
        """
        综合分析 - 同时运行三合一策略和五维意图分析
        
        返回: {
            'match': bool,          # 是否匹配三合一策略
            'strategy_type': str,   # 策略类型
            'reason': str,          # 策略理由
            'score': float,         # 调整后评分
            'intent': str           # 五维意图
        }
        """
        # 三合一策略
        is_match, s_type, reason, adj_score = self.analyze(pack)
        
        # 五维意图
        intent = self.analyze_intent(
            pack.get('score', 60),
            flow_msg,
            chip_msg,
            pack.get('change', 0),
            tech_signal
        )
        
        return {
            'match': is_match,
            'strategy_type': s_type,
            'reason': reason,
            'score': adj_score,
            'intent': intent
        }
