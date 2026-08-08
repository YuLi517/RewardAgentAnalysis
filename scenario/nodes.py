"""v1.0.16 (2026-08-08): 场景节点表 (scenario_nodes) 操作封装

业务动机 (用户 2026-08-08, 第 7 轮澄清):
  - 之前 2144 节点由 _build_bfs_tree 动态生成, 业务不稳定 (模板升级影响旧 scenario)
  - 用户诉求: 随时查每个点位 (level/parent/region), 验证 commission 计算正确性
  - 拍板: 节点表存, POST scenario 时 1 次算全树 + bulk INSERT 2144 行

设计:
  - scenario_nodes 表 (scenario_id, bfs_id, level, parent_bfs, slot_line_id, region_id, join_week, join_month, color_index)
  - 联合主键 (scenario_id, bfs_id) UNIQUE
  - 4 INDEX (level, parent_bfs, region_id, 联合唯一)
  - FK ON DELETE CASCADE (scenario 删, 节点自动删)

业务定位:
  - "稳定" - 模板升级不影响旧 scenario (节点关系已快照)
  - "可查" - 任意 bfs_id 都能 SELECT 出 level/parent/slot/region
  - "可验证" - 任何 1 节点 4 子 + commission 计算依据都能查

性能:
  - POST scenario: 1 次 bulk INSERT 2144 行 ~50ms
  - 查任意 bfs_id: SELECT WHERE scenario_id=? AND bfs_id=? ~1ms
  - DB 体积: 137 scenario × 2144 节点 × ~30 bytes = 8.8MB
"""
from __future__ import annotations
import json
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from scenario.model import Scenario
from scenario.builder import _build_bfs_tree
from models import Scenario as ScenarioORM, ScenarioNode as ScenarioNodeORM


def compute_scenario_nodes(scenario: Scenario) -> Dict[int, dict]:
    """算全网 2144 节点 (跟 _build_bfs_tree 输出 dict 一致)

    业务: POST scenario 时调, 然后 bulk INSERT 到 scenario_nodes 表
    跟 _build_bfs_tree 区别: 这个是 wrapper, 业务上调用入口更清晰
    """
    return _build_bfs_tree(scenario.tree_shape, scenario.growth)


def bulk_insert_scenario_nodes(db: Session, scenario_id: int,
                                nodes: Dict[int, dict]) -> int:
    """bulk INSERT 节点到 scenario_nodes 表

    业务: POST scenario 流程:
      1. compute_scenario_nodes(scenario) 算全树
      2. bulk_insert_scenario_nodes(db, scenario_id, nodes) 写 DB
      3. ~50ms (2144 行 1 次 bulk INSERT)

    Returns: 写入行数
    """
    # 删旧 nodes (idempotent, 重新写)
    db.execute(
        delete(ScenarioNodeORM).where(ScenarioNodeORM.scenario_id == scenario_id)
    )
    # bulk INSERT
    rows = [{
        "scenario_id": scenario_id,
        "bfs_id": n["bfs_id"],
        "level": n["level"],
        "parent_bfs": n["parent_bfs"] if n["parent_bfs"] != -1 else None,
        "slot_line_id": n["slot_line_id"],
        "region_id": n["region_id"],
        "join_week": n.get("join_week", 0),
        "join_month": n.get("join_month", 0),
        "color_index": n.get("color_index", 0),
    } for n in nodes.values()]
    db.bulk_insert_mappings(ScenarioNodeORM, rows)
    db.commit()
    return len(rows)


def load_scenario_nodes(db: Session, scenario_id: int) -> Optional[Dict[int, dict]]:
    """从 scenario_nodes 表 1 次 SELECT 全树, 转 dict 跟 _build_bfs_tree 一致

    Returns:
        Dict[bfs_id, node_dict] (level/parent_bfs/slot_line_id/region_id/join_week/join_month/color_index)
        None if scenario 没 nodes (lazy backfill 触发)
    """
    stmt = select(ScenarioNodeORM).where(ScenarioNodeORM.scenario_id == scenario_id)
    rows = db.execute(stmt).scalars().all()
    if not rows:
        return None
    return {row.bfs_id: row.to_dict() for row in rows}


def load_single_node(db: Session, scenario_id: int, bfs_id: int) -> Optional[dict]:
    """查单个节点 (业务可视化用, 任意 bfs_id 可查)
    Returns: 节点 dict (level/parent_bfs/...) 或 None
    """
    stmt = select(ScenarioNodeORM).where(
        ScenarioNodeORM.scenario_id == scenario_id,
        ScenarioNodeORM.bfs_id == bfs_id,
    )
    row = db.execute(stmt).scalar_one_or_none()
    return row.to_dict() if row else None


def load_children_of(db: Session, scenario_id: int, parent_bfs: int) -> List[dict]:
    """查某父节点的所有子节点 (业务可视化用, JOIN parent_bfs INDEX)
    Returns: [node_dict1, node_dict2, ...] 按 bfs_id 升序
    """
    stmt = select(ScenarioNodeORM).where(
        ScenarioNodeORM.scenario_id == scenario_id,
        ScenarioNodeORM.parent_bfs == parent_bfs,
    ).order_by(ScenarioNodeORM.bfs_id)
    rows = db.execute(stmt).scalars().all()
    return [row.to_dict() for row in rows]


def load_nodes_by_level(db: Session, scenario_id: int, level: int) -> List[dict]:
    """查某层所有节点 (业务可视化用, JOIN level INDEX)
    Returns: [node_dict1, ...] 按 bfs_id 升序
    """
    stmt = select(ScenarioNodeORM).where(
        ScenarioNodeORM.scenario_id == scenario_id,
        ScenarioNodeORM.level == level,
    ).order_by(ScenarioNodeORM.bfs_id)
    rows = db.execute(stmt).scalars().all()
    return [row.to_dict() for row in rows]


def load_nodes_by_region(db: Session, scenario_id: int, region_id: int) -> List[dict]:
    """查某大区所有节点 (业务可视化用, JOIN region INDEX)
    Returns: [node_dict1, ...] 按 bfs_id 升序
    """
    stmt = select(ScenarioNodeORM).where(
        ScenarioNodeORM.scenario_id == scenario_id,
        ScenarioNodeORM.region_id == region_id,
    ).order_by(ScenarioNodeORM.bfs_id)
    rows = db.execute(stmt).scalars().all()
    return [row.to_dict() for row in rows]


def count_nodes(db: Session, scenario_id: int) -> int:
    """查 scenario 节点总数 (业务验证用)
    Returns: 节点行数
    """
    stmt = select(ScenarioNodeORM).where(ScenarioNodeORM.scenario_id == scenario_id)
    return len(db.execute(stmt).scalars().all())


def has_nodes(db: Session, scenario_id: int) -> bool:
    """业务上: scenario 有 nodes 表数据?
    Returns: True if has at least 1 node
    """
    return count_nodes(db, scenario_id) > 0
