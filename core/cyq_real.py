# -*- coding: utf-8 -*-
"""
真实/可用的“筹码/获利盘”模块（稳健版）
优先：Tushare Pro cyq_perf（若账号权限不足/接口无数据会自动降级）
降级：用近N日成交额/成交量估算平均成本（VWAP），用“量能加权盈利天数”估算获利盘比例
注意：降级算法是“近似筹码”，不是交易所官方筹码。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple

import math

def _safe_float(x, default=0.0) -> float:
    try:
        if x is None:
            return float(default)
        return float(x)
    except Exception:
        return float(default)

def _now_ymd() -> str:
    return datetime.now().strftime("%Y%m%d")

def _ymd_days_ago(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

def _try_tushare_cyq_perf(pro, ts_code: str, lookback_days: int = 60) -> Optional[Dict[str, Any]]:
    """尝试调用 Tushare Pro 的 cyq_perf。成功则返回标准化 dict，否则返回 None。"""
    if pro is None:
        return None
    try:
        df = pro.cyq_perf(
            ts_code=ts_code,
            start_date=_ymd_days_ago(lookback_days),
            end_date=_now_ymd()
        )
        if df is None or getattr(df, "empty", True):
            return None

        df = df.sort_values(by="trade_date", ascending=False)
        row = df.iloc[0].to_dict()

        # winner_rate: 获利盘（%）
        winner = row.get("winner_rate", row.get("winner_rate_pct", row.get("winner", None)))
        winner_rate = _safe_float(winner, 0.0)

        # 平均成本：优先 cost_50pct / cost_50
        avg_cost = row.get("cost_50pct", row.get("cost_50", row.get("avg_cost", 0)))
        avg_cost = _safe_float(avg_cost, 0.0)

        if avg_cost <= 0 and winner_rate <= 0:
            return None

        return {
            "winner_rate": float(winner_rate),
            "avg_cost": float(avg_cost),
            "source": "tushare_cyq_perf",
            "raw": {k: row.get(k) for k in ("trade_date", "winner_rate", "cost_50pct", "cost_50")}
        }
    except Exception:
        return None

def _fallback_estimate_from_daily(
    daily_rows: List[Dict[str, Any]],
    current_price: float,
    window: int = 60
) -> Optional[Dict[str, Any]]:
    """用日线近似筹码：
    - avg_cost：近window日 VWAP（amount/vol）
    - winner_rate：量能加权“close <= current_price”的比例（0-100）
    daily_rows: 形如 [{'trade_date':..., 'close':..., 'vol':..., 'amount':...}, ...]，通常按时间倒序（最新在0）
    """
    if not daily_rows or current_price <= 0:
        return None

    rows = daily_rows[:max(10, window)]  # 至少10天，否则没意义
    total_vol = 0.0
    total_amt = 0.0
    win_vol = 0.0

    for r in rows:
        close = _safe_float(r.get("close"), 0.0)
        vol = _safe_float(r.get("vol"), 0.0)
        amt = _safe_float(r.get("amount"), 0.0)

        # tushare 日线：vol(手=100股)，amount(千元)；这里用 amt/vol 得到“千元/手”
        # 转成“元/股”： (amt*1000) / (vol*100)
        if vol <= 0 or close <= 0:
            continue

        total_vol += vol
        total_amt += amt

        if close <= current_price:
            win_vol += vol

    if total_vol <= 0:
        return None

    # VWAP 近似：元/股
    avg_cost = (total_amt * 1000.0) / (total_vol * 100.0)

    winner_rate = (win_vol / total_vol) * 100.0
    winner_rate = max(0.0, min(100.0, winner_rate))

    return {
        "winner_rate": float(round(winner_rate, 2)),
        "avg_cost": float(round(avg_cost, 2)),
        "source": "fallback_vwap_volume_weighted",
        "raw": {"window": len(rows)}
    }

def get_cyq_analysis(
    ts_code: str,
    pro=None,
    daily_rows: Optional[List[Dict[str, Any]]] = None,
    current_price: float = 0.0
) -> Dict[str, Any]:
    """统一入口，返回给前端的 cyq_data 结构。"""
    # 1) 尝试官方筹码接口
    r = _try_tushare_cyq_perf(pro, ts_code)
    if r:
        desc = f"获利盘 {r['winner_rate']}%"
        return {
            "avg_cost": r["avg_cost"],
            "winner_rate": r["winner_rate"],
            "desc": desc,
            "valid": True,
            "source": r.get("source", "tushare"),
        }

    # 2) 降级估算（不依赖权限）
    est = _fallback_estimate_from_daily(daily_rows or [], current_price=current_price, window=60)
    if est:
        desc = f"获利盘 {est['winner_rate']}%（估算）"
        return {
            "avg_cost": est["avg_cost"],
            "winner_rate": est["winner_rate"],
            "desc": desc,
            "valid": True,
            "source": est.get("source", "fallback"),
        }

    return {"avg_cost": 0.0, "winner_rate": 0.0, "desc": "无数据", "valid": False, "source": "none"}
