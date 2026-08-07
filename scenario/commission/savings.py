"""PR #73: 储蓄奖金
ownBasic ≥ $250 → savings = min(ownBasic × 15%, $500)
"""
from decimal import Decimal
from scenario.model import Scenario


def compute_savings_for_node(scenario: Scenario, bfs_id: int, month: int,
                              own_basic_usd: Decimal) -> Decimal:
    """PR #73: savings = min(ownBasic × 15%, $500) if ownBasic ≥ $250
    注: breakdown.py 已经传 own_basic_usd 进来, 这里只算阈值/cap
    """
    cc = scenario.commission_config
    if own_basic_usd < Decimal(str(cc.savings_usd_threshold)):
        return Decimal("0.0000")
    s = min(
        own_basic_usd * Decimal(str(cc.savings_rate)),
        Decimal(str(cc.savings_cap_usd))
    )
    return s.quantize(Decimal("0.0001"))
