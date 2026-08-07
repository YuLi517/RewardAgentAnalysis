"""P1.5: ThreadPoolExecutor 14 worker 并行算 14 月 × 8 报酬 矩阵

业务:
- 14 worker 同时算 14 月, 受 GIL 但 IO 释放能并行
- 14 月 × 5s / 5 ≈ 1s, 总 < 10s
- 跟 compute_overview_all 行为一致, 仅并发
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict

from scenario.model import Scenario
from scenario.overview import compute_month_overview

# 模块级 executor, 跨请求复用 (避免每请求启停 worker)
_executor = ThreadPoolExecutor(max_workers=14, thread_name_prefix="p15-month-")


def compute_overview_all_parallel(scenario: Scenario, total_months: int = 14) -> Dict:
    """14 月 × 8 报酬 矩阵, 14 worker 并行算

    Returns:
        {
            "total_months": 14,
            "fields": ["ownBasic", "pairBonus", ...],
            "months": [0, 1, ..., 14],
            "matrix": {"ownBasic": ["$0.00", ...], ...}
        }
    """
    fields = ["ownBasic", "pairBonus", "teamBonus", "savings",
              "leader", "horizontal", "retail", "total"]
    months = list(range(0, total_months + 1))
    matrix: Dict[str, list] = {f: [None] * (total_months + 1) for f in fields}

    def compute_one_month(m):
        return m, compute_month_overview(scenario, month=m)

    # 14 worker 并行 (LRU 缓存命中, 实际只算 1 次)
    futures = [_executor.submit(compute_one_month, m) for m in months]
    for f in as_completed(futures):
        m, overview = f.result()
        for field in fields:
            matrix[field][m] = str(overview.get(field, "0"))

    return {
        "total_months": total_months,
        "fields": fields,
        "months": months,
        "matrix": matrix,
    }
