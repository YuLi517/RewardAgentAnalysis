"""Scenario HTTP 路由 (PR3 Task 4) — 3 个路由, 接入 FastAPI app

业务 (P1 PR3, 2026-08-07):
  - 大重构阶段 3: 运营系统 → 分析推理系统 (招商/路演实时计算器)
  - 3 个路由:
    1. POST /api/scenarios — 客户调 4 组参数, 建场景
    2. GET /api/scenarios/{id}/state?month=&bfs_id= — 节点当月 8 种报酬明细
    3. GET /api/scenarios/{id}/overview?month= — 当月全网 8 种合计
  - 跟 main.py 集成: app.include_router(scenario_routes.router)

设计要点:
  1. Pydantic v2 风格 (model_dump 而不是 dict)
  2. JSON 字段用 Dict[str, int/float] (Pydantic 友好), 内部转 int key
  3. 路由独立文件, main.py 0 改动除 include_router
  4. Decimal 边界: own_basic_rate Float Pydantic → Decimal CommissionConfig
  5. 404 if scenario_id 不存在 (跟 FastAPI 惯例一致)
"""
from __future__ import annotations
from decimal import Decimal
from typing import Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from scenario.builder import build_scenario
from scenario.repository import ScenarioRepository
from scenario.breakdown import compute_commission_breakdown
from scenario.overview import compute_month_overview
from scenario.parallel import compute_overview_all_parallel
from scenario.model import (
    TreeShape, Growth, Revenue, CommissionConfig,
)


router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


# --- Pydantic v2 models (request body) ---
# JSON 字段用 Dict[str, int/float] (Pydantic 友好), 内部用 _int_keys 统一转 int

class TreeShapeIn(BaseModel):
    fork_type: str
    max_level: int
    layer_counts: Dict[str, int]


class GrowthIn(BaseModel):
    nodes_per_region_per_week: int
    n_regions: int
    join_strategy: str
    weeks_per_month: int


class RevenueIn(BaseModel):
    initial_pv: int
    monthly_renew_pv: int
    color_rule: str
    color_names: List[str]


class CommissionConfigIn(BaseModel):
    enable_retail_profit: bool
    enable_team_bonus: bool
    team_bonus_tier_rates: Dict[str, float]
    team_bonus_window_weeks: int
    enable_own_basic: bool
    own_basic_rate: float
    own_basic_line_pv_cap: int
    enable_savings: bool
    savings_usd_threshold: float
    savings_rate: float
    savings_cap_usd: float
    enable_pair_bonus: bool
    pair_bonus_ratios: Dict[str, float]
    pair_bonus_4th_usd_threshold: float
    pair_bonus_5th_usd_threshold: float
    enable_leader_dividend: bool
    leader_dividend_threshold_pv: int
    leader_dividend_share_usd: float
    leader_dividend_tiers: Dict[str, int]
    enable_horizontal_leader: bool
    horizontal_leader_share_usd: float
    horizontal_leader_tiers: Dict[str, int]
    enable_opportunity_points: bool


class ScenarioIn(BaseModel):
    name: str
    tree_shape: TreeShapeIn
    growth: GrowthIn
    revenue: RevenueIn
    commission_config: CommissionConfigIn


# --- Helpers ---

def _int_keys(d: Dict[str, Any]) -> Dict[int, Any]:
    """JSON object key 总是 string, 但业务要求 int key
    路由边界: HTTP body JSON 进来 key 是 str, 内部统一转 int"""
    return {int(k): v for k, v in d.items()}


# --- Routes ---

@router.post("", status_code=201)
def create_scenario(body: ScenarioIn, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """建场景: 4 组参数 → DB 存 1 行, 返 {id, name}

    业务:
      1. body dict 4 组参数 → TreeShape/Growth/Revenue/CommissionConfig
      2. build_scenario 算 total_target/total_weeks/total_months
      3. ScenarioRepository.save 拍平 40 列存 DB
      4. 返 {id, name} (id 是新 row pk)
    """
    ts = TreeShape(
        fork_type=body.tree_shape.fork_type,
        max_level=body.tree_shape.max_level,
        layer_counts=_int_keys(body.tree_shape.layer_counts),
    )
    g = Growth(
        nodes_per_region_per_week=body.growth.nodes_per_region_per_week,
        n_regions=body.growth.n_regions,
        join_strategy=body.growth.join_strategy,
        weeks_per_month=body.growth.weeks_per_month,
    )
    r = Revenue(
        initial_pv=body.revenue.initial_pv,
        monthly_renew_pv=body.revenue.monthly_renew_pv,
        color_rule=body.revenue.color_rule,
        color_names=tuple(body.revenue.color_names),
    )
    # Pydantic v2: model_dump() 而不是 .dict()
    cc_data = body.commission_config.model_dump()
    # 拆分: 4 个 dict 字段转 int key, 其余标量
    cc_scalar = {k: v for k, v in cc_data.items()
                 if k not in ("team_bonus_tier_rates", "pair_bonus_ratios",
                              "leader_dividend_tiers", "horizontal_leader_tiers")}
    # own_basic_rate 是 Float (Pydantic), 业务用 Decimal
    cc_scalar["own_basic_rate"] = Decimal(str(cc_scalar["own_basic_rate"]))
    cc = CommissionConfig(
        **cc_scalar,
        team_bonus_tier_rates=_int_keys(cc_data["team_bonus_tier_rates"]),
        pair_bonus_ratios=_int_keys(cc_data["pair_bonus_ratios"]),
        leader_dividend_tiers=_int_keys(cc_data["leader_dividend_tiers"]),
        horizontal_leader_tiers=_int_keys(cc_data["horizontal_leader_tiers"]),
    )
    s = build_scenario(ts, g, r, cc, name=body.name)
    # v1.0.14: 预计算 1代4 4 子锁定 (1 次 BFS 算全网, 写 DB JSON 字段)
    # 业务: 1代4 计算 = 查表 locks, 不再每次 BFS (避免出错 + 性能)
    from scenario.locks import compute_one_gen_four_locks, serialize_locks
    locks = compute_one_gen_four_locks(s)
    s._db_locks_json = serialize_locks(locks)
    repo = ScenarioRepository(db)
    scenario_id = repo.save(s)
    return {"id": scenario_id, "name": body.name}


@router.get("/{scenario_id}/state")
def get_state(scenario_id: int,
              month: int = Query(..., ge=0),
              bfs_id: int = Query(..., ge=0),
              db: Session = Depends(get_db)) -> Dict[str, Any]:
    """取节点状态: scenario_id + month + bfs_id → CommissionBreakdown JSON

    业务:
      1. 加载 scenario (4 组参数 + 派生 from DB)
      2. compute_commission_breakdown 算当月节点 9 种报酬 (v1.0.12 加 1代4) + 累计
      3. Decimal 字段 str 化 (JSON 不支持 Decimal)
    """
    repo = ScenarioRepository(db)
    s = repo.load(scenario_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"scenario {scenario_id} not found")
    cb = compute_commission_breakdown(s, bfs_id=bfs_id, month=month)
    return {
        "bfs_id": cb.bfs_id,
        "month": cb.month,
        "own_basic_usd": str(cb.own_basic_usd),
        "pair_bonus_usd": str(cb.pair_bonus_usd),
        "team_bonus_usd": str(cb.team_bonus_usd),
        "savings_usd": str(cb.savings_usd),
        "leader_dividend_usd": str(cb.leader_dividend_usd),
        "horizontal_leader_usd": str(cb.horizontal_leader_usd),
        "retail_profit_usd": str(cb.retail_profit_usd),
        "opportunity_points": cb.opportunity_points,
        "one_gen_four_usd": str(cb.one_gen_four_usd),  # v1.0.12: 1代4 商品价值
        "total_usd": str(cb.total_usd),
        "ip_chain_status": cb.ip_chain_status,
        "is_optimized_region": cb.is_optimized_region,
        "cumulative_to_date_usd": str(cb.cumulative_to_date_usd),
    }


@router.get("/{scenario_id}/overview")
def get_overview(scenario_id: int,
                 month: int = Query(..., ge=0),
                 db: Session = Depends(get_db)) -> Dict[str, Any]:
    """取当月全网总览: scenario_id + month → 9 种合计 (v1.0.12 加 1代4)

    业务:
      1. 加载 scenario
      2. compute_month_overview 算当月全网 9 种合计
      3. Decimal 字段 str 化
    """
    repo = ScenarioRepository(db)
    s = repo.load(scenario_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"scenario {scenario_id} not found")
    overview = compute_month_overview(s, month=month)
    return {k: str(v) for k, v in overview.items()}


@router.get("/{scenario_id}/overview/all")
def get_overview_all(scenario_id: int,
                     total_months: int = Query(14, ge=1, le=15),
                     db: Session = Depends(get_db)) -> Dict[str, Any]:
    """取 scenario 0-total_months 月的 9 报酬 × 月 矩阵 (heatmap 渲染用)

    业务 (P3 PR2 + P1.5 + v1.0.12):
      - P3 PR2: 1 次算 14 月 × 8 报酬 = 112 值 (避免前端 14 次串行 GET)
      - P1.5: ThreadPoolExecutor 14 worker 并行, 14 月 14 分钟 → 10 秒内
      - P1.6: ProcessPoolExecutor GIL-free 真正并行, 1st < 150ms
      - v1.0.12: 9 报酬 (加 1代4) = 126 值
      - 矩阵按字段分组, 返 15 个 string (0-14 月)
    """
    repo = ScenarioRepository(db)
    s = repo.load(scenario_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"scenario {scenario_id} not found")
    # P1.5: ThreadPoolExecutor 14 worker 并行 (从 14 分钟 → 10 秒)
    return compute_overview_all_parallel(s, total_months)


@router.get("", response_class=PlainTextResponse)
def list_scenarios_csv(db: Session = Depends(get_db)) -> PlainTextResponse:
    """列所有 scenarios (CSV 格式, 简单列表)

    Returns:
        text/csv, 1 行 header + N 行数据
        id,name,created_at,total_target,total_weeks,total_months
    """
    from models import Scenario
    from sqlalchemy import select
    rows = db.execute(select(Scenario).order_by(Scenario.id)).scalars().all()
    lines = ["id,name,created_at,total_target,total_weeks,total_months"]
    for r in rows:
        lines.append(f"{r.id},{r.name},{r.created_at},{r.total_target},{r.total_weeks},{r.total_months}")
    return PlainTextResponse("\n".join(lines), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=scenarios.csv"})


@router.get("/{scenario_id}/export/csv", response_class=PlainTextResponse)
def export_scenario_csv(scenario_id: int,
                        total_months: int = Query(14, ge=1, le=15),
                        db: Session = Depends(get_db)) -> PlainTextResponse:
    """导出 scenario overview 14 月 × 9 报酬 = 126 行 CSV (v1.0.12 加 1代4)
    """
    from scenario.repository import ScenarioRepository
    repo = ScenarioRepository(db)
    s = repo.load(scenario_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"scenario {scenario_id} not found")
    fields = ["ownBasic", "pairBonus", "teamBonus", "savings",
              "leader", "horizontal", "retail", "oneGenFour", "total"]
    lines = ["scenario_id,scenario_name,month,field,value"]
    for m in range(0, total_months + 1):
        ov = compute_month_overview(s, month=m)
        for f in fields:
            v = ov.get(f, "0")
            lines.append(f"{s.id},{s.name},{m},{f},{v}")
    return PlainTextResponse("\n".join(lines), media_type="text/csv",
                                 headers={"Content-Disposition":
                                          f"attachment; filename=scenario_{s.id}_overview.csv"})
