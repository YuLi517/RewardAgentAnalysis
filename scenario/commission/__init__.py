"""scenario 业务算法子包 (PR2 + v1.0.12 加 1代4)"""
from scenario.commission.own_basic import compute_own_basic_for_node
from scenario.commission.pair_bonus import compute_pair_bonus_for_node
from scenario.commission.team_bonus import compute_team_bonus_for_node
from scenario.commission.savings import compute_savings_for_node
from scenario.commission.leader import compute_leader_dividend_for_node
from scenario.commission.horizontal import compute_horizontal_for_node
from scenario.commission.retail_profit import compute_retail_profit_for_node
from scenario.commission.opportunity import compute_opportunity_for_node
from scenario.commission.one_gen_four import compute_one_gen_four_for_node  # v1.0.12

__all__ = [
    "compute_own_basic_for_node",
    "compute_pair_bonus_for_node",
    "compute_team_bonus_for_node",
    "compute_savings_for_node",
    "compute_leader_dividend_for_node",
    "compute_horizontal_for_node",
    "compute_retail_profit_for_node",
    "compute_opportunity_for_node",
    "compute_one_gen_four_for_node",  # v1.0.12 第 9 种
]
