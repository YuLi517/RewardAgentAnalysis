"""scenario 树形构建 (PR2 收尾 round 3)
PR1: 基础 BFS 树构建
PR2 收尾 round 3: L3+ 节点按 Growth 排 join_week/month
  - 4 大区各 nodes_per_region_per_week/周
  - join_week = (l3plus_index_in_region) // nodes_per_region_per_week
  - join_month = join_week // weeks_per_month
  - color_index = (join_month % 4) + 1
"""
from __future__ import annotations
from collections import deque
from typing import Dict, List, Optional, Tuple

from scenario.model import Scenario, TreeShape, Growth, Revenue, CommissionConfig, MonthSnapshot


def _build_bfs_tree(tree_shape: TreeShape, growth: Optional[Growth] = None) -> Dict[int, dict]:
    """PR2 收尾: growth 是可选 (旧测试调用单参)"""
    """构 BFS 树 + L3+ 节点 round_robin 排 join_week/month
    业务上 L3+ 节点 (新成员) 每周 4 大区各 NODES_PER_REGION_PER_WEEK 加入
    """
    nodes: Dict[int, dict] = {}
    layer_counts = tree_shape.layer_counts
    total = sum(layer_counts.values())
    fork_max = {"binary": 2, "four_way": 4, "eight_way": 8}[tree_shape.fork_type]
    if growth is None:
        n_per_region_per_week = 9
        n_regions = 4
        weeks_per_month = 4
    else:
        n_per_region_per_week = growth.nodes_per_region_per_week
        n_regions = growth.n_regions
        weeks_per_month = growth.weeks_per_month

    # L0 root
    nodes[0] = {"bfs_id": 0, "level": 0, "parent_bfs": -1, "slot_line_id": 0,
                "region_id": 0, "join_week": 0, "join_month": 0, "color_index": 0}

    # L1: 按 fork_type 决定 L1 父数
    if tree_shape.fork_type == "binary":
        l1_n = 4
    elif tree_shape.fork_type == "four_way":
        l1_n = 4
    else:
        l1_n = 8
    for line in range(1, l1_n + 1):
        bfs_id = line
        region = line if l1_n <= 4 else line
        nodes[bfs_id] = {"bfs_id": bfs_id, "level": 1, "parent_bfs": 0, "slot_line_id": line,
                         "region_id": region, "join_week": 0, "join_month": 0, "color_index": 0}

    # L2+: 严格 fork_max 叉 (queue[lv] 存 lv 层父节点, pop 出在 lv+1 层造子)
    bfs_cursor = l1_n + 1
    layer_bfs_queues: Dict[int, deque] = {lv: deque() for lv in layer_counts.keys()}
    for bfs_id in range(1, l1_n + 1):
        layer_bfs_queues[1].append(bfs_id)

    # PR2 收尾 round 3: 跟踪每个 region 的 l3plus_count 用于排 join_week
    # 业务: 4 大区独立 BFS 排, 每大区每周 n_per_region_per_week
    # round_robin: 4 大区各每周 N 个, 全网 36/周
    # region_l3plus_count 用 L1 父 region 范围 (1-l1_n)
    region_l3plus_count: Dict[int, int] = {r: 0 for r in range(1, l1_n + 1)}

    max_lv = max(layer_counts.keys())
    for lv in range(1, max_lv):
        if bfs_cursor >= total:
            break
        while layer_bfs_queues[lv] and bfs_cursor < total:
            parent_bfs = layer_bfs_queues[lv].popleft()
            parent_node = nodes[parent_bfs]
            for line in range(1, fork_max + 1):
                if bfs_cursor >= total:
                    break
                bfs_id = bfs_cursor
                level = parent_node["level"] + 1
                region = parent_node["region_id"]
                # L3+ 节点 (level >= 3) 排 join_week/month
                if level >= 3:
                    idx_in_region = region_l3plus_count[region]
                    join_week = idx_in_region // n_per_region_per_week
                    join_month = join_week // weeks_per_month
                    color_index = (join_month % 4) + 1
                    region_l3plus_count[region] += 1
                else:
                    join_week = 0
                    join_month = 0
                    color_index = 0
                nodes[bfs_id] = {"bfs_id": bfs_id, "level": level, "parent_bfs": parent_bfs,
                                 "slot_line_id": line, "region_id": region,
                                 "join_week": join_week, "join_month": join_month,
                                 "color_index": color_index}
                layer_bfs_queues[level].append(bfs_id)
                bfs_cursor += 1

    if bfs_cursor != total:
        raise ValueError(
            f"layer_counts 跟 fork_type 不一致: 造了 {bfs_cursor} 节点, 目标 {total}"
        )
    return nodes


def _compute_total_weeks(nodes: Dict[int, dict], growth: Growth) -> Tuple[int, int]:
    """算 total_weeks + total_months
    L3+ 节点按 (region, join_week) round_robin 排, 取 max join_week
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
    nodes = _build_bfs_tree(tree_shape, growth)
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
