# -*- coding: utf-8 -*-
"""
V10 Ultra Pro：统一交易主裁 (Decision Core)
============================================
所有策略、评分、风控必须输出到这里
禁止策略模块直接返回 BUY / SELL

优先级体系（P0-P4）：
P0：账户级/资金级风控（否决权）
P1：市场状态/情绪极端
P2：实时资金方向
P3：趋势/筹码/成本
P4：AI文案/解读

规则：P0~P2 任意触发 → P3/P4 禁止输出"买入叙事"
"""

from typing import Dict, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass
from datetime import datetime


class Priority(Enum):
    """优先级枚举"""
    P0_ACCOUNT_RISK = 0      # 账户级风控（最高，一票否决）
    P1_MARKET_EXTREME = 1    # 市场极端状态
    P2_REALTIME_FUND = 2     # 实时资金方向
    P3_TREND_CHIP = 3        # 趋势/筹码
    P4_AI_NARRATIVE = 4      # AI文案


class Signal(Enum):
    """信号类型"""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    REDUCE = "reduce"
    SELL = "sell"
    STRONG_SELL = "strong_sell"
    VETO = "veto"  # 一票否决


@dataclass
class JudgmentInput:
    """裁决输入"""
    priority: Priority
    signal: Signal
    reason: str
    confidence: float = 0.5  # 0-1
    source: str = ""  # 来源模块


@dataclass
class FinalVerdict:
    """最终裁决"""
    action: str                    # 最终动作
    action_class: str             # go/watch/run
    confidence: float             # 置信度
    primary_reason: str           # 主要原因
    veto_reasons: List[str]       # 否决原因列表
    all_inputs: List[Dict]        # 所有输入
    timestamp: datetime           # 裁决时间
    is_vetoed: bool              # 是否被否决


class DecisionCore:
    """统一交易主裁"""
    
    # ====== 一票否决条件 ======
    VETO_CONDITIONS = {
        'main_outflow_threshold': -2000,   # 主力净流出超2000万
        'buy_sell_ratio_min': 0.5,          # 买卖力量比最低
        'fund_trend_veto': ['大幅流出', '巨额流出', '持续流出'],
        'market_extreme_sell': ['极度恐慌', '熔断风险', '系统性风险'],
        'max_drawdown': 0.15,               # 最大回撤15%
        'consecutive_loss_max': 3,          # 连续亏损次数
    }
    
    # ====== 禁止的矛盾文案 ======
    FORBIDDEN_COMBOS = [
        ('闭眼买', '主力出货'),
        ('主升浪', '资金撤离'),
        ('强势', '大幅流出'),
        ('买入', '风险极高'),
    ]
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.judgments: List[JudgmentInput] = []
        self.veto_active = False
        self.veto_reasons = []
        
    def reset(self):
        """重置裁决状态"""
        self.judgments = []
        self.veto_active = False
        self.veto_reasons = []
    
    def add_judgment(self, 
                     priority: Priority,
                     signal: Signal,
                     reason: str,
                     confidence: float = 0.5,
                     source: str = "") -> None:
        """
        添加裁决输入
        
        Args:
            priority: 优先级
            signal: 信号类型
            reason: 原因
            confidence: 置信度
            source: 来源模块
        """
        judgment = JudgmentInput(
            priority=priority,
            signal=signal,
            reason=reason,
            confidence=confidence,
            source=source
        )
        self.judgments.append(judgment)
        
        # 检查是否触发一票否决
        if priority in [Priority.P0_ACCOUNT_RISK, Priority.P1_MARKET_EXTREME, Priority.P2_REALTIME_FUND]:
            if signal in [Signal.SELL, Signal.STRONG_SELL, Signal.VETO]:
                self.veto_active = True
                self.veto_reasons.append(f"[{priority.name}] {reason}")
    
    def check_veto_conditions(self,
                              main_net_flow: float = 0,
                              buy_sell_ratio: float = 1.0,
                              fund_trend: str = "",
                              market_sentiment: str = "",
                              account_drawdown: float = 0,
                              consecutive_losses: int = 0) -> Tuple[bool, List[str]]:
        """
        检查一票否决条件
        
        Returns:
            (是否触发否决, 否决原因列表)
        """
        veto = False
        reasons = []
        
        # P0: 账户级风控
        if account_drawdown >= self.VETO_CONDITIONS['max_drawdown']:
            veto = True
            reasons.append(f"账户回撤{account_drawdown*100:.1f}%，超过阈值")
            
        if consecutive_losses >= self.VETO_CONDITIONS['consecutive_loss_max']:
            veto = True
            reasons.append(f"连续亏损{consecutive_losses}次，暂停交易")
        
        # P1: 市场极端
        if market_sentiment in self.VETO_CONDITIONS['market_extreme_sell']:
            veto = True
            reasons.append(f"市场状态：{market_sentiment}")
        
        # P2: 实时资金
        if main_net_flow < self.VETO_CONDITIONS['main_outflow_threshold']:
            veto = True
            reasons.append(f"主力净流出{abs(main_net_flow):.0f}万")
            
        if buy_sell_ratio < self.VETO_CONDITIONS['buy_sell_ratio_min']:
            veto = True
            reasons.append(f"买卖力量比{buy_sell_ratio:.2f}过低")
            
        if fund_trend in self.VETO_CONDITIONS['fund_trend_veto']:
            veto = True
            reasons.append(f"资金趋势：{fund_trend}")
        
        if veto:
            self.veto_active = True
            self.veto_reasons.extend(reasons)
            
        return veto, reasons
    
    def filter_narrative(self, narrative: str) -> str:
        """
        过滤AI叙事文案
        如果否决激活，禁止乐观文案
        """
        if not self.veto_active:
            return narrative
            
        # 否决激活时，替换乐观词汇
        forbidden_words = ['闭眼买', '主升浪', '强势拉升', '突破', '抄底', '黄金坑', '铁底']
        warning_prefix = "⚠️ 风险提示：存在否决因子。"
        
        for word in forbidden_words:
            if word in narrative:
                narrative = narrative.replace(word, f"[已过滤:{word}]")
        
        return warning_prefix + narrative
    
    def check_contradiction(self, texts: List[str]) -> Tuple[bool, str]:
        """
        检查文案矛盾
        
        Returns:
            (是否矛盾, 矛盾描述)
        """
        combined = " ".join(texts)
        
        for word1, word2 in self.FORBIDDEN_COMBOS:
            if word1 in combined and word2 in combined:
                return True, f"矛盾：同时出现'{word1}'和'{word2}'"
        
        return False, ""
    
    def make_verdict(self) -> FinalVerdict:
        """
        生成最终裁决
        
        优先级规则：
        1. P0-P2 有否决信号 → 禁止看多
        2. 按优先级排序，高优先级信号权重更大
        3. 合并生成最终结论
        """
        if not self.judgments:
            return FinalVerdict(
                action="观望",
                action_class="watch",
                confidence=0.5,
                primary_reason="无有效信号",
                veto_reasons=[],
                all_inputs=[],
                timestamp=datetime.now(),
                is_vetoed=False
            )
        
        # 按优先级排序
        sorted_judgments = sorted(self.judgments, key=lambda x: x.priority.value)
        
        # 提取所有输入
        all_inputs = [
            {
                'priority': j.priority.name,
                'signal': j.signal.value,
                'reason': j.reason,
                'confidence': j.confidence,
                'source': j.source
            }
            for j in sorted_judgments
        ]
        
        # 如果被否决，强制改为观望/卖出
        if self.veto_active:
            # 找到最高优先级的否决信号
            veto_signal = next(
                (j for j in sorted_judgments 
                 if j.signal in [Signal.SELL, Signal.STRONG_SELL, Signal.VETO]),
                None
            )
            
            if veto_signal and veto_signal.signal == Signal.STRONG_SELL:
                return FinalVerdict(
                    action="❌ 禁止买入",
                    action_class="run",
                    confidence=0.9,
                    primary_reason=veto_signal.reason,
                    veto_reasons=self.veto_reasons,
                    all_inputs=all_inputs,
                    timestamp=datetime.now(),
                    is_vetoed=True
                )
            else:
                return FinalVerdict(
                    action="⚠️ 观望为主",
                    action_class="watch",
                    confidence=0.7,
                    primary_reason="存在否决因子，不宜激进",
                    veto_reasons=self.veto_reasons,
                    all_inputs=all_inputs,
                    timestamp=datetime.now(),
                    is_vetoed=True
                )
        
        # 无否决，按信号强度计算
        buy_score = 0
        sell_score = 0
        buy_signals = 0  # V10新增：买入信号计数
        sell_signals = 0  # V10新增：卖出信号计数
        
        for j in sorted_judgments:
            weight = 1.0 / (j.priority.value + 1)  # 优先级越高权重越大
            
            if j.signal in [Signal.STRONG_BUY, Signal.BUY]:
                buy_score += weight * j.confidence
                buy_signals += 1
            elif j.signal in [Signal.STRONG_SELL, Signal.SELL]:
                sell_score += weight * j.confidence
                sell_signals += 1
        
        # V10改进：提高准确性
        # 1. 买入信号需要≥2个信号同时确认
        # 2. 买入得分需超过卖出得分0.5（原0.3）
        # 3. 置信度要求更高
        min_buy_signals = 2  # 最少2个买入信号
        buy_threshold = 0.5   # 买入阈值提高到0.5
        
        # 决定最终动作
        if buy_score > sell_score + buy_threshold and buy_signals >= min_buy_signals:
            action = "✅ 可以关注"
            action_class = "go"
            confidence = min(buy_score, 1.0)
            reason = f"{sorted_judgments[0].reason}（{buy_signals}个信号确认）"
        elif sell_score > buy_score + 0.3 or sell_signals >= 2:
            action = "⚠️ 谨慎观望"
            action_class = "watch"
            confidence = min(sell_score, 1.0)
            reason = sorted_judgments[0].reason
        else:
            action = "⚖️ 多空平衡"
            action_class = "watch"
            confidence = 0.5
            reason = "信号不足或混合，需耐心等待"
        
        return FinalVerdict(
            action=action,
            action_class=action_class,
            confidence=confidence,
            primary_reason=reason,
            veto_reasons=[],
            all_inputs=all_inputs,
            timestamp=datetime.now(),
            is_vetoed=False
        )
    
    def generate_unified_conclusion(self, 
                                    trend_text: str,
                                    fund_text: str,
                                    risk_text: str,
                                    ai_text: str) -> str:
        """
        生成统一结论，避免UI矛盾
        
        合并所有模块输出为一句裁决结论
        """
        verdict = self.make_verdict()
        
        # 检查矛盾
        has_contradiction, contradiction_desc = self.check_contradiction(
            [trend_text, fund_text, risk_text, ai_text]
        )
        
        if has_contradiction:
            # 存在矛盾，以高优先级为准
            if verdict.is_vetoed:
                return f"🚨 **最终裁决**：{verdict.action}\n原因：{verdict.primary_reason}\n{contradiction_desc}"
            else:
                return f"⚖️ **裁决结论**：{verdict.action}\n综合考量：{verdict.primary_reason}"
        
        # 无矛盾，正常输出
        if verdict.is_vetoed:
            veto_summary = "、".join(verdict.veto_reasons[:2])
            return f"🚨 **最终裁决**：{verdict.action}\n⛔ 否决因子：{veto_summary}"
        else:
            return f"📊 **综合研判**：{verdict.action}\n💡 {verdict.primary_reason}"


# ====== 工厂函数 ======
def create_decision_core(config: Dict = None) -> DecisionCore:
    """创建决策核心"""
    return DecisionCore(config)


# ====== 便捷函数 ======
def quick_verdict(
    main_net_flow: float = 0,
    buy_sell_ratio: float = 1.0,
    fund_trend: str = "",
    market_sentiment: str = "",
    score: float = 50,
    trend_signal: str = "",
    chip_signal: str = ""
) -> FinalVerdict:
    """
    快速裁决（便捷API）
    
    一次性输入所有因子，返回最终裁决
    """
    core = DecisionCore()
    
    # 检查否决条件
    core.check_veto_conditions(
        main_net_flow=main_net_flow,
        buy_sell_ratio=buy_sell_ratio,
        fund_trend=fund_trend,
        market_sentiment=market_sentiment
    )
    
    # P2: 实时资金
    if main_net_flow > 2000:
        core.add_judgment(Priority.P2_REALTIME_FUND, Signal.BUY, 
                         f"主力净流入{main_net_flow:.0f}万", 0.7, "realtime_fund")
    elif main_net_flow < -2000:
        core.add_judgment(Priority.P2_REALTIME_FUND, Signal.SELL,
                         f"主力净流出{abs(main_net_flow):.0f}万", 0.7, "realtime_fund")
    
    # P3: 趋势/筹码
    if "多头" in trend_signal or "金叉" in trend_signal:
        core.add_judgment(Priority.P3_TREND_CHIP, Signal.BUY,
                         trend_signal, 0.6, "trend")
    elif "空头" in trend_signal or "死叉" in trend_signal:
        core.add_judgment(Priority.P3_TREND_CHIP, Signal.SELL,
                         trend_signal, 0.6, "trend")
    
    # P3: 评分
    if score >= 75:
        core.add_judgment(Priority.P3_TREND_CHIP, Signal.BUY,
                         f"综合评分{score}分", 0.6, "score")
    elif score <= 35:
        core.add_judgment(Priority.P3_TREND_CHIP, Signal.SELL,
                         f"综合评分{score}分", 0.6, "score")
    
    return core.make_verdict()
