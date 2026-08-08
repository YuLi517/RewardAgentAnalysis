"""P1.6: ProcessPoolExecutor 14 worker 真正并行 (GIL-free)

P1.5 ThreadPoolExecutor 14 worker 受 GIL 限制, 实际并发 ≈ 1-2 worker
P1.6 ProcessPoolExecutor 14 worker 跨进程, GIL-free 真正并行

业务:
- 14 worker 同时算 14 月, 跨进程 (spawn 模式) 各持独立 Python 解释器
- scenario 走 pickling 跨进程 (Pydantic Scenario 自动支持)
- 14 月 × ~50ms / 14 ≈ 50ms 目标, 1st call < 150ms
- 14 worker × 50MB = 700MB 内存峰值, 业务接受
- 注: Windows spawn 模式, 嵌套 closure 函数不可 pickle
  → worker 必须是模块级函数, scenario 通过参数传入
- P1.6 加成: 父进程 LRU 检查 → 2nd call 直接 hit 跳过 executor
  → worker 返 MonthSnapshot (非仅 overview), 父存 LRU 供后续复用
"""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, List

from scenario.model import Scenario


# 模块级 worker (Windows spawn 模式必须可 pickle, 嵌套 closure 不行)
def _compute_one_month_worker(scenario: Scenario, m: int):
    """worker 函数: 算 1 个月 MonthSnapshot (8 表 + overview)

    模块级函数 → pickle 走 save_global, 跨进程可重建
    scenario 走 pickle.dumps (Pydantic dataclass 自动支持)
    返 (month, MonthSnapshot) 让父进程能存 LRU
    """
    from scenario._month_snapshot import build_month_snapshot
    snap = build_month_snapshot(scenario, m)
    return m, snap


# 模块级 executor, 跨请求复用 (避免每请求启停 worker)
# Windows: ProcessPoolExecutor 默认 spawn 模式, 14 worker 各自启独立 Python 解释器
_executor = ProcessPoolExecutor(max_workers=14)


def compute_overview_all_parallel(scenario: Scenario, total_months: int = 14) -> Dict:
    """14 月 × 9 报酬 矩阵, 14 worker 真正并行 (P1.6 GIL-free, v1.0.12 加 1代4)

    P1.6 优化:
    - 先查父进程 LRU, 命中的 month 跳过 executor (2nd call 0.6ms)
    - 未命中的 month 走 ProcessPoolExecutor (1st call 100-150ms, 跨进程 GIL-free)
    - executor 返 MonthSnapshot, 父存 LRU 供后续复用

    Returns:
        {
            "total_months": 14,
            "fields": ["ownBasic", "pairBonus", ...],
            "months": [0, 1, ..., 14],
            "matrix": {"ownBasic": ["$0.00", ...], ...}
        }
    """
    fields = ["ownBasic", "pairBonus", "teamBonus", "savings",
              "leader", "horizontal", "retail", "oneGenFour", "total"]
    months: List[int] = list(range(0, total_months + 1))
    matrix: Dict[str, list] = {f: [None] * (total_months + 1) for f in fields}

    # 1. 先查父进程 LRU, 命中的直接用 (2nd call 0 延迟)
    snapshots: Dict[int, object] = {}
    missing: List[int] = []
    for m in months:
        snap = scenario._cache.get(m)
        if snap is not None:
            snapshots[m] = snap
        else:
            missing.append(m)

    # 2. 未命中的 month 走 ProcessPoolExecutor (GIL-free 真正并行)
    if missing:
        futures = {
            m: _executor.submit(_compute_one_month_worker, scenario, m)
            for m in missing
        }
        for m, f in futures.items():
            m_result, snap = f.result()
            snapshots[m_result] = snap
            # 关键: 存 LRU 供 2nd call 命中
            scenario._cache.set(m_result, snap)

    # 3. 组装 matrix (从 snapshot.overview 抽数字)
    for m in months:
        snap = snapshots[m]
        for field in fields:
            matrix[field][m] = str(snap.overview.get(field, "0"))

    return {
        "total_months": total_months,
        "fields": fields,
        "months": months,
        "matrix": matrix,
    }
