"""v1.0.16 (2026-08-08): 节点表业务可视化工具

业务 (用户 2026-08-08, 第 7 轮澄清):
  - 任意 bfs_id 都能查 level/parent_bfs/slot_line_id/region_id
  - 验证 commission 计算正确性
  - 业务可视化: 查某层 / 某大区 / 某父的所有节点

用法:
  python tools/inspect_scenario_nodes.py [scenario_id]
    → 列 scenario 总览 (节点数, 按 level 分布, 4 大区节点数)
  python tools/inspect_scenario_nodes.py [scenario_id] [bfs_id]
    → 查某 bfs_id 节点详情 + 父 + 子
  python tools/inspect_scenario_nodes.py [scenario_id] level=5
    → 列 L5 所有节点
  python tools/inspect_scenario_nodes.py [scenario_id] parent=10
    → 列 parent=10 的所有子
  python tools/inspect_scenario_nodes.py [scenario_id] region=2
    → 列 region=2 (大区 2) 的所有节点
"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from database import SessionLocal
from scenario.repository import ScenarioRepository
from scenario.nodes import (
    load_single_node, load_children_of,
    load_nodes_by_level, load_nodes_by_region,
    count_nodes, has_nodes,
)


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python tools/inspect_scenario_nodes.py [scenario_id]")
        print("    列 scenario 总览 (节点数, 按 level 分布, 4 大区节点数)")
        print("  python tools/inspect_scenario_nodes.py [scenario_id] [bfs_id]")
        print("    查某 bfs_id 节点详情 + 父 + 子")
        print("  python tools/inspect_scenario_nodes.py [scenario_id] level=5")
        print("    列 L5 所有节点")
        print("  python tools/inspect_scenario_nodes.py [scenario_id] parent=10")
        print("    列 parent=10 的所有子")
        print("  python tools/inspect_scenario_nodes.py [scenario_id] region=2")
        print("    列 region=2 (大区 2) 的所有节点")
        sys.exit(1)
    scenario_id = int(sys.argv[1])
    arg2 = sys.argv[2] if len(sys.argv) > 2 else None

    db = SessionLocal()
    try:
        # 触发 lazy backfill (如果需要)
        repo = ScenarioRepository(db)
        scenario = repo.load(scenario_id)
        if scenario is None:
            print(f"scenario {scenario_id} 不存在")
            sys.exit(1)
        print(f"Scenario {scenario_id}: {scenario.name}")
        print(f"  total_target={scenario.total_target}  total_weeks={scenario.total_weeks}  total_months={scenario.total_months}")
        print()

        # 验 nodes 表有数据
        if not has_nodes(db, scenario_id):
            print("scenario_nodes 表空, 应该是 lazy backfill 刚填充的, 重跑")
            sys.exit(1)

        if arg2 is None:
            # 总览
            n_total = count_nodes(db, scenario_id)
            print(f"scenario_nodes 行数: {n_total} (期望 {scenario.total_target})")
            print()
            print("按 level 分布:")
            for lv in range(0, scenario.tree_shape.max_level + 1):
                nodes = load_nodes_by_level(db, scenario_id, lv)
                if nodes:
                    sample = nodes[:3]
                    sample_str = ", ".join(f"bfs_id={n['bfs_id']} slot={n['slot_line_id']} reg={n['region_id']}"
                                            for n in sample)
                    more = f" ... (+{len(nodes) - 3} more)" if len(nodes) > 3 else ""
                    print(f"  L{lv}: {len(nodes):>4} 节点   例: [{sample_str}]{more}")
            print()
            print("按 region 分布:")
            for r in range(0, 5):
                nodes = load_nodes_by_region(db, scenario_id, r)
                if nodes:
                    print(f"  region {r}: {len(nodes):>4} 节点")
            return

        if "=" in arg2:
            # 过滤: level=N / parent=N / region=N
            key, val = arg2.split("=", 1)
            val = int(val)
            if key == "level":
                nodes = load_nodes_by_level(db, scenario_id, val)
                print(f"L{val} 所有节点 (共 {len(nodes)}):")
                for n in nodes:
                    print(f"  bfs_id={n['bfs_id']:>5}  parent_bfs={n['parent_bfs']:>5}  slot={n['slot_line_id']}  region={n['region_id']}")
            elif key == "parent":
                nodes = load_children_of(db, scenario_id, val)
                print(f"parent_bfs={val} 的所有子 (共 {len(nodes)}):")
                for n in nodes:
                    print(f"  bfs_id={n['bfs_id']:>5}  level={n['level']}  slot={n['slot_line_id']}  region={n['region_id']}")
            elif key == "region":
                nodes = load_nodes_by_region(db, scenario_id, val)
                print(f"region={val} 的所有节点 (共 {len(nodes)}):")
                for n in nodes[:20]:
                    print(f"  bfs_id={n['bfs_id']:>5}  level={n['level']}  parent_bfs={n['parent_bfs']:>5}  slot={n['slot_line_id']}")
                if len(nodes) > 20:
                    print(f"  ... (+{len(nodes) - 20} more)")
            return

        # arg2 = bfs_id
        bfs_id = int(arg2)
        node = load_single_node(db, scenario_id, bfs_id)
        if node is None:
            print(f"bfs_id={bfs_id} 不在 scenario {scenario_id} 节点表里")
            print(f"  (bfs_id 范围: 1 - {scenario.total_target})")
            sys.exit(1)
        print(f"bfs_id={bfs_id} 节点详情:")
        print(f"  level:        {node['level']}")
        print(f"  parent_bfs:   {node['parent_bfs']}  (-1 = root)")
        print(f"  slot_line_id: {node['slot_line_id']}  (1-5 子区编号)")
        print(f"  region_id:    {node['region_id']}  (1-4 大区)")
        print(f"  join_week:    {node['join_week']}")
        print(f"  join_month:    {node['join_month']}")
        print(f"  color_index:  {node['color_index']}")
        print()
        # 父节点
        if node['parent_bfs'] >= 0:
            parent = load_single_node(db, scenario_id, node['parent_bfs'])
            print(f"父节点 (parent_bfs={node['parent_bfs']}):")
            print(f"  level={parent['level']} slot={parent['slot_line_id']} region={parent['region_id']}")
            print()
        # 子节点
        children = load_children_of(db, scenario_id, bfs_id)
        if children:
            print(f"子节点 (parent_bfs={bfs_id}, 共 {len(children)}):")
            for c in children:
                print(f"  bfs_id={c['bfs_id']:>5}  level={c['level']}  slot={c['slot_line_id']}  region={c['region_id']}")
        else:
            print(f"bfs_id={bfs_id} 是叶子节点, 无子")
    finally:
        db.close()


if __name__ == "__main__":
    main()
