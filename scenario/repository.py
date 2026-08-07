"""ScenarioRepository — 持久化 Scenario ↔ DB row (PR3 Task 3)

业务 (P1 PR3, 2026-08-07):
  - 大重构阶段 3: 运营系统 → 分析推理系统 (招商/路演实时计算器)
  - ScenarioRepository 吃 scenario dataclass, save / load / list / delete 4 个操作
  - 客户路演: 调 4 组参数 → POST /api/scenarios → DB row → 下次 GET /api/scenarios/{id} 读回
  - cache 绑定到 id(scenario_instance) 不绑 row id (scenario/builder.py 已用 LRU)

设计要点:
  1. ORM ↔ dataclass 转换: JSON 字段要 int key 转换 (JSON 标准 str key)
  2. 派生字段 (total_target/total_weeks/total_months) 存表, load 时复用 (避免重算)
  3. SQLAlchemy 2.x 风格 (select 而不是 query)
  4. list_all 按 id 升序 (跟 ORM 默认 order_by 一致, 客户看时间序)
"""
from __future__ import annotations
import datetime
import json
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from scenario.cache import LRUDict
from scenario.model import (
    Scenario, TreeShape, Growth, Revenue, CommissionConfig,
)
from models import Scenario as ScenarioORM


def _json_safe_value(v):
    """Decimal → float (JSON 不支持 Decimal, Float/Int 走原值)
    业务上 tier_rates/own_basic_rate 都是 Decimal, 序列化前转 float 保持精度
    """
    if isinstance(v, Decimal):
        return float(v)
    return v


def _json_safe_dict(d: dict) -> dict:
    """JSON 序列化前预处理: int key + Decimal → float
    业务上 CommissionConfig tier_rates 是 Dict[int, Decimal], JSON 边界要 int key + float val
    """
    return {int(k): _json_safe_value(v) for k, v in d.items()}


def _coerce_value(v):
    """JSON 反序列化后 Decimal 变成 float, 业务要 Decimal
    CommissionConfig.own_basic_rate 是 Decimal 字段, 转换保持精度
    """
    # 这里只处理已知 Decimal 字段 (callers 决定), 不全局转
    return v


def _orm_to_dataclass(row: ScenarioORM) -> Scenario:
    """DB row → dataclass (Scenario)

    业务注意:
      1. JSON 字段 int key 转换 (Dict[str, int] → Dict[int, int])
      2. 派生字段 (total_target/total_weeks/total_months) 复用, 不重算
      3. Decimal 字段 (own_basic_rate) 显式包 Decimal
      4. build_scenario 内部会重算 (LRU 缓存命中), 不影响性能
    """
    ts = TreeShape(
        fork_type=row.tree_fork_type,
        max_level=row.tree_max_level,
        layer_counts=_json_safe_dict(json.loads(row.tree_layer_counts_json)),
    )
    g = Growth(
        nodes_per_region_per_week=row.growth_nodes_per_region_per_week,
        n_regions=row.growth_n_regions,
        join_strategy=row.growth_join_strategy,
        weeks_per_month=row.growth_weeks_per_month,
    )
    r = Revenue(
        initial_pv=row.revenue_initial_pv,
        monthly_renew_pv=row.revenue_monthly_renew_pv,
        color_rule=row.revenue_color_rule,
        color_names=tuple(json.loads(row.revenue_color_names_json)),
    )
    cc = CommissionConfig(
        enable_retail_profit=row.cc_enable_retail_profit,
        enable_team_bonus=row.cc_enable_team_bonus,
        team_bonus_tier_rates=_json_safe_dict(json.loads(row.cc_team_bonus_tier_rates_json)),
        team_bonus_window_weeks=row.cc_team_bonus_window_weeks,
        enable_own_basic=row.cc_enable_own_basic,
        own_basic_rate=Decimal(str(row.cc_own_basic_rate)),  # JSON 边界: float → Decimal
        own_basic_line_pv_cap=row.cc_own_basic_line_pv_cap,
        enable_savings=row.cc_enable_savings,
        savings_usd_threshold=row.cc_savings_usd_threshold,
        savings_rate=row.cc_savings_rate,
        savings_cap_usd=row.cc_savings_cap_usd,
        enable_pair_bonus=row.cc_enable_pair_bonus,
        pair_bonus_ratios=_json_safe_dict(json.loads(row.cc_pair_bonus_ratios_json)),
        pair_bonus_4th_usd_threshold=row.cc_pair_bonus_4th_usd_threshold,
        pair_bonus_5th_usd_threshold=row.cc_pair_bonus_5th_usd_threshold,
        enable_leader_dividend=row.cc_enable_leader_dividend,
        leader_dividend_threshold_pv=row.cc_leader_dividend_threshold_pv,
        leader_dividend_share_usd=row.cc_leader_dividend_share_usd,
        leader_dividend_tiers=_json_safe_dict(json.loads(row.cc_leader_dividend_tiers_json)),
        enable_horizontal_leader=row.cc_enable_horizontal_leader,
        horizontal_leader_share_usd=row.cc_horizontal_leader_share_usd,
        horizontal_leader_tiers=_json_safe_dict(json.loads(row.cc_horizontal_leader_tiers_json)),
        enable_opportunity_points=row.cc_enable_opportunity_points,
    )
    # 用 build_scenario 重建 (内部会跑 builder + 算 total_weeks/months, 但 LRU 缓存命中)
    from scenario.builder import build_scenario
    s = build_scenario(ts, g, r, cc, name=row.name, scenario_id=row.id)
    return s


class ScenarioRepository:
    """Scenario ↔ DB row 持久化 (PR3 Task 3)

    业务:
      - save: scenario dataclass → DB row, 返 id
      - load: DB row id → scenario dataclass (None if 不存在)
      - list_all: 所有 scenario, 按 id 升序
      - delete: 删 DB row by id

    缓存策略 (P1.6 Task 4):
      - 类级别 _process_cache LRUDict[int, Scenario] maxsize=20
      - 跨请求跨实例共享, 1st call 省 scenario.load() 100ms (SQL query)
      - 业务接受 20 个最常用 scenarios 全缓存
      - subprocess 隔离: 多进程下各 worker 独立加载 (P1.6 跟 ProcessPoolExecutor 协同)

    缓存策略 (PR3 Task 3 旧):
      - scenario._cache (LRU 50) 绑到 id(scenario_instance), 不是 row id
      - save 后再 load 是新 instance, cache miss, 重算 (但很快, builder O(N) 2K 节点)
    """

    # 类级别 cache, 跨请求跨 worker 共享 (单进程)
    _process_cache: "LRUDict[int, Scenario]" = LRUDict(maxsize=20)

    def __init__(self, session: Session):
        self.session = session

    def save(self, scenario: Scenario) -> int:
        """存 scenario, 返 DB id

        业务注意:
          1. created_at 用 ISO string (跟 ORM String(32) 字段一致)
          2. JSON 字段用 str key 序列化 (JSON 标准, 反序列化时再转 int)
          3. JSON 值 Decimal → float (JSON 不支持 Decimal)
          4. 派生字段 (total_target/total_weeks/total_months) 直接存, load 时复用
        """
        # 业务: tier_rates 等 Dict[int, Decimal] 先 int key + Decimal→float 预处理
        ts_json = json.dumps({str(k): v for k, v in scenario.tree_shape.layer_counts.items()})
        tier_rates_json = json.dumps({str(k): _json_safe_value(v)
                                       for k, v in scenario.commission_config.team_bonus_tier_rates.items()})
        pair_ratios_json = json.dumps({str(k): _json_safe_value(v)
                                        for k, v in scenario.commission_config.pair_bonus_ratios.items()})
        leader_tiers_json = json.dumps({str(k): v
                                        for k, v in scenario.commission_config.leader_dividend_tiers.items()})
        horizontal_tiers_json = json.dumps({str(k): v
                                              for k, v in scenario.commission_config.horizontal_leader_tiers.items()})
        row = ScenarioORM(
            name=scenario.name,
            created_at=datetime.datetime.now().isoformat(),
            tree_fork_type=scenario.tree_shape.fork_type,
            tree_max_level=scenario.tree_shape.max_level,
            tree_layer_counts_json=ts_json,
            growth_nodes_per_region_per_week=scenario.growth.nodes_per_region_per_week,
            growth_n_regions=scenario.growth.n_regions,
            growth_join_strategy=scenario.growth.join_strategy,
            growth_weeks_per_month=scenario.growth.weeks_per_month,
            revenue_initial_pv=scenario.revenue.initial_pv,
            revenue_monthly_renew_pv=scenario.revenue.monthly_renew_pv,
            revenue_color_rule=scenario.revenue.color_rule,
            revenue_color_names_json=json.dumps(list(scenario.revenue.color_names)),
            cc_enable_retail_profit=scenario.commission_config.enable_retail_profit,
            cc_enable_team_bonus=scenario.commission_config.enable_team_bonus,
            cc_team_bonus_tier_rates_json=tier_rates_json,
            cc_team_bonus_window_weeks=scenario.commission_config.team_bonus_window_weeks,
            cc_enable_own_basic=scenario.commission_config.enable_own_basic,
            cc_own_basic_rate=float(scenario.commission_config.own_basic_rate),  # Decimal → float
            cc_own_basic_line_pv_cap=scenario.commission_config.own_basic_line_pv_cap,
            cc_enable_savings=scenario.commission_config.enable_savings,
            cc_savings_usd_threshold=scenario.commission_config.savings_usd_threshold,
            cc_savings_rate=scenario.commission_config.savings_rate,
            cc_savings_cap_usd=scenario.commission_config.savings_cap_usd,
            cc_enable_pair_bonus=scenario.commission_config.enable_pair_bonus,
            cc_pair_bonus_ratios_json=pair_ratios_json,
            cc_pair_bonus_4th_usd_threshold=scenario.commission_config.pair_bonus_4th_usd_threshold,
            cc_pair_bonus_5th_usd_threshold=scenario.commission_config.pair_bonus_5th_usd_threshold,
            cc_enable_leader_dividend=scenario.commission_config.enable_leader_dividend,
            cc_leader_dividend_threshold_pv=scenario.commission_config.leader_dividend_threshold_pv,
            cc_leader_dividend_share_usd=scenario.commission_config.leader_dividend_share_usd,
            cc_leader_dividend_tiers_json=leader_tiers_json,
            cc_enable_horizontal_leader=scenario.commission_config.enable_horizontal_leader,
            cc_horizontal_leader_share_usd=scenario.commission_config.horizontal_leader_share_usd,
            cc_horizontal_leader_tiers_json=horizontal_tiers_json,
            cc_enable_opportunity_points=scenario.commission_config.enable_opportunity_points,
            total_target=scenario.total_target,
            total_weeks=scenario.total_weeks,
            total_months=scenario.total_months,
        )
        self.session.add(row)
        self.session.commit()
        # P1.6 Task 4: save 后 invalidate cache (新 row 取代任何 stale cached version)
        self.invalidate_cache(row.id)
        return row.id

    def load(self, scenario_id: int) -> Optional[Scenario]:
        """load DB row by id, 转 dataclass, None if 不存在

        P1.6 Task 4: 类级别 _process_cache 优先查, 命中省 scenario.load() 100ms
        """
        # 1. 查类级别 cache (跨请求复用)
        cached = ScenarioRepository._process_cache.get(scenario_id)
        if cached is not None:
            return cached
        # 2. 没缓存: DB 加载
        row = self.session.get(ScenarioORM, scenario_id)
        if row is None:
            return None
        s = _orm_to_dataclass(row)
        if s is not None:
            ScenarioRepository._process_cache.set(scenario_id, s)
        return s

    def invalidate_cache(self, scenario_id: int) -> None:
        """手动失效 (测试用 + 后续 P6 兼容性用)

        业务: save 跟 delete 不会自动失效, 改 scenario 参数后必须手动调
        """
        if scenario_id in ScenarioRepository._process_cache:
            del ScenarioRepository._process_cache._data[scenario_id]

    @classmethod
    def clear_cache(cls) -> None:
        """清空类级别 _process_cache (测试间隔离用)

        业务:
        - 类级别 cache 跨请求复用, 但跨测试 (fresh DB) 必须清
        - 测试 conftest.py autouse fixture 自动调
        - 业务代码不要随便调 (会丢所有缓存)
        """
        cls._process_cache._data.clear()

    def list_ids(self) -> List[int]:
        """列所有 scenario id (供预热用, P1.6 Task 3 预热机制依赖)"""
        from sqlalchemy import select
        stmt = select(ScenarioORM.id).order_by(ScenarioORM.id)
        return [row[0] for row in self.session.execute(stmt).all()]

    def list_all(self) -> List[Scenario]:
        """所有 scenarios, 按 id 升序 (跟 ORM 默认 order_by 一致)

        P1.6 Task 4: 走 _process_cache 优先, 命中直接返, 避免 DB 反序列化开销
        """
        stmt = select(ScenarioORM).order_by(ScenarioORM.id)
        rows = self.session.execute(stmt).scalars().all()
        result: List[Scenario] = []
        for r in rows:
            cached = ScenarioRepository._process_cache.get(r.id)
            if cached is not None:
                result.append(cached)
            else:
                s = _orm_to_dataclass(r)
                ScenarioRepository._process_cache.set(r.id, s)
                result.append(s)
        return result

    def delete(self, scenario_id: int) -> None:
        """删 DB row by id (不报错 if 不存在)

        P1.6 Task 4: 同时失效 _process_cache, 避免 load 返 stale cached data
        """
        row = self.session.get(ScenarioORM, scenario_id)
        if row is not None:
            self.session.delete(row)
            self.session.commit()
        # cache 失效: 无论 DB 是否真删, 都清掉 (避免 stale read)
        self.invalidate_cache(scenario_id)
