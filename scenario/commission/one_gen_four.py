"""v1.0.13 (2026-08-08): 1代4 商品价值 (新第 9 种报酬, 凑齐 + 1 月触发)

业务拍板 (用户 2026-08-08):
  1. 触发条件: 父节点 (非叶) 在 month 月"长出树"上 BFS 凑齐 4 个最近子
     - "长出树" = 父节点为根的子树 (不含父节点自己, 含子孙)
     - "BFS 凑齐 4 个最近" = 按 BFS 距离优先, slot 1-5 顺序
  2. 奖励金额: 95 PV (固定, 公司随机商品 80-110 PV 取中值)
  3. 触发频率: 凑齐 4 子后下个月起, 每月都拿 95 PV (持续)

v1.0.13 关键变更 (用户 2026-08-08 第 4 轮澄清):
  - 首次触发延迟: 凑齐 4 子那个月 + 1 月才触发
  - 业务背景: 子节点挂满 4 后, 需要下个月完成 100 PV 递延才触发
    (例: 3月第2周 A、B 挂入父 F, 3月第3周 C、D 挂入父 F → 凑齐 4 子在 3月第3周
         → 等到 4月第3周, C、D 完成 100 PV 递延 → 4月第3周 (月 1) 触发)
  - 业务算法: 凑齐月份 M_first = max(join_month of 4 子)
                触发月 = month >= M_first + 1
  - 后续每月都触发 (跟 v1.0.12 "按月" 业务一致, 业务上 4 子都续费是默认, 不单独检查)

算法:
  - 对每个非叶父节点, BFS 走 5 子区 (slot 1-5)
  - 凑齐 4 个节点 (非父节点自身), 记录凑齐月份 M_first
  - month >= M_first + 1 → 95 PV
  - month < M_first + 1 → 0
  - 全网 sum 时多个父节点独立判断, 累加

设计参考: 跟 team_bonus 一样是"父节点培养下线奖励",
          但金额固定 95 PV (跟 4 档精确匹配无关)
          首次触发延迟 1 月 反映 "子节点 100 PV 续费" 业务背景
"""
from __future__ import annotations
from collections import deque
from decimal import Decimal
from typing import Dict, List, Tuple

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


def _get_first_complete_month(scenario: Scenario, bfs_id: int) -> int:
    """算父节点凑齐 4 子那个月 M_first (= 4 子中 max(join_month))

    业务 (v1.0.13):
      - 凑齐 4 子月份 = 4 子中最后挂入的子节点 join_month
      - 例: 3月第2周 A、B 挂入 + 3月第3周 C、D 挂入 → M_first = 月 0 (业务上 4 子都 3月挂入)
      - 实际: binarytree 模板所有 join_month=0, 所以 M_first 总是 0
      - 后续: v1.0.13+ 如果 json_tree_loader 算 L2+ join_month 反映 BFS 位置, M_first 会动态
    """
    nodes, children_map = get_nodes_and_children(scenario)
    if bfs_id not in nodes:
        return -1  # 不存在
    if not children_map.get(bfs_id):
        return -1  # 叶子不参与
    collected = _bfs_collect_n_nodes(scenario, bfs_id, 4)
    if len(collected) < 4:
        return -1  # 凑不齐 4 子
    # 凑齐月份 = 4 子中 max(join_month)
    return max(nodes[c]["join_month"] for c in collected)


def compute_one_gen_four_for_node(scenario: Scenario, bfs_id: int, month: int) -> Decimal:
    """单节点 API: bfs_id 在 month 月触发 1代4 → 95 PV, 否则 0

    业务 (v1.0.13):
      - 凑齐 4 子月份 = M_first (4 子中 max(join_month))
      - 触发月 = month >= M_first + 1 (凑齐后下个月起)
      - 后续月持续触发 (4 子都还在线, 业务默认都续费)
      - month < M_first + 1 → 0
    """
    nodes, children_map = get_nodes_and_children(scenario)
    if bfs_id not in nodes:
        return Decimal("0")
    if not children_map.get(bfs_id):
        return Decimal("0")
    m_first = _get_first_complete_month(scenario, bfs_id)
    if m_first < 0:
        return Decimal("0")
    # 首次触发延迟 + 1 月 (凑齐当月不算, 下个月起)
    if month < m_first + 1:
        return Decimal("0")
    return ONE_GEN_FOUR_GOODS_PV


def compute_one_gen_four_table_for_month(scenario: Scenario, month: int) -> Dict[int, Decimal]:
    """P1.5 全网表: 1 次算全网 2144 节点 1代4 触发情况
    v1.0.13: 凑齐 + 1 月触发逻辑
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
        m_first = _get_first_complete_month(scenario, bfs_id)
        if m_first < 0:
            result[bfs_id] = Decimal("0")
            continue
        # 首次触发延迟 + 1 月
        if month < m_first + 1:
            result[bfs_id] = Decimal("0")
        else:
            result[bfs_id] = ONE_GEN_FOUR_GOODS_PV

    cache[cache_key] = result
    return result
