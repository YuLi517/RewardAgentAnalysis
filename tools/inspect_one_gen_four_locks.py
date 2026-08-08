"""v1.0.14 (2026-08-08): 1代4 4 子锁定 业务可视化工具

业务:
  - 列出某 scenario 所有父节点 (非叶 + 凑齐 4 子) 的 4 子 bfs_id + 凑齐月份 M_first
  - 用户可以 grep 某个 bfs_id 看 4 子是谁 (业务可视化, 不再 "动态 BFS 黑盒")
  - 用法: python tools/inspect_one_gen_four_locks.py [scenario_id] [bfs_id_filter]

示例:
  python tools/inspect_one_gen_four_locks.py 134
  python tools/inspect_one_gen_four_locks.py 134 1
  python tools/inspect_one_gen_four_locks.py 134 6
"""
import json
import sys
from pathlib import Path

# 加项目根到 sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from database import SessionLocal
from scenario.repository import ScenarioRepository
from scenario.locks import deserialize_locks


def main():
    if len(sys.argv) < 2:
        print("用法: python tools/inspect_one_gen_four_locks.py [scenario_id] [bfs_id_filter]")
        print("示例: python tools/inspect_one_gen_four_locks.py 134")
        print("      python tools/inspect_one_gen_four_locks.py 134 1")
        sys.exit(1)
    scenario_id = int(sys.argv[1])
    bfs_filter = int(sys.argv[2]) if len(sys.argv) > 2 else None

    db = SessionLocal()
    try:
        repo = ScenarioRepository(db)
        # 触发 lazy backfill (如果需要)
        scenario = repo.load(scenario_id)
        if scenario is None:
            print(f"scenario {scenario_id} 不存在")
            sys.exit(1)
        print(f"Scenario {scenario_id}: {scenario.name}")
        print(f"  total_target={scenario.total_target}  total_weeks={scenario.total_weeks}  total_months={scenario.total_months}")
        print()

        # 读 locks JSON 字段
        from models import Scenario as ScenarioORM
        row = db.get(ScenarioORM, scenario_id)
        locks = deserialize_locks(row.one_gen_four_locks_json)
        if locks is None:
            print("locks_json 是空 (应该是 lazy backfill 刚填充的, 重新跑一遍)")
            sys.exit(1)

        # 过滤 + 排序
        if bfs_filter is not None:
            lock = locks.get(bfs_filter)
            if lock is None:
                print(f"bfs_id={bfs_filter} 没在 locks 里 (可能是叶子 / 凑不齐 4 子)")
                print(f"已 lock 的父节点 bfs_id 范围: {min(locks.keys())} - {max(locks.keys())}, 共 {len(locks)} 个")
                sys.exit(0)
            print(f"bfs_id={bfs_filter} 4 子锁定:")
            print(f"  subs:     {lock['subs']}")
            print(f"  m_first:  {lock['m_first']}  (凑齐 4 子月份, 触发 = month >= m_first + 1)")
            print(f"  触发月份范围: {lock['m_first'] + 1} - {scenario.total_months}")
            return

        # 全网表
        print(f"全网 1代4 locks (共 {len(locks)} 个父节点凑齐 4 子):")
        print()
        print(f"  {'bfs_id':>6}  {'subs (4 个子节点)':40s}  m_first")
        print(f"  {'-'*6}  {'-'*40}  {'-'*7}")
        # 按 bfs_id 排序
        for bfs_id in sorted(locks.keys()):
            lock = locks[bfs_id]
            subs_str = ", ".join(str(s) for s in lock["subs"])
            print(f"  {bfs_id:>6}  {subs_str:40s}  {lock['m_first']}")
        print()
        print(f"统计: 凑齐 4 子的父节点 = {len(locks)}")
        if locks:
            m_first_set = set(lock["m_first"] for lock in locks.values())
            print(f"      m_first 范围: {min(m_first_set)} - {max(m_first_set)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
