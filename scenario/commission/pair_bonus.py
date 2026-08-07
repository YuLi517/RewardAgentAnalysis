"""PR #74: 1-6 代 ancestor share, 4-5 USD 门槛, 7 拿不到
PR2 阶段: stub 返 0 (PR2 收尾实现)
"""
from decimal import Decimal
from scenario.model import Scenario


def compute_pair_bonus_for_node(scenario: Scenario, bfs_id: int, month: int) -> Decimal:
    """1-6 代 ancestor share. PR2 stub: 返 0 (后续 PR2 收尾实现)"""
    return Decimal("0.0000")
