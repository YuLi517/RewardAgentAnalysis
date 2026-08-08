"""v1.0.12 (2026-08-08): 1代4 商品价值 (新第 9 种报酬)

业务拍板 (用户 2026-08-08):
  1. 触发条件: 父节点 (非叶) 在 month 月"长出树"上 BFS 凑齐 4 个最近子
     - "长出树" = 父节点为根的子树 (不含父节点自己, 含子孙)
     - "BFS 凑齐 4 个最近" = 按 BFS 距离优先, slot 1-5 顺序
  2. 奖励金额: 95 PV (固定, 公司随机商品 80-110 PV 取中值)
  3. 触发频率: 按月计算 (每月满足条件就给 1 次)

算法:
  - 对每个非叶父节点, BFS 走 5 子区 (slot 1-5)
  - 凑齐 4 个节点 (非父节点自身) → 父节点当月拿 95 PV
  - 全网 sum 时多个父节点独立判断, 累加

设计参考: 跟 team_bonus 一样是"父节点培养下线奖励",
          但金额固定 95 PV (跟 4 档精确匹配无关)
"""
from __future__ import annotations
from collections import deque
from decimal import Decimal
from typing import Dict, List

from scenario.model import Scenario
from scenario.commission._helpers import get_nodes_and_children


# 1代4 商品价值 (固定, 中间值)
ONE_GEN_FOUR_GOODS_PV = Decimal("95")


def _bfs_collect_n_nodes(scenario: Scenario, root_bfs: int, n: int) -> List[int]:
    """BFS 走 root_bfs 长出树, 凑齐 n 个最近子节点 (BFS 距离优先, slot 1-5 顺序)
    返回 [bfs_id1, bfs_id2, ...] (不含 root_bfs 自身)
    """
    nodes, children_map = get_nodes_and_children(scenario)
    if root_bfs not in nodes:
        return []
    collected: List[int] = []
    queue: deque = deque()
    # 把 root_bfs 的所有 5 子区子节点按 slot 顺序入队
    own_children = children_map.get(root_bfs, [])
    # 按 slot_line_id 排序, 1-5 顺序
    own_children_sorted = sorted(own_children, key=lambda c: nodes[c]["slot_line_id"])
    for c in own_children_sorted:
        queue.append(c)
    while queue and len(collected) < n:
        cur = queue.popleft()
        collected.append(cur)
        # cur 的子节点也按 slot 顺序入队
        cur_children = children_map.get(cur, [])
        cur_children_sorted = sorted(cur_children, key=lambda c: nodes[c]["slot_line_id"])
        for cc in cur_children_sorted:
            queue.append(cc)
    return collected


def compute_one_gen_four_for_node(scenario: Scenario, bfs_id: int, month: int) -> Decimal:
    """单节点 API: bfs_id 当月凑齐 4 子 → 95 PV, 否则 0

    业务:
      - bfs_id 是父节点 (非叶)
      - month 月当月判断, BFS 凑齐 4 个最近子
      - 凑齐 → 95 PV (固定, 跟 PV 值无关)
    """
    nodes, children_map = get_nodes_and_children(scenario)
    if bfs_id not in nodes:
        return Decimal("0")
    # 叶子 (无子) 不参与
    if not children_map.get(bfs_id):
        return Decimal("0")
    # BFS 凑齐 4 个最近子
    collected = _bfs_collect_n_nodes(scenario, bfs_id, 4)
    if len(collected) >= 4:
        return ONE_GEN_FOUR_GOODS_PV
    return Decimal("0")


def compute_one_gen_four_table_for_month(scenario: Scenario, month: int) -> Dict[int, Decimal]:
    """P1.5 全网表: 1 次算全网 2144 节点 1代4 触发情况
    缓存机制 (跟其他 commission 一样)
    """
    cache_key = ("one_gen_four_table", id(scenario), month)
    if not hasattr(compute_one_gen_four_table_for_month, "_cache"):
        compute_one_gen_four_table_for_month._cache = {}  # type: ignore
    cache = compute_one_gen_four_table_for_month._cache  # type: ignore
    if cache_key in cache:
        return cache[cache_key]

    nodes, children_map = get_nodes_and_children(scenario)
    result: Dict[int, Decimal] = {}
    for bfs_id in nodes.keys():
        # 叶子 (无子) 不参与
        if not children_map.get(bfs_id):
            result[bfs_id] = Decimal("0")
            continue
        # BFS 凑齐 4 个最近子
        collected = _bfs_collect_n_nodes(scenario, bfs_id, 4)
        if len(collected) >= 4:
            result[bfs_id] = ONE_GEN_FOUR_GOODS_PV
        else:
            result[bfs_id] = Decimal("0")

    cache[cache_key] = result
    return result
