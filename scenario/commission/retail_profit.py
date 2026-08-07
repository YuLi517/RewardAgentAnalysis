"""PR #70: 零售利润 (下单管理, 非 commission 累计)
PR2 阶段: stub 返 0 (PR2 收尾实现, 跟 PR #70 下单管理联动)
"""
from decimal import Decimal
from scenario.model import Scenario


def compute_retail_profit_for_node(scenario: Scenario, bfs_id: int, month: int) -> Decimal:
    """PR2 stub: 返 0 (零售利润不计入 commission breakdown 累计)"""
    return Decimal("0.0000")
