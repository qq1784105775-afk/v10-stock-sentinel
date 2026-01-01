
from datetime import datetime

class ReviewManager:
    def generate(self, mkt_data, pos_data, hot_sector):
        today = datetime.now().strftime('%Y-%m-%d')
        
        # 1. 获取核心数据
        idx_chg = float(mkt_data.get('index_change', 0))
        north = float(mkt_data.get('north_money', 0))
        
        # 2. 判定大盘情绪 (图标 + 文字)
        sentiment_icon = "🟡"
        sentiment_text = "震荡"
        
        if idx_chg > 0.8:
            sentiment_icon = "🔴"
            sentiment_text = "强势"
        elif idx_chg < -0.8:
            sentiment_icon = "🟢"
            sentiment_text = "极弱"
        elif idx_chg < 0:
            sentiment_icon = "🔵"
            sentiment_text = "调整"
            
        # 3. 计算持仓情况
        pos_count = len(pos_data)
        profit_count = sum(1 for p in pos_data if p['float_pnl'] > 0)
        if pos_count > 0:
            pos_status = f"持有 {pos_count} 只，盈利 {profit_count} 只"
        else:
            pos_status = "空仓 (等待机会)"

        # 4. 生成 AI 策略 (根据 大盘 + 北向 联合判断)
        # 逻辑：北向是大盘的聪明钱，结合指数看更准
        strategy_icon = "⏳"
        strategy_text = "观望 (等待企稳)"
        
        if idx_chg > 0 and north > 20:
            strategy_icon = "🚀"
            strategy_text = "进攻 (跟随主力)"
        elif idx_chg < 0 and north < -20:
            strategy_icon = "🛡️"
            strategy_text = "防守 (严控仓位)"
        elif idx_chg < 0 and north > 10:
            strategy_icon = "💎"
            strategy_text = "低吸 (外资抄底)"
        
        # 5. 生成 HTML (完全复刻图二样式)
        html = f"""
        <div style="text-align:center; font-size:18px; font-weight:bold; color:#fff; margin-bottom:15px;">
            🤖 每日复盘
        </div>
        <div style="font-size:15px; line-height:2.2; color:#cfd8dc;">
            <div style="border-bottom:1px dashed #445; padding-bottom:5px; margin-bottom:5px;">
                <span style="font-size:18px;">{today} 复盘报告</span>
            </div>
            
            <div>🌐 <b>大盘情绪：</b> {sentiment_icon} <span style="color:#fff">{sentiment_text}</span> (指数 {idx_chg}%)</div>
            
            <div>🔥 <b>强势板块：</b> <span style="color:#ffcc00">{hot_sector}</span></div>
            
            <div>📊 <b>持仓状态：</b> {pos_status}</div>
            
            <div>🎯 <b>明日策略：</b> {strategy_icon} <span style="color:#00ffff; font-weight:bold;">{strategy_text}</span></div>
            
            <div style="margin-top:10px; font-size:12px; color:#889; background:rgba(255,255,255,0.05); padding:8px; border-radius:4px;">
                建议关注 Smart Selector 筛出的高评分个股，避免去接飞刀。
            </div>
        </div>
        """
        
        return html
