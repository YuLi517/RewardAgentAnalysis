"""scenario 树形构建 (PR1)"""
from __future__ import annotations
from collections import deque
from typing import Dict, List, Optional, Tuple

from scenario.model import Scenario, TreeShape, Growth, Revenue, CommissionConfig, MonthSnapshot


def _build_bfs_tree(tree_shape: TreeShape) -> Dict[int, dict]:
    """构 BFS 树, 返 {bfs_id: {level, parent_bfs, slot_line_id, region_id, join_week, join_month, color_index}}
    跟旧 tools/rebuild_2144_simulation.py:build_bfs_tree() 行为完全一致:
    - 2 叉 (binary): L0=1, L1=4 (line 1-4 4 大区), L2+ 严格 2 叉 (line 1-2)
    - 4 叉 (four_way): L0=1, L1=4 (line 1-4), L2+ 严格 4 叉 (line 1-4)
    - 8 叉 (eight_way): L0=1, L1=8 (line 1-8), L2+ 严格 8 叉
    """
    nodes: Dict[int, dict] = {}
    layer_counts = tree_shape.layer_counts
    total = sum(layer_counts.values())
    fork_max = {"binary": 2, "four_way": 4, "eight_way": 8}[tree_shape.fork_type]

    # L0 root
    nodes[0] = {"bfs_id": 0, "level": 0, "parent_bfs": -1, "slot_line_id": 0,
                "region_id": 0, "join_week": 0, "join_month": 0, "color_index": 0}

    # L1: 按 fork_type 决定 L1 父数
    if tree_shape.fork_type == "binary":
        l1_n = 4  # binary 也用 4 大区, 但 L2+ 严格 2 叉
    elif tree_shape.fork_type == "four_way":
        l1_n = 4
    else:  # eight_way
        l1_n = 8
    for line in range(1, l1_n + 1):
        bfs_id = line
        region = line
        nodes[bfs_id] = {"bfs_id": bfs_id, "level": 1, "parent_bfs": 0, "slot_line_id": line,
                         "region_id": region, "join_week": 0, "join_month": 0, "color_index": 0}

    # L2+: 严格 fork_max 叉 (queue[lv] 存 lv 层父节点, pop 出在 lv+1 层造子)
    bfs_cursor = l1_n + 1
    layer_bfs_queues: Dict[int, deque] = {lv: deque() for lv in layer_counts.keys()}
    for bfs_id in range(1, l1_n + 1):
        layer_bfs_queues[1].append(bfs_id)

    # 严格按层级循环: 先 L2 父造 L3, 再 L3 父造 L4, ...
    # 关键: 一个层造完才进下一层 (避免跨层递归 bug)
    max_lv = max(layer_counts.keys())
    for lv in range(1, max_lv):
        if bfs_cursor >= total:
            break
        # 处理 lv 层所有父, 造 lv+1 层子
        while layer_bfs_queues[lv] and bfs_cursor < total:
            parent_bfs = layer_bfs_queues[lv].popleft()
            parent_node = nodes[parent_bfs]
            for line in range(1, fork_max + 1):
                if bfs_cursor >= total:
                    break
                bfs_id = bfs_cursor
                level = parent_node["level"] + 1
                region = parent_node["region_id"]
                nodes[bfs_id] = {"bfs_id": bfs_id, "level": level, "parent_bfs": parent_bfs,
                                 "slot_line_id": line, "region_id": region,
                                 "join_week": 0, "join_month": 0, "color_index": 0}
                layer_bfs_queues[level].append(bfs_id)
                bfs_cursor += 1

    if bfs_cursor != total:
        raise ValueError(
            f"layer_counts 跟 fork_type 不一致: 造了 {bfs_cursor} 节点, 目标 {total}"
        )

    return nodes


def _compute_total_weeks(nodes: Dict[int, dict], growth: Growth) -> Tuple[int, int]:
    """算 total_weeks + total_months
    L0/L1/L2 节点 join_week=0, L3+ 按 NODES_PER_REGION_PER_WEEK 排周
    业务: 4 大区 × nodes_per_region_per_week = 全网每节点/周
    """
    l3plus_count = sum(1 for n in nodes.values() if n["level"] >= 3)
    n_per_week = growth.nodes_per_region_per_week * growth.n_regions
    total_weeks = (l3plus_count + n_per_week - 1) // n_per_week if l3plus_count > 0 else 0
    total_months = (total_weeks + growth.weeks_per_month - 1) // growth.weeks_per_month
    return total_weeks, total_months


def build_scenario(tree_shape: TreeShape,
                    growth: Growth,
                    revenue: Revenue,
                    commission_config: CommissionConfig,
                    name: str = "untitled",
                    scenario_id: Optional[int] = None) -> Scenario:
    """主入口: 从 4 组参数构场景"""
    nodes = _build_bfs_tree(tree_shape)
    total_target = sum(tree_shape.layer_counts.values())
    total_weeks, total_months = _compute_total_weeks(nodes, growth)
    return Scenario(
        id=scenario_id,
        name=name,
        tree_shape=tree_shape,
        growth=growth,
        revenue=revenue,
        commission_config=commission_config,
        total_target=total_target,
        total_weeks=total_weeks,
        total_months=total_months,
    )
