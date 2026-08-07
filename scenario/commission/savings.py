"""PR #73: 储蓄奖金 (ownBasic ≥ $250 → min(×15%, $500))
PR2 阶段: stub 返 0 (PR2 收尾实现)
"""
from decimal import Decimal
from scenario.model import Scenario


def compute_savings_for_node(scenario: Scenario, bfs_id: int, month: int, own_basic_usd: Decimal) -> Decimal:
    """PR2 stub: 返 0 (后续 PR2 收尾实现)"""
    return Decimal("0.0000")
