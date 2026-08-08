"""v1.0.18 (2026-08-08): bfs_id 偏移迁移工具

业务背景 (v1.0.18, 用户 2026-08-08):
  - v1.0.9 引入 JSON 模板 (binarytree_4093.json / quaternarytree_87381.json) 时
    模板 id 1 = root → bfs_id 1 (跟原 builder.py root=0 不一致)
  - 业务影响: state 端点 bfs_id=0 拿空, PDF TOP5_BFS_IDS=[0,1,2,3,4] 第 1 个不是 root,
             前端默认 bfs_id=0 = root 跟 binary/quaternary 实际不一致
  - v1.0.18 修复: json_tree_loader.py 改 bfs_id = template_id - 1
    业务上 ternary / binary / quaternary 三种 fork_type 全部统一:
    root = bfs_id 0, L1 父 = bfs_id 1, 2, 3, 4
  - 旧 binary/quaternary scenario (id 1, 123, 124, 131, 134, 135, 137, 138, 139)
    都有 scenario_nodes 行 + one_gen_four_locks_json 字段, 业务上是"旧 bfs_id 体系"
    需要重新算 + 写新 bfs_id 体系

业务方案 (简化):
  1. 删所有 binary/quaternary scenario 的 scenario_nodes 行 (FK 引用, 必须先清)
  2. 设 one_gen_four_locks_json = NULL (让 lazy backfill 重新算)
  3. 清 ScenarioRepository._process_cache (id(scenario_instance) cache)
  4. 下次访问 scenario 自动触发 lazy backfill (用新 bfs_id 体系重新算 + 写 DB)

业务影响:
  - 8 个旧 binary/quaternary scenario 首次访问会触发 lazy backfill
  - lazy backfill 一次性 ~700ms per scenario, 总 ~6 秒
  - 后续访问 0 延迟 (LRU cache)

用法:
  python tools/migrate_bfs_offset.py             # 一键迁移
  python tools/migrate_bfs_offset.py --dry-run  # 仅列出待清
"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def main():
    dry_run = "--dry-run" in sys.argv

    print("=" * 80)
    print("v1.0.18 bfs_id 偏移迁移 (json_tree_loader.py 改 bfs_id = template_id - 1)")
    print("=" * 80)

    import sqlite3
    db_path = project_root / "data" / "rewarddb.db"
    db = sqlite3.connect(str(db_path))
    c = db.cursor()

    # 1. 列出所有 binary/quaternary scenario
    c.execute("""
        SELECT id, name, tree_fork_type
        FROM scenarios
        WHERE tree_fork_type IN ('binary', 'quaternary')
        ORDER BY id
    """)
    scenarios = c.fetchall()
    print(f"\n需要迁移的 scenario ({len(scenarios)} 个):")
    for s in scenarios:
        print(f"  + id={s[0]:>3} name={s[1][:35]:<35} fork={s[2]}")
    print()

    if dry_run:
        print("[DRY-RUN] 不真删, 退出")
        return 0

    if not scenarios:
        print("没有需要迁移的 scenario")
        return 0

    # 2. 删 scenario_nodes (FK 引用, 必须先清)
    ids = [s[0] for s in scenarios]
    placeholders = ",".join("?" * len(ids))
    c.execute(f"DELETE FROM scenario_nodes WHERE scenario_id IN ({placeholders})", ids)
    n_nodes_deleted = c.rowcount
    print(f"已删 {n_nodes_deleted:,} 个 scenario_nodes 行")

    # 3. 设 one_gen_four_locks_json = NULL (让 lazy backfill 重新算)
    c.execute(f"UPDATE scenarios SET one_gen_four_locks_json = NULL WHERE id IN ({placeholders})", ids)
    n_locks_cleared = c.rowcount
    print(f"已清 {n_locks_cleared} 个 one_gen_four_locks_json 字段 (lazy backfill 触发)")

    db.commit()
    db.close()

    # 4. 清 ScenarioRepository._process_cache
    from scenario.repository import ScenarioRepository
    ScenarioRepository.clear_cache()
    print("已清 ScenarioRepository._process_cache")

    # 5. VACUUM 回收 free pages (可选, 跟 v1.0.17 一样)
    print()
    print("VACUUM INTO 回收 free pages...")
    import shutil
    db_path_vacuum = project_root / "data" / "rewarddb_vacuum.db"
    db = sqlite3.connect(str(db_path))
    c = db.cursor()
    c.execute(f"VACUUM INTO '{db_path_vacuum}'")
    db.close()
    shutil.move(str(db_path_vacuum), str(db_path))
    import os
    size_after = os.path.getsize(str(db_path))
    print(f"VACUUM done, DB size: {size_after:,} bytes ({size_after/1024:.1f} KB)")

    print()
    print("=" * 80)
    print("迁移完成!")
    print("=" * 80)
    print(f"  清理: {n_nodes_deleted:,} scenario_nodes 行 + {n_locks_cleared} locks 字段")
    print(f"  影响: {len(scenarios)} 个 binary/quaternary scenario 首次访问会 lazy backfill")
    print(f"  lazy backfill 自动用新 bfs_id 体系 (root=0, L1 父=1,2,3,4)")
    print(f"  业务: ternary / binary / quaternary 三种 fork_type 全部统一 bfs_id 体系")

    return 0


if __name__ == "__main__":
    sys.exit(main())
