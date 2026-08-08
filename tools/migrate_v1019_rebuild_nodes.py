"""v1.0.19 迁移: 重建 binary/quaternary scenario 的 scenario_nodes (修 join_month 全 0 bug)

业务: S140 等 binary scenario 的 nodes 表是 v1.0.19 修复前的快照, join_month 全 0
      重建: 走 _build_bfs_tree 重新算 (会按 growth 正确排 join_month) → bulk INSERT

跑法: 停 server → 跑这个脚本 → 重启 server
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models import Scenario as ScenarioORM, ScenarioNode as ScenarioNodeORM
from scenario.nodes import compute_scenario_nodes, bulk_insert_scenario_nodes
from scenario.repository import ScenarioRepository
from scenario.repository import ScenarioRepository
from scenario.commission._helpers import clear_all_caches
from sqlalchemy import select

db = SessionLocal()
repo = ScenarioRepository(db)
# 清类级别 cache, 防 stale instance
ScenarioRepository.clear_cache()

try:
    # 查所有 binary/quaternary scenario (ternary 不受影响, 一直用 _build_bfs_tree 排)
    stmt = select(ScenarioORM).where(ScenarioORM.tree_fork_type.in_(["binary", "quaternary"]))
    scenarios = db.execute(stmt).scalars().all()
    print(f"Found {len(scenarios)} binary/quaternary scenarios to rebuild")

    for s_orm in scenarios:
        # 用 repo.load 拿完整 dataclass (内部会触发 lazy backfill, 但 nodes 已存在所以跳过)
        s = repo.load(s_orm.id)
        if s is None:
            print(f"  S{s_orm.id}: load failed, skip")
            continue
        # 清 helper cache
        clear_all_caches()
        # 重新算 nodes (走 _build_bfs_tree → JSON 模板 → v1.0.19 修复版)
        nodes = compute_scenario_nodes(s)
        # bulk INSERT (会先删旧的)
        count = bulk_insert_scenario_nodes(db, s_orm.id, nodes)
        # 验证 join_month 分布
        new_stmt = select(ScenarioNodeORM).where(ScenarioNodeORM.scenario_id == s_orm.id)
        rows = db.execute(new_stmt).scalars().all()
        jm_dist = {}
        for r in rows:
            jm_dist[r.join_month] = jm_dist.get(r.join_month, 0) + 1
        jm_summary = dict(sorted(jm_dist.items()))
        # 简化输出 (避免 GBK encoding 错)
        print(f"  S{s_orm.id} ({s_orm.name}): rebuilt {count} nodes, join_month dist: {jm_summary}")

    # 清类级别 cache, 让 server 重启后重新加载
    ScenarioRepository.clear_cache()
    db.commit()
    print("\nAll binary/quaternary scenarios rebuilt successfully")
except Exception as e:
    db.rollback()
    print(f"Failed: {e}")
    raise
finally:
    db.close()
