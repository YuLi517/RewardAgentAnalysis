"""v1.0.15 (2026-08-08): 1代4 产品奖金 (新第 9 种报酬, 凑齐 + 1 月触发, 4 子锁定, 190 USD)

业务拍板 (用户 2026-08-08):
  1. 触发条件: 父节点 (非叶) 在 month 月"长出树"上 BFS 凑齐 4 个最近子
     - "长出树" = 父节点为根的子树 (不含父节点自己, 含子孙)
     - "BFS 凑齐 4 个最近" = 按 BFS 距离优先, slot 1-5 顺序
  2. 奖励金额: 190 USD (固定, 公司随机商品 80-110 PV 取中值 × 2 USD/PV)
     - 业务动机 (用户 2026-08-08): 9 报酬统一 USD 表示, 1代4 不能用 PV 单位
     - 转换率: 1 PV = 2 USD (业务拍板, 跟其他 8 报酬 USD 一致)
  3. 触发频率: 凑齐 4 子后下个月起, 每月都拿 190 USD (持续)
  4. 首次触发延迟 + 1 月 (v1.0.13): 凑齐 4 子那个月 + 1 月才触发
  5. 4 子关系固定 (v1.0.14): 凑齐 4 子时刻, 4 个 bfs_id + M_first 锁定到 scenario.locks_json
  6. 替代 retail 业务 (v1.0.15): retail 卡片改 "1代4 产品奖金", 9→8 卡片

v1.0.15 关键变更 (用户 2026-08-08):
  - 金额 95 PV → 190 USD (PV × 2 USD/PV 转换, 跟其他 8 报酬 USD 一致)
  - 业务动机: 9 报酬统一 USD, 1代4 之前用 PV 是单位不一致
  - 业务等价性: 95 PV × 2 USD/PV = 190 USD, 业务激励跟 v1.0.14 同
  - 卡片: 9 → 8 (retail 卡片改 label "1代4 产品奖金" + data-field=oneGenFour, 删独立 oneGenFour 卡片)
  - 实施: 算法 ONE_GEN_FOUR_GOODS_USD=190, 4 页面改 label + 8 卡片, AGENTS.md 同步

算法:
  - 4 子关系 = 预计算 (DB one_gen_four_locks_json, v1.0.14)
  - 凑齐月份 M_first = max(join_month of 4 子) (同 v1.0.13)
  - 触发月 = month >= M_first + 1 (同 v1.0.13)
  - 触发金额 = ONE_GEN_FOUR_GOODS_USD = 190 (v1.0.15, 改 95 PV)
  - 全网 sum 时多个父节点独立查表, 累加
"""
from __future__ import annotations
from decimal import Decimal
from typing import Dict

from scenario.model import Scenario
from scenario.locks import get_lock_for_node, compute_one_gen_four_locks


# 1代4 产品奖金 (固定, USD 单位, 业务 95 PV × 2 USD/PV = 190 USD)
ONE_GEN_FOUR_GOODS_USD = Decimal("190")


def compute_one_gen_four_for_node(scenario: Scenario, bfs_id: int, month: int) -> Decimal:
    """单节点 API: bfs_id 在 month 月触发 1代4 → 190 USD, 否则 0

    业务 (v1.0.15):
      - 查 locks 找 bfs_id 的 4 子 + M_first (不再动态 BFS, v1.0.14)
      - 触发月 = month >= M_first + 1 (凑齐后下个月起, v1.0.13)
      - 后续月持续触发 (4 子都还在线, 业务默认都续费)
      - 触发金额 = 190 USD (v1.0.15, 从 95 PV 改 190 USD)
      - month < M_first + 1 → 0
    """
    lock = get_lock_for_node(scenario, bfs_id)
    if lock is None:
        return Decimal("0")  # 叶子 / 凑不齐 4 子
    m_first = lock["m_first"]
    if month < m_first + 1:
        return Decimal("0")
    return ONE_GEN_FOUR_GOODS_USD


def compute_one_gen_four_table_for_month(scenario: Scenario, month: int) -> Dict[int, Decimal]:
    """P1.5 全网表: 1 次算全网 2144 节点 1代4 触发情况
    v1.0.14: 查 locks 表, 不动态 BFS
    v1.0.15: 金额 95 PV → 190 USD
    缓存机制 (跟其他 commission 一样)
    """
    cache_key = ("one_gen_four_table", id(scenario), month)
    if not hasattr(compute_one_gen_four_table_for_month, "_cache"):
        compute_one_gen_four_table_for_month._cache = {}  # type: ignore
    cache = compute_one_gen_four_table_for_month._cache  # type: ignore
    if cache_key in cache:
        return cache[cache_key]

    # 1. 1 次算全网 locks (查表 / backfill / cache, < 100ms)
    locks = compute_one_gen_four_locks(scenario)
    # 2. 全网表, 每个 bfs_id 查表
    result: Dict[int, Decimal] = {}
    for bfs_id in locks.keys():
        lock = locks[bfs_id]
        m_first = lock["m_first"]
        if month < m_first + 1:
            result[bfs_id] = Decimal("0")
        else:
            result[bfs_id] = ONE_GEN_FOUR_GOODS_USD
    # 3. 没 lock 的节点 (叶子 / 凑不齐) 默认 0
    #    注意: 上游 compute_month_overview 用 .get(bfs_id, 0) 处理, 缺 key = 0
    #    所以这里只填有 lock 的 bfs_id, 叶子自动 0

    cache[cache_key] = result
    return result
