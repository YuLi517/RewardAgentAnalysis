"""2026-08-07 纵向领袖分红: 4 大区各 1 套 IP 链 (IP1=L1 父, IP2=L2 父, IP3=L3 父, IP4=L4 父)
PR2 阶段: stub 返 0 (PR2 收尾实现)
"""
from decimal import Decimal
from scenario.model import Scenario


def compute_leader_dividend_for_node(scenario: Scenario, bfs_id: int, month: int) -> Decimal:
    """PR2 stub: 返 0 (后续 PR2 收尾实现, 包括 IP 链 + 4 大区各 1 套)"""
    return Decimal("0.0000")
