"""2026-08-07 纵向领袖分红: 4 大区各 1 套 IP 链 (IP1=L1 父, IP2=L2 父, IP3=L3 父, IP4=L4 父)
迁移自旧 tools/rebuild_2144_simulation.py:compute_leader_dividend
业务: 4 大区 (root 4 line) 各自 1 套 IP 链, IP_n 拿 2n 份
- 触发: IP 节点选 2 条分支 (2 叉方案 2 选 2) 都 4 周 ≥ 13,334 PV
- 每份 $500
- 不满足当月 = 0 份
"""
from __future__ import annotations
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from scenario.model import Scenario
from scenario.commission._helpers import (
    get_nodes_and_children, subtree_pv_at_month,
)
from scenario._pv import compute_monthly_pv


def compute_leader_for_node(scenario: Scenario, bfs_id: int, month: int) -> Decimal:
    """算 bfs_id 在 month 月拿的纵向领袖分红 USD
    业务: bfs_id 必须是 4 大区 IP 链上的某 IP 节点 (region 1-4 的 IP1/IP2/IP3/IP4)
    简化为: 计算 4 大区 IP 链总份数 × $500, 然后分给 bfs_id 所在的 IP (如果有)
    """
    # 算 month 月 IP 链总状态
    status = compute_leader_dividend_status(scenario, month)
    # bfs_id 是不是某 IP 节点?
    for region, ip_level, top1_pv, top2_pv, ok, shares in status["ip_status"]:
        # IP 节点 = bfs_id (region) for IP1, IP1 1区 子 for IP2, etc.
        ip_bfs = _resolve_ip_bfs(scenario, region, ip_level)
        if ip_bfs == bfs_id and ok:
            return (Decimal(shares) * Decimal(str(scenario.commission_config.leader_dividend_share_usd))).quantize(Decimal("0.01"))
    return Decimal("0.00")


def compute_leader_dividend_for_node(scenario: Scenario, bfs_id: int, month: int) -> Decimal:
    """单节点 API"""
    return compute_leader_for_node(scenario, bfs_id, month)


def _resolve_ip_bfs(scenario: Scenario, region: int, ip_level: int) -> Optional[int]:
    """找 region 大区第 ip_level 级 IP 节点 bfs_id
    IP1 = L1 父 region
    IP2 = IP1 1区 (line 1) 子
    IP3 = IP2 1区 子
    IP4 = IP3 1区 子
    """
    if ip_level < 1:
        return None
    ip_bfs = region  # IP1
    nodes, children_map = get_nodes_and_children(scenario)
    for _ in range(1, ip_level):
        # 找 line 1 子
        next_ip = None
        for c in children_map.get(ip_bfs, []):
            if nodes[c]["slot_line_id"] == 1:
                next_ip = c
                break
        ip_bfs = next_ip
        if ip_bfs is None:
            return None
    return ip_bfs


def compute_leader_dividend_status(scenario: Scenario, month: int) -> dict:
    """算 month 月 4 大区 IP 链状态
    Returns: {
        "total_shares": int,
        "total_usd": Decimal,
        "per_region": {1: shares, 2: shares, ...},
        "ip_status": [(region, ip_level, top1_pv, top2_pv, ok, shares), ...]
    }
    """
    cc = scenario.commission_config
    threshold_pv = cc.leader_dividend_threshold_pv  # 13334
    months_per_period = 4
    monthly_pv_threshold = threshold_pv * months_per_period  # 53336

    # 算 month 月 monthly_pv (own + 子孙累计)
    total_months = max(month + 1, scenario.total_months)
    monthly_pv, _ = compute_monthly_pv(scenario, total_months)

    per_region_shares: Dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0}
    ip_status: List[Tuple[int, int, int, int, bool, int]] = []

    for region in [1, 2, 3, 4]:
        ip_bfs = region  # IP1 = L1 父
        for ip_level in [1, 2, 3, 4]:
            if ip_bfs is None:
                break
            # 算 IP 节点所有 line 子树 PV
            nodes, children_map = get_nodes_and_children(scenario)
            line_pvs: List[Tuple[int, int]] = []
            for c in children_map.get(ip_bfs, []):
                if nodes[c]["slot_line_id"] <= 5:
                    sp = subtree_pv_at_month(scenario, c, month, monthly_pv)
                    line_pvs.append((nodes[c]["slot_line_id"], sp))
            line_pvs.sort(key=lambda x: -x[1])
            if len(line_pvs) >= 2:
                top1_pv = line_pvs[0][1]
                top2_pv = line_pvs[1][1]
                ok = (top1_pv >= monthly_pv_threshold and top2_pv >= monthly_pv_threshold)
            else:
                ok = False
                top1_pv = line_pvs[0][1] if line_pvs else 0
                top2_pv = 0
            shares = 2 * ip_level if ok else 0
            ip_status.append((region, ip_level, top1_pv, top2_pv, ok, shares))
            per_region_shares[region] += shares
            if not ok:
                break
            # 下一 IP 沿 line 1
            ip_bfs = _resolve_ip_bfs(scenario, region, ip_level + 1)

    total_shares = sum(per_region_shares.values())
    total_usd = (Decimal(total_shares) * Decimal(str(cc.leader_dividend_share_usd))).quantize(Decimal("0.01"))
    return {
        "total_shares": total_shares,
        "total_usd": total_usd,
        "per_region": per_region_shares,
        "ip_status": ip_status,
    }
