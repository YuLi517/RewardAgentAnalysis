"""PR3 Task 6: 加 AGENTS.md §6.3 状态记录"""
from pathlib import Path

addition = """


### 6.3 P1 PR3 — scenarios 表 + 3 个 HTTP 路由

**业务**: 把 scenario 引擎接入 FastAPI, 客户通过 HTTP 调 4 组参数 (招商/路演实时计算器)
**完成日**: 2026-08-07 (本轮)
**Commit**: `035fd8c` Task 1 + `7c16939` Task 2 + `a878bd3` Task 3 + `6dd15b0` Task 4
**关键文件**:
- `models.py` — Scenario ORM (40 列, 3 标量 + 4 growth + 4 revenue + 21 cc + 3 派生 + 5 misc)
  - 6 JSON 字段: tree_layer_counts_json / revenue_color_names_json / cc_team_bonus_tier_rates_json /
    cc_pair_bonus_ratios_json / cc_leader_dividend_tiers_json / cc_horizontal_leader_tiers_json
  - Boolean 字段 (21 cc): cc_enable_team_bonus / cc_enable_own_basic / 等
  - 派生字段 (3): total_target / total_weeks / total_months 也存表
  - to_dict() 反序列化时把 Dict[str, int] 转 Dict[int, int] (业务要求)
- `tools/migrate_add_scenarios_table.py` — idempotent 创表 (用 SQLAlchemy 2.x ORM, inspect 检测跳过)
- `scenario/repository.py` — ScenarioRepository (save/load/list/delete)
  - save: 4 组参数 + 派生拍平 40 列, JSON 字段 int key + Decimal→float
  - load: row → dataclass, Decimal 字段显式包 Decimal
  - list_all: SQLAlchemy 2.x select 风格, 按 id 升序
  - delete: 删 row, 不报错 if 不存在
- `scenario_routes.py` — 3 个 FastAPI 路由 (新文件, 不改 main.py 业务代码)
  - POST /api/scenarios — 4 组参数 → DB row, 返 {id, name}
  - GET /api/scenarios/{id}/state?month=&bfs_id= — 节点当月 8 种报酬 + total
  - GET /api/scenarios/{id}/overview?month= — 当月全网 8 种合计
- `main.py` — 末尾追加 5 行 `import scenario_routes + app.include_router(scenario_routes.router)`
- `tests/test_scenario_orm.py` — 3 个测试 (40 列验证 + 创表不破坏 + to_dict roundtrip)
- `tests/test_migrate_scenarios.py` — 2 个测试 (idempotent + 不误删)
- `tests/test_scenario_repository.py` — 4 个测试 (save/load roundtrip + list + delete + 同 name 多次 save)
- `tests/test_scenario_routes.py` — 4 个测试 (POST 201 + GET state 200 + GET overview 200 + 404)

**验收 (67 测试全过)**:
- test_scenario_orm: 3 (40 列验证 + 创表不破坏 + to_dict)
- test_migrate_scenarios: 2 (idempotent + 不误删)
- test_scenario_repository: 4 (save/load roundtrip + list + delete + 同 name 多次)
- test_scenario_routes: 4 (POST 201 + GET state 200 + GET overview 200 + 404)
- test_scenario_builder + test_scenario_pv + test_scenario_cache + test_scenario_consistency + test_scenario_model: 22 (PR1)
- test_commission_own_basic + test_pr2_root_consistency + test_db_admin: 32 (PR2 + admin)
- 合计 67 测试全过 (PR1+PR2+PR3 Task 1-4, 单独跑稳定)
- live server 验证 3 路由 (port 38089, post → id 1, state 14 字段, overview 8 字段)

**业务价值 (路演场景)**:
- 客户路演: 调 4 组参数 → POST /api/scenarios → DB 存 1 行 → GET state/overview 实时算 8 种报酬
- 旧 builder 兼容: PR3 跟 PR2 解耦, 旧 builder 走 main.py 不变, 新 scenario 走 routes
- 大重构 6 子项目 P1 阶段 3/3 完成 (Scenario 库 + 业务算法 + 持久化 + 路由)

**PR3 + PR2 组合场景**:
- POST /api/scenarios 建场景 → DB row id
- GET /api/scenarios/{id}/state?month=14&bfs_id=0 返 8 种报酬 + total
- 跟 PR2 round 3 数字一致 (4 函数对齐 own_basic/savings/horizontal/pair_bonus, 2 函数 BFS 偏差)
- 客户能调参, 实时看 8 种报酬在 15 月累计 (路演场景 1 套)

**PR4 待办 (后续)**:
- Task 1-5: skills/pair_commission.py 旧函数 → scenario wrapper
- Task 6: main.py 0 改动, 旧运营 UI 跟新 scenario_routes 共存
- Task 7-8: 跟 main.py 集成测试 + UAT zip 打包
"""

with open('AGENTS.md', 'ab') as f:
    f.write(addition.encode('utf-8'))

print(f"Appended {len(addition)} chars to AGENTS.md")
print(f"Total size: {Path('AGENTS.md').stat().st_size} bytes")
