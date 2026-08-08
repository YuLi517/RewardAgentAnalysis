"""v1.0.14 (2026-08-08): 1代4 商品价值 (新第 9 种报酬, 凑齐 + 1 月触发, 4 子锁定查表)

业务拍板 (用户 2026-08-08):
  1. 触发条件: 父节点 (非叶) 在 month 月"长出树"上 BFS 凑齐 4 个最近子
     - "长出树" = 父节点为根的子树 (不含父节点自己, 含子孙)
     - "BFS 凑齐 4 个最近" = 按 BFS 距离优先, slot 1-5 顺序
  2. 奖励金额: 95 PV (固定, 公司随机商品 80-110 PV 取中值)
  3. 触发频率: 凑齐 4 子后下个月起, 每月都拿 95 PV (持续)
  4. 首次触发延迟 + 1 月 (v1.0.13): 凑齐 4 子那个月 + 1 月才触发
  5. 4 子关系固定 (v1.0.14): 凑齐 4 子时刻, 4 个 bfs_id + M_first 锁定到 scenario.locks_json

v1.0.14 关键变更 (用户 2026-08-08 第 5 轮澄清):
  - 4 子关系 = scenario 树形属性, 跟 layer_counts 一样持久化
  - 业务动机: 用户担心每次动态 BFS 可能出错, 4 子集合可能微变
  - 实施: scenario POST 预计算 locks 写 DB, 1代4 计算 = 查表 locks, 0 BFS, 0 误差
  - 旧 134 scenario lazy backfill: 首次 GET 时算 + UPDATE DB

算法:
  - 4 子关系 = 预计算 (DB one_gen_four_locks_json)
  - 凑齐月份 M_first = max(join_month of 4 子) (同 v1.0.13)
  - 触发月 = month >= M_first + 1 (同 v1.0.13)
  - 全网 sum 时多个父节点独立查表, 累加

设计参考: 跟 team_bonus 一样是"父节点培养下线奖励",
          但金额固定 95 PV (跟 4 档精确匹配无关)
          首次触发延迟 1 月 反映 "子节点 100 PV 续费" 业务背景
          v1.0.14 4 子锁定 反映 "业务上 4 子关系确定性" 业务动机
"""
from __future__ import annotations
from decimal import Decimal
from typing import Dict

from scenario.model import Scenario
from scenario.locks import get_lock_for_node, compute_one_gen_four_locks


# 1代4 商品价值 (固定, 中间值)
ONE_GEN_FOUR_GOODS_PV = Decimal("95")


def compute_one_gen_four_for_node(scenario: Scenario, bfs_id: int, month: int) -> Decimal:
    """单节点 API: bfs_id 在 month 月触发 1代4 → 95 PV, 否则 0

    业务 (v1.0.14):
      - 查 locks 找 bfs_id 的 4 子 + M_first (不再动态 BFS)
      - 触发月 = month >= M_first + 1 (凑齐后下个月起)
      - 后续月持续触发 (4 子都还在线, 业务默认都续费)
      - month < M_first + 1 → 0
    """
    lock = get_lock_for_node(scenario, bfs_id)
    if lock is None:
        return Decimal("0")  # 叶子 / 凑不齐 4 子
    m_first = lock["m_first"]
    if month < m_first + 1:
        return Decimal("0")
    return ONE_GEN_FOUR_GOODS_PV


def compute_one_gen_four_table_for_month(scenario: Scenario, month: int) -> Dict[int, Decimal]:
    """P1.5 全网表: 1 次算全网 2144 节点 1代4 触发情况
    v1.0.14: 查 locks 表, 不动态 BFS
    缓存机制 (跟其他 commission 一样)
    """
    cache_key = ("one_gen_four_table", id(scenario), month)
    if not hasattr(compute_one_gen_four_table_for_month, "_cache"):
        compute_one_gen_four_table_for_month._cache = {}  # type: ignore
    cache = compute_one_gen_four_table_for_month._cache  # type: ignore
    if cache_key in cache:
        return cache[cache_key]

    # 1. 1 次算全网 locks (查表 / backfill / cache, < 100ms)
    locks = compute_one_gen_four_locks(scenario)
    # 2. 全网表, 每个 bfs_id 查表
    nodes_dict = {bid: True for bid in locks.keys()}  # 简化: 只算有 lock 的父节点
    result: Dict[int, Decimal] = {}
    for bfs_id in locks.keys():
        lock = locks[bfs_id]
        m_first = lock["m_first"]
        if month < m_first + 1:
            result[bfs_id] = Decimal("0")
        else:
            result[bfs_id] = ONE_GEN_FOUR_GOODS_PV
    # 3. 没 lock 的节点 (叶子 / 凑不齐) 默认 0
    #    注意: 上游 compute_month_overview 用 .get(bfs_id, 0) 处理, 缺 key = 0
    #    所以这里只填有 lock 的 bfs_id, 叶子自动 0

    cache[cache_key] = result
    return result
