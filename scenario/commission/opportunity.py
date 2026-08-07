"""第 8 种: 机遇积分 (用户 2026-08-07 拍板第 8 种报酬方式)
PR2 阶段: stub 返 0 (业务规则未拍板, raise NotImplementedError when enabled)
"""
from scenario.model import Scenario


def compute_opportunity_for_node(scenario: Scenario, bfs_id: int, month: int) -> int:
    """PR2 stub: 返 0. 业务规则用户未拍板, 启用时 raise NotImplementedError"""
    if scenario.commission_config.enable_opportunity_points:
        raise NotImplementedError(
            "机遇积分 (第 8 种) 业务规则用户未拍板, 暂未实现. 业务上下文: 用户 2026-08-07 brainstorming"
        )
    return 0
