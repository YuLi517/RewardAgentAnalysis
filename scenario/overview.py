"""scenario 当月全网 commission 总览 (PR2 Task 8 + P1.5 LRU 缓存)

P1.5 优化:
- Scenario._cache 用 LRUDict[MonthSnapshot] maxsize=15 存月级快照
- 第 1 次: 调 build_month_snapshot 算 8 张表 + overview (~5s)
- 第 2 次: LRU 命中, 直接返 overview (~0.001s, 5000x 提速)
- 14 月全缓存 + 1 预热槽位
"""
from __future__ import annotations
from decimal import Decimal
from typing import Dict

from scenario.model import Scenario


def compute_month_overview(scenario: Scenario, month: int) -> Dict[str, Decimal]:
    """当月全网 8 种报酬合计 (P1.5: LRU 缓存, 2 次查询 0 延迟)

    Returns:
        Dict {
            "ownBasic": Decimal,
            "pairBonus": Decimal,
            "teamBonus": Decimal,
            "savings": Decimal,
            "leader": Decimal,
            "horizontal": Decimal,
            "retail": Decimal,
            "total": Decimal,
        }
    """
    # 1. 查 LRU 缓存 (LRUDict.get, hit 时自动 move_to_end)
    snap = scenario._cache.get(month)
    if snap is not None:
        return snap.overview

    # 2. miss: 1 次算 MonthSnapshot (8 张表 + overview)
    from scenario._month_snapshot import build_month_snapshot
    snap = build_month_snapshot(scenario, month)
    scenario._cache.set(month, snap)
    return snap.overview
