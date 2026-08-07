"""PR #74: 1-6 代 ancestor share, 4-5 USD 门槛, 7 拿不到
迁移自旧 tools/rebuild_2144_simulation.py:compute_ancestor_share
"""
from __future__ import annotations
from decimal import Decimal
from typing import Dict

from scenario.model import Scenario
from scenario.commission._helpers import (
    get_nodes_and_children, get_parent_map,
    clear_all_caches,
)


def compute_ancestor_share_dict(scenario: Scenario, own_basic: Dict[int, Decimal]) -> Dict[int, Decimal]:
    """算每个节点的 pair_bonus (1-6 代 ancestor share 之和)
    业务 (PR #74):
      - 1-3 代: 黄金 always → 15% / 10% / 5%
      - 4 代: anc.ownBasic ≥ $500 → 5%
      - 5 代: anc.ownBasic ≥ $1000 → 5%
      - 6 代: 黄金 (1 部门, always) → 5%
      - 7 代: 拿不到
    """
    cc = scenario.commission_config
    ratios = cc.pair_bonus_ratios
    max_depth = len(ratios)
    threshold_4th = Decimal(str(cc.pair_bonus_4th_usd_threshold))
    threshold_5th = Decimal(str(cc.pair_bonus_5th_usd_threshold))

    parent_map = get_parent_map(scenario)
    ancestor_share: Dict[int, Decimal] = {}
    for bfs_id, commission in own_basic.items():
        if commission <= 0:
            continue
        # ancestors 链 (1-max_depth)
        ancestors = []
        cur = parent_map.get(bfs_id, -1)
        while cur >= 0 and len(ancestors) < max_depth:
            ancestors.append(cur)
            cur = parent_map.get(cur, -1)
        # ancestors[0] = 直接父 (1 代)
        for depth, anc_bfs in enumerate(ancestors):
            gen = depth + 1
            ratio = Decimal(str(ratios.get(gen, 0.0)))
            if ratio == 0:
                continue
            # 4-5 代 USD 门槛
            if gen == 4:
                anc_ob = own_basic.get(anc_bfs, Decimal("0"))
                if anc_ob < threshold_4th:
                    continue
            elif gen == 5:
                anc_ob = own_basic.get(anc_bfs, Decimal("0"))
                if anc_ob < threshold_5th:
                    continue
            share = (commission * ratio).quantize(Decimal("0.0001"))
            ancestor_share[anc_bfs] = ancestor_share.get(anc_bfs, Decimal("0")) + share
    return ancestor_share


def compute_pair_bonus_for_node(scenario: Scenario, bfs_id: int, month: int) -> Decimal:
    """PR2 单节点 API: 算 bfs_id 在 month 月的 pair_bonus
    注意: pair_bonus 严格说是"自己 ownBasic 贡献给祖先的部分", 但单节点 API
    接受 ownBasic 字典才能算。这里简化为: 返自己 ownBasic 贡献给祖先的 pair_bonus
    (用 get_own_basic_for_node 逻辑)
    实际生产用 compute_pair_bonus_table + breakdown.py 跑全月再算每个节点
    """
    # PR2 收尾实现: 单节点 API 不可行 (pair_bonus 依赖全网 ownBasic)
    # 改为: 内部用全网 own_basic 表 (本月已算过的), 算 bfs_id 作为 ancestor 拿多少
    # 这里先返 0, breakdown.py 用 compute_pair_bonus_table 算全月
    return Decimal("0.0000")


def compute_pair_bonus_table(scenario: Scenario, month: int,
                              own_basic_dict: Dict[int, Decimal]) -> Dict[int, Decimal]:
    """PR2 收尾: 算 month 月每个节点的 pair_bonus (ancestor share 之和)
    业务: 对每个有 ownBasic 的节点, 算它给 1-6 代 ancestor 的贡献
    """
    clear_all_caches()
    return compute_ancestor_share_dict(scenario, own_basic_dict)
