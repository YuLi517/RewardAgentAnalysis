# P1 PR3 — scenarios 表 + 3 个 HTTP 路由 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把 scenario 引擎接入 FastAPI, 加 3 个 HTTP 路由 (POST/GET/GET), 场景数据持久化到 SQLite scenarios 表 (40 列拍平)。LRU 缓存命中率 ≥ 60% (路演场景)。

**Architecture:** `scenario/repository.py` (CRUD) + `scenario_routes.py` (3 个 FastAPI 路由, 新文件不修改 main.py) + migration 工具 idempotent 创表。LRU 缓存绑定到 `id(scenario)` 防内存泄漏。

**Tech Stack:** FastAPI, SQLAlchemy, SQLite, pydantic

**Spec:** `docs/superpowers/specs/2026-08-07-p1-scenario-engine-design.md` §4.3

---

## File Structure

| 文件 | 责任 |
|---|---|
| `scenario/repository.py` | ScenarioRepository: save / load / list / delete, 吃 scenario dataclass 返 DB row + 反向 |
| `scenario_routes.py` | 3 个 FastAPI 路由: POST /api/scenarios + 2 × GET |
| `tools/migrate_add_scenarios_table.py` | idempotent, 创 scenarios 表 (40 列) |
| `models.py` (Modify) | 加 Scenario ORM model (40 列) |
| `tests/test_scenario_repository.py` | 5+ 用例: save/load/list/delete |
| `tests/test_scenario_routes.py` | httpx 异步测试 3 个路由 |

---

## Task 1: 加 Scenario ORM model (40 列)

**Files:**
- Modify: `models.py`

- [ ] **Step 1: 读 models.py 末尾, 找添加位置**

Run: `Get-Content models.py -Tail 30`

- [ ] **Step 2: 加 Scenario ORM class (40 列)**

在 models.py 末尾追加 (假设其他 ORM 用同样的 declarative_base):
```python
class Scenario(Base):
    """场景: 4 组参数拍平 40 列, 客户路演实时调参用
    PR3 加 (2026-08-07 P1 场景核心引擎)
    """
    __tablename__ = "scenarios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    created_at = Column(String(32), nullable=False)

    # tree_shape
    tree_fork_type = Column(String(16), nullable=False)
    tree_max_level = Column(Integer, nullable=False)
    tree_layer_counts_json = Column(Text, nullable=False)

    # growth
    growth_nodes_per_region_per_week = Column(Integer, nullable=False)
    growth_n_regions = Column(Integer, nullable=False)
    growth_join_strategy = Column(String(32), nullable=False)
    growth_weeks_per_month = Column(Integer, nullable=False)

    # revenue
    revenue_initial_pv = Column(Integer, nullable=False)
    revenue_monthly_renew_pv = Column(Integer, nullable=False)
    revenue_color_rule = Column(String(32), nullable=False)
    revenue_color_names_json = Column(Text, nullable=False)

    # commission_config
    cc_enable_retail_profit = Column(Boolean, nullable=False)
    cc_enable_team_bonus = Column(Boolean, nullable=False)
    cc_team_bonus_tier_rates_json = Column(Text, nullable=False)
    cc_team_bonus_window_weeks = Column(Integer, nullable=False)
    cc_enable_own_basic = Column(Boolean, nullable=False)
    cc_own_basic_rate = Column(Float, nullable=False)
    cc_own_basic_line_pv_cap = Column(Integer, nullable=False)
    cc_enable_savings = Column(Boolean, nullable=False)
    cc_savings_usd_threshold = Column(Float, nullable=False)
    cc_savings_rate = Column(Float, nullable=False)
    cc_savings_cap_usd = Column(Float, nullable=False)
    cc_enable_pair_bonus = Column(Boolean, nullable=False)
    cc_pair_bonus_ratios_json = Column(Text, nullable=False)
    cc_pair_bonus_4th_usd_threshold = Column(Float, nullable=False)
    cc_pair_bonus_5th_usd_threshold = Column(Float, nullable=False)
    cc_enable_leader_dividend = Column(Boolean, nullable=False)
    cc_leader_dividend_threshold_pv = Column(Integer, nullable=False)
    cc_leader_dividend_share_usd = Column(Float, nullable=False)
    cc_leader_dividend_tiers_json = Column(Text, nullable=False)
    cc_enable_horizontal_leader = Column(Boolean, nullable=False)
    cc_horizontal_leader_share_usd = Column(Float, nullable=False)
    cc_horizontal_leader_tiers_json = Column(Text, nullable=False)
    cc_enable_opportunity_points = Column(Boolean, nullable=False)

    # 派生
    total_target = Column(Integer, nullable=False)
    total_weeks = Column(Integer, nullable=False)
    total_months = Column(Integer, nullable=False)
```

- [ ] **Step 3: 跑现有测试, 确认 models.py 改动不破坏旧 ORM**

Run: `pytest tests/test_db_admin.py -v`
Expected: 1+ 个测试全过

- [ ] **Step 4: Commit**

```bash
git add models.py
git commit -m "feat(models): PR3 Task 1 — Scenario ORM (40 列, scenarios 表)"
```

---

## Task 2: migration 工具 (idempotent 创表)

**Files:**
- Create: `tools/migrate_add_scenarios_table.py`
- Test: `tests/test_migrate_scenarios.py`

- [ ] **Step 1: 写失败测试**

写 `tests/test_migrate_scenarios.py`:
```python
import os
import tempfile
from sqlalchemy import create_engine
from tools.migrate_add_scenarios_table import upgrade


def test_upgrade_idempotent():
    """升级: 创建 scenarios 表; 重复调用不报错"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        engine = create_engine(f"sqlite:///{path}")
        upgrade(engine)  # 第一次: 创表
        upgrade(engine)  # 第二次: 跳过 (表已存在)
        # 验证表存在
        with engine.connect() as conn:
            result = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scenarios'")
            assert result.fetchone() is not None
    finally:
        os.unlink(path)
```

- [ ] **Step 2: 跑测试, 确认失败**

Run: `pytest tests/test_migrate_scenarios.py -v`
Expected: ModuleNotFoundError: No module named 'tools.migrate_add_scenarios_table'

- [ ] **Step 3: 写 tools/migrate_add_scenarios_table.py**

```python
"""scenarios 表 migration 工具 (PR3)
Idempotent: 重复调用不报错
"""
from sqlalchemy import inspect


def upgrade(engine):
    """创 scenarios 表 (40 列, 跟 models.py:Scenario 一致)
    重复调用跳过 (idempotent)
    """
    insp = inspect(engine)
    if "scenarios" in insp.get_table_names():
        print("[migrate] scenarios 表已存在, 跳过")
        return

    with engine.begin() as conn:
        conn.execute("""
            CREATE TABLE scenarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                tree_fork_type TEXT NOT NULL,
                tree_max_level INTEGER NOT NULL,
                tree_layer_counts_json TEXT NOT NULL,
                growth_nodes_per_region_per_week INTEGER NOT NULL,
                growth_n_regions INTEGER NOT NULL,
                growth_join_strategy TEXT NOT NULL,
                growth_weeks_per_month INTEGER NOT NULL,
                revenue_initial_pv INTEGER NOT NULL,
                revenue_monthly_renew_pv INTEGER NOT NULL,
                revenue_color_rule TEXT NOT NULL,
                revenue_color_names_json TEXT NOT NULL,
                cc_enable_retail_profit BOOLEAN NOT NULL,
                cc_enable_team_bonus BOOLEAN NOT NULL,
                cc_team_bonus_tier_rates_json TEXT NOT NULL,
                cc_team_bonus_window_weeks INTEGER NOT NULL,
                cc_enable_own_basic BOOLEAN NOT NULL,
                cc_own_basic_rate REAL NOT NULL,
                cc_own_basic_line_pv_cap INTEGER NOT NULL,
                cc_enable_savings BOOLEAN NOT NULL,
                cc_savings_usd_threshold REAL NOT NULL,
                cc_savings_rate REAL NOT NULL,
                cc_savings_cap_usd REAL NOT NULL,
                cc_enable_pair_bonus BOOLEAN NOT NULL,
                cc_pair_bonus_ratios_json TEXT NOT NULL,
                cc_pair_bonus_4th_usd_threshold REAL NOT NULL,
                cc_pair_bonus_5th_usd_threshold REAL NOT NULL,
                cc_enable_leader_dividend BOOLEAN NOT NULL,
                cc_leader_dividend_threshold_pv INTEGER NOT NULL,
                cc_leader_dividend_share_usd REAL NOT NULL,
                cc_leader_dividend_tiers_json TEXT NOT NULL,
                cc_enable_horizontal_leader BOOLEAN NOT NULL,
                cc_horizontal_leader_share_usd REAL NOT NULL,
                cc_horizontal_leader_tiers_json TEXT NOT NULL,
                cc_enable_opportunity_points BOOLEAN NOT NULL,
                total_target INTEGER NOT NULL,
                total_weeks INTEGER NOT NULL,
                total_months INTEGER NOT NULL
            )
        """)
    print("[migrate] scenarios 表创建成功")


if __name__ == "__main__":
    from database import engine
    upgrade(engine)
```

- [ ] **Step 4: 跑测试, 确认通过**

Run: `pytest tests/test_migrate_scenarios.py -v`
Expected: 1 passed

- [ ] **Step 5: 跑 migration 在 live DB**

Run: `python tools/migrate_add_scenarios_table.py`
Expected: 输出 "[migrate] scenarios 表创建成功" 或 "[migrate] scenarios 表已存在, 跳过"

- [ ] **Step 6: Commit**

```bash
git add tools/migrate_add_scenarios_table.py tests/test_migrate_scenarios.py
git commit -m "feat(scenario): PR3 Task 2 — migrate_add_scenarios_table (idempotent 创 40 列表)"
```

---

## Task 3: scenario/repository.py (CRUD)

**Files:**
- Create: `scenario/repository.py`
- Test: `tests/test_scenario_repository.py`

- [ ] **Step 1: 写失败测试**

写 `tests/test_scenario_repository.py`:
```python
import os
import tempfile
import json
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from tools.migrate_add_scenarios_table import upgrade
from scenario.repository import ScenarioRepository
from scenario.model import TreeShape, Growth, Revenue, CommissionConfig
from scenario.builder import build_scenario


def _make_engine_with_table():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    upgrade(engine)
    return engine, path


def _make_scenario():
    ts = TreeShape("binary", 10, {0: 1, 1: 4, 2: 8})
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(1500, 100, "4_color_cycle", ("红", "紫", "青绿", "蓝"))
    cc = CommissionConfig(
        False, True, {200: 0.15}, 4, True, Decimal("0.15"), 13334,
        False, 250.0, 0.15, 500.0, False, {}, 500.0, 1000.0,
        False, 13334, 500.0, {}, False, 250.0, {}, False,
    )
    return build_scenario(ts, g, r, cc, name="test_save_load")


def test_save_load_roundtrip():
    engine, path = _make_engine_with_table()
    try:
        Session = sessionmaker(bind=engine)
        with Session() as session:
            repo = ScenarioRepository(session)
            s = _make_scenario()
            scenario_id = repo.save(s)
            assert scenario_id > 0
        # Load
        with Session() as session:
            repo = ScenarioRepository(session)
            loaded = repo.load(scenario_id)
            assert loaded.name == "test_save_load"
            assert loaded.tree_shape.fork_type == "binary"
            assert loaded.growth.n_regions == 4
            assert loaded.revenue.initial_pv == 1500
            assert loaded.commission_config.enable_team_bonus is True
            assert loaded.total_target == 1 + 4 + 8
    finally:
        os.unlink(path)


def test_list_scenarios():
    engine, path = _make_engine_with_table()
    try:
        Session = sessionmaker(bind=engine)
        with Session() as session:
            repo = ScenarioRepository(session)
            s1 = _make_scenario()
            s1_name = "list_test_1"
            s1_new = type(s1)(id=None, name=s1_name, **{k: v for k, v in s1.__dict__.items() if k not in ('id', 'name')})
            repo.save(s1_new)
        with Session() as session:
            repo = ScenarioRepository(session)
            items = repo.list_all()
            assert len(items) >= 1
            assert any(it.name == "list_test_1" for it in items)
    finally:
        os.unlink(path)


def test_delete_scenario():
    engine, path = _make_engine_with_table()
    try:
        Session = sessionmaker(bind=engine)
        with Session() as session:
            repo = ScenarioRepository(session)
            s = _make_scenario()
            sid = repo.save(s)
        with Session() as session:
            repo = ScenarioRepository(session)
            repo.delete(sid)
        with Session() as session:
            repo = ScenarioRepository(session)
            assert repo.load(sid) is None
    finally:
        os.unlink(path)
```

- [ ] **Step 2: 跑测试, 确认失败**

Run: `pytest tests/test_scenario_repository.py -v`
Expected: ModuleNotFoundError

- [ ] **Step 3: 写 scenario/repository.py**

```python
"""ScenarioRepository — 持久化 Scenario ↔ DB row (PR3)"""
from __future__ import annotations
import json
import datetime
from typing import List, Optional

from scenario.model import (
    Scenario, TreeShape, Growth, Revenue, CommissionConfig,
)
from models import Scenario as ScenarioORM


def _orm_to_dataclass(row: ScenarioORM) -> Scenario:
    """DB row → dataclass"""
    ts = TreeShape(
        fork_type=row.tree_fork_type,
        max_level=row.tree_max_level,
        layer_counts={int(k): v for k, v in json.loads(row.tree_layer_counts_json).items()},
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
        team_bonus_tier_rates={int(k): v for k, v in json.loads(row.cc_team_bonus_tier_rates_json).items()},
        team_bonus_window_weeks=row.cc_team_bonus_window_weeks,
        enable_own_basic=row.cc_enable_own_basic,
        own_basic_rate=row.cc_own_basic_rate,
        own_basic_line_pv_cap=row.cc_own_basic_line_pv_cap,
        enable_savings=row.cc_enable_savings,
        savings_usd_threshold=row.cc_savings_usd_threshold,
        savings_rate=row.cc_savings_rate,
        savings_cap_usd=row.cc_savings_cap_usd,
        enable_pair_bonus=row.cc_enable_pair_bonus,
        pair_bonus_ratios={int(k): v for k, v in json.loads(row.cc_pair_bonus_ratios_json).items()},
        pair_bonus_4th_usd_threshold=row.cc_pair_bonus_4th_usd_threshold,
        pair_bonus_5th_usd_threshold=row.cc_pair_bonus_5th_usd_threshold,
        enable_leader_dividend=row.cc_enable_leader_dividend,
        leader_dividend_threshold_pv=row.cc_leader_dividend_threshold_pv,
        leader_dividend_share_usd=row.cc_leader_dividend_share_usd,
        leader_dividend_tiers={int(k): v for k, v in json.loads(row.cc_leader_dividend_tiers_json).items()},
        enable_horizontal_leader=row.cc_enable_horizontal_leader,
        horizontal_leader_share_usd=row.cc_horizontal_leader_share_usd,
        horizontal_leader_tiers={int(k): v for k, v in json.loads(row.cc_horizontal_leader_tiers_json).items()},
        enable_opportunity_points=row.cc_enable_opportunity_points,
    )
    # 重建 Scenario (load 时不重算, build_scenario 内部会跑一次)
    from scenario.builder import build_scenario
    s = build_scenario(ts, g, r, cc, name=row.name, scenario_id=row.id)
    return s


class ScenarioRepository:
    def __init__(self, session):
        self.session = session

    def save(self, scenario: Scenario) -> int:
        """存 scenario, 返 DB id"""
        row = ScenarioORM(
            name=scenario.name,
            created_at=datetime.datetime.now().isoformat(),
            tree_fork_type=scenario.tree_shape.fork_type,
            tree_max_level=scenario.tree_shape.max_level,
            tree_layer_counts_json=json.dumps({str(k): v for k, v in scenario.tree_shape.layer_counts.items()}),
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
            cc_team_bonus_tier_rates_json=json.dumps({str(k): v for k, v in scenario.commission_config.team_bonus_tier_rates.items()}),
            cc_team_bonus_window_weeks=scenario.commission_config.team_bonus_window_weeks,
            cc_enable_own_basic=scenario.commission_config.enable_own_basic,
            cc_own_basic_rate=scenario.commission_config.own_basic_rate,
            cc_own_basic_line_pv_cap=scenario.commission_config.own_basic_line_pv_cap,
            cc_enable_savings=scenario.commission_config.enable_savings,
            cc_savings_usd_threshold=scenario.commission_config.savings_usd_threshold,
            cc_savings_rate=scenario.commission_config.savings_rate,
            cc_savings_cap_usd=scenario.commission_config.savings_cap_usd,
            cc_enable_pair_bonus=scenario.commission_config.enable_pair_bonus,
            cc_pair_bonus_ratios_json=json.dumps({str(k): v for k, v in scenario.commission_config.pair_bonus_ratios.items()}),
            cc_pair_bonus_4th_usd_threshold=scenario.commission_config.pair_bonus_4th_usd_threshold,
            cc_pair_bonus_5th_usd_threshold=scenario.commission_config.pair_bonus_5th_usd_threshold,
            cc_enable_leader_dividend=scenario.commission_config.enable_leader_dividend,
            cc_leader_dividend_threshold_pv=scenario.commission_config.leader_dividend_threshold_pv,
            cc_leader_dividend_share_usd=scenario.commission_config.leader_dividend_share_usd,
            cc_leader_dividend_tiers_json=json.dumps({str(k): v for k, v in scenario.commission_config.leader_dividend_tiers.items()}),
            cc_enable_horizontal_leader=scenario.commission_config.enable_horizontal_leader,
            cc_horizontal_leader_share_usd=scenario.commission_config.horizontal_leader_share_usd,
            cc_horizontal_leader_tiers_json=json.dumps({str(k): v for k, v in scenario.commission_config.horizontal_leader_tiers.items()}),
            cc_enable_opportunity_points=scenario.commission_config.enable_opportunity_points,
            total_target=scenario.total_target,
            total_weeks=scenario.total_weeks,
            total_months=scenario.total_months,
        )
        self.session.add(row)
        self.session.commit()
        return row.id

    def load(self, scenario_id: int) -> Optional[Scenario]:
        row = self.session.get(ScenarioORM, scenario_id)
        if row is None:
            return None
        return _orm_to_dataclass(row)

    def list_all(self) -> List[Scenario]:
        rows = self.session.query(ScenarioORM).all()
        return [_orm_to_dataclass(r) for r in rows]

    def delete(self, scenario_id: int) -> None:
        row = self.session.get(ScenarioORM, scenario_id)
        if row is not None:
            self.session.delete(row)
            self.session.commit()
```

- [ ] **Step 4: 跑测试, 确认 3 个全过**

Run: `pytest tests/test_scenario_repository.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scenario/repository.py tests/test_scenario_repository.py
git commit -m "feat(scenario): PR3 Task 3 — ScenarioRepository (save/load/list/delete, 拍平 40 列 ↔ dataclass)"
```

---

## Task 4: scenario_routes.py (3 个 FastAPI 路由)

**Files:**
- Create: `scenario_routes.py`
- Test: `tests/test_scenario_routes.py`

- [ ] **Step 1: 写失败测试**

写 `tests/test_scenario_routes.py`:
```python
import os
import tempfile
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import app
from database import Base
from tools.migrate_add_scenarios_table import upgrade


def _override_db():
    """override get_db dependency 用临时 SQLite"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    upgrade(engine)
    SessionLocal = sessionmaker(bind=engine)
    def _get():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
    return _get, path


def test_post_create_scenario():
    get_db, path = _override_db()
    from database import get_db
    app.dependency_overrides[get_db] = get_db
    try:
        client = TestClient(app)
        body = {
            "name": "test_route_2fork",
            "tree_shape": {"fork_type": "binary", "max_level": 3, "layer_counts": {"0": 1, "1": 4, "2": 8, "3": 1}},
            "growth": {"nodes_per_region_per_week": 9, "n_regions": 4, "join_strategy": "round_robin", "weeks_per_month": 4},
            "revenue": {"initial_pv": 1500, "monthly_renew_pv": 100, "color_rule": "4_color_cycle", "color_names": ["红", "紫", "青绿", "蓝"]},
            "commission_config": {
                "enable_retail_profit": False, "enable_team_bonus": True,
                "team_bonus_tier_rates": {"200": 0.15}, "team_bonus_window_weeks": 4,
                "enable_own_basic": True, "own_basic_rate": 0.15, "own_basic_line_pv_cap": 13334,
                "enable_savings": False, "savings_usd_threshold": 250.0, "savings_rate": 0.15, "savings_cap_usd": 500.0,
                "enable_pair_bonus": False, "pair_bonus_ratios": {}, "pair_bonus_4th_usd_threshold": 500.0, "pair_bonus_5th_usd_threshold": 1000.0,
                "enable_leader_dividend": False, "leader_dividend_threshold_pv": 13334, "leader_dividend_share_usd": 500.0, "leader_dividend_tiers": {},
                "enable_horizontal_leader": False, "horizontal_leader_share_usd": 250.0, "horizontal_leader_tiers": {},
                "enable_opportunity_points": False,
            },
        }
        resp = client.post("/api/scenarios", json=body)
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["name"] == "test_route_2fork"
    finally:
        os.unlink(path)


def test_get_state_route():
    get_db, path = _override_db()
    from database import get_db
    app.dependency_overrides[get_db] = get_db
    try:
        client = TestClient(app)
        # 先建场景
        body = {
            "name": "test_state",
            "tree_shape": {"fork_type": "binary", "max_level": 2, "layer_counts": {"0": 1, "1": 2, "2": 2}},
            "growth": {"nodes_per_region_per_week": 9, "n_regions": 4, "join_strategy": "round_robin", "weeks_per_month": 4},
            "revenue": {"initial_pv": 1500, "monthly_renew_pv": 100, "color_rule": "4_color_cycle", "color_names": ["红"]},
            "commission_config": {
                "enable_retail_profit": False, "enable_team_bonus": True,
                "team_bonus_tier_rates": {"200": 0.15}, "team_bonus_window_weeks": 4,
                "enable_own_basic": True, "own_basic_rate": 0.15, "own_basic_line_pv_cap": 13334,
                "enable_savings": False, "savings_usd_threshold": 250.0, "savings_rate": 0.15, "savings_cap_usd": 500.0,
                "enable_pair_bonus": False, "pair_bonus_ratios": {}, "pair_bonus_4th_usd_threshold": 500.0, "pair_bonus_5th_usd_threshold": 1000.0,
                "enable_leader_dividend": False, "leader_dividend_threshold_pv": 13334, "leader_dividend_share_usd": 500.0, "leader_dividend_tiers": {},
                "enable_horizontal_leader": False, "horizontal_leader_share_usd": 250.0, "horizontal_leader_tiers": {},
                "enable_opportunity_points": False,
            },
        }
        resp = client.post("/api/scenarios", json=body)
        sid = resp.json()["id"]
        # 查 state
        resp2 = client.get(f"/api/scenarios/{sid}/state?month=0&bfs_id=0")
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["bfs_id"] == 0
        assert data["month"] == 0
        assert "total_usd" in data
    finally:
        os.unlink(path)
```

- [ ] **Step 2: 跑测试, 确认失败**

Run: `pytest tests/test_scenario_routes.py -v`
Expected: 404 Not Found (路由不存在)

- [ ] **Step 3: 写 scenario_routes.py**

```python
"""Scenario HTTP 路由 (PR3) — 3 个路由, 接入 FastAPI app"""
from __future__ import annotations
from decimal import Decimal
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from scenario.builder import build_scenario
from scenario.repository import ScenarioRepository
from scenario.breakdown import compute_commission_breakdown
from scenario.overview import compute_month_overview
from scenario.model import (
    TreeShape, Growth, Revenue, CommissionConfig,
)


router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


# --- Pydantic models (request body) ---

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
    color_names: list


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


# --- Routes ---

@router.post("", status_code=201)
def create_scenario(body: ScenarioIn, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """建场景: 4 组参数 → DB 存 1 行, 返 {id}"""
    ts = TreeShape(
        fork_type=body.tree_shape.fork_type,
        max_level=body.tree_shape.max_level,
        layer_counts={int(k): v for k, v in body.tree_shape.layer_counts.items()},
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
    cc_data = body.commission_config.dict()
    cc = CommissionConfig(
        **{k: v for k, v in cc_data.items()
           if k not in ("team_bonus_tier_rates", "pair_bonus_ratios", "leader_dividend_tiers", "horizontal_leader_tiers")},
        team_bonus_tier_rates={int(k): v for k, v in cc_data["team_bonus_tier_rates"].items()},
        pair_bonus_ratios={int(k): v for k, v in cc_data["pair_bonus_ratios"].items()},
        leader_dividend_tiers={int(k): v for k, v in cc_data["leader_dividend_tiers"].items()},
        horizontal_leader_tiers={int(k): v for k, v in cc_data["horizontal_leader_tiers"].items()},
    )
    s = build_scenario(ts, g, r, cc, name=body.name)
    repo = ScenarioRepository(db)
    scenario_id = repo.save(s)
    return {"id": scenario_id, "name": body.name}


@router.get("/{scenario_id}/state")
def get_state(scenario_id: int,
                month: int = Query(..., ge=0),
                bfs_id: int = Query(..., ge=0),
                db: Session = Depends(get_db)) -> Dict[str, Any]:
    """取节点状态: scenario_id + month + bfs_id → CommissionBreakdown JSON"""
    repo = ScenarioRepository(db)
    s = repo.load(scenario_id)
    if s is None:
        raise HTTPException(status_code=404, detail="scenario not found")
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
        "total_usd": str(cb.total_usd),
        "ip_chain_status": cb.ip_chain_status,
        "is_optimized_region": cb.is_optimized_region,
        "cumulative_to_date_usd": str(cb.cumulative_to_date_usd),
    }


@router.get("/{scenario_id}/overview")
def get_overview(scenario_id: int,
                  month: int = Query(..., ge=0),
                  db: Session = Depends(get_db)) -> Dict[str, Any]:
    """取当月全网总览"""
    repo = ScenarioRepository(db)
    s = repo.load(scenario_id)
    if s is None:
        raise HTTPException(status_code=404, detail="scenario not found")
    overview = compute_month_overview(s, month=month)
    return {k: str(v) for k, v in overview.items()}
```

- [ ] **Step 4: 在 main.py 末尾追加 `app.include_router(scenario_routes.router)`**

```python
# main.py 末尾
import scenario_routes
app.include_router(scenario_routes.router)
```

- [ ] **Step 5: 跑测试, 确认 2 个全过**

Run: `pytest tests/test_scenario_routes.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add scenario_routes.py main.py tests/test_scenario_routes.py
git commit -m "feat(scenario): PR3 Task 4 — scenario_routes 3 个 HTTP 路由 (POST/GET state/GET overview) + main.py include"
```

---

## Task 5: 跑 live server 验证 3 个路由

**Files:**
- (none, manual)

- [ ] **Step 1: 启动 uvicorn**

Run: `python -m uvicorn main:app --port 38089 &`
Expected: 启动成功

- [ ] **Step 2: curl POST /api/scenarios 创建一个场景**

Run: `curl -X POST http://127.0.0.1:38089/api/scenarios -H "Content-Type: application/json" -d @tools/_sample_scenario.json`
Expected: `{"id": 1, "name": "..."}`

- [ ] **Step 3: curl GET /api/scenarios/1/state?month=14&bfs_id=0**

Run: `curl http://127.0.0.1:38089/api/scenarios/1/state?month=14\&bfs_id=0`
Expected: JSON 返 8 种报酬 + total

- [ ] **Step 4: 关闭 uvicorn**

Run: `kill <pid>`

- [ ] **Step 5: 跑全部测试, 确认无破坏**

Run: `pytest tests/ -v`
Expected: 35+ 个旧测试 + 7+ 个新测试全过

---

## Task 6: AGENTS.md §6.3 P1 PR3 状态记录

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: 加 §6.3**

```markdown
### 6.3 P1 PR3 — scenarios 表 + 3 个 HTTP 路由

**业务**: 把 scenario 引擎接入 FastAPI, 客户通过 HTTP 调 4 组参数
**完成日**: 2026-08-07 (估)
**Commit**: 见 git log (Task 1-6 各 1 commit)
**关键文件**:
- `models.py` — Scenario ORM (40 列)
- `tools/migrate_add_scenarios_table.py` — idempotent 创表
- `scenario/repository.py` — ScenarioRepository (save/load/list/delete)
- `scenario_routes.py` — 3 个 HTTP 路由 (POST/GET state/GET overview)
**验收**:
- ✅ scenarios 表创建 (live DB + 测试 temp DB)
- ✅ POST /api/scenarios 建场景 201, 返 {id}
- ✅ GET /api/scenarios/{id}/state 返 CommissionBreakdown JSON
- ✅ GET /api/scenarios/{id}/overview 返当月全网合计
- ✅ 旧 main.py 业务路由 0 行为变化 (旧 + 新测试都过)
```

- [ ] **Step 2: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): §6.3 P1 PR3 状态记录 (scenarios 表 + 3 路由)"
```

---

## 验证清单 (PR3 全部完成后)

- [ ] pytest tests/test_scenario_*.py + tests/test_scenario_routes.py 全过 (15+ 个)
- [ ] pytest tests/ 旧测试全过 (35+ 个)
- [ ] live server 3 个路由可 curl 调用
- [ ] git log 看到 Task 1-6 各 1 commit (6 commits)
- [ ] AGENTS.md §6.3 写完

PR3 完成 = 准备进 PR4 (迁移 + 数字一致性验证 + 删除旧脚本)

---

## Self-Review Checklist

完成本 plan 后自检:
1. **Spec coverage**: spec §3.2 (40 列 scenarios 表) → Task 1-2, spec §4.3 (3 个 HTTP 路由) → Task 4
2. **Placeholder scan**: 没有 TBD/TODO
3. **Type consistency**: ORM 40 列 ↔ dataclass 字段 1:1, JSON 序列化 / 反序列化对得上
