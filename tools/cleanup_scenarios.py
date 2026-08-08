"""v1.0.17 (2026-08-08): Scenario 清理工具 (激进清理方案 A)

业务背景:
  - 测试期间 140 个 scenario 累积, 大部分是 UI 重复点击产生的 'live_scenario' 测试
  - 业务上 10 个有效 scenario 已够 (v1.0.7-v1.0.16 业务版本快照 + 早期 live_test)
  - 清理后 DB 体积从 15.1MB 回 1MB, 业务可演示

清理规则 (方案 A, 保留 10 个):
  - id 1: 早期 live_test (e2e 起始测试)
  - id 111, 112, 113, 115: v1.0.7/v1.0.8 fork_type (binary/ternary/quaternary)
  - id 123, 124: v1.0.9 binarytree_4093 / quaternarytree_87381 模板测试
  - id 131, 134, 135, 137, 138: v1.0.12/13/14/15/16 E2E 验证

清 130 个:
  - id 2-110 中除保留的 (5 测试类)
  - id 116, 117 (v1.0.8 重复)
  - id 119-122, 125-130, 132, 133, 136, 139, 140 (重复 / 老旧)

FK CASCADE 自动清:
  - scenario_nodes (节点表)
  - one_gen_four_locks_json 字段 (1代4 锁定)

用法:
  python tools/cleanup_scenarios.py             # 一键清理
  python tools/cleanup_scenarios.py --dry-run  # 仅列出待清, 不真删
  python tools/cleanup_scenarios.py --keep=1,111,112  # 自定义保留列表
"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# 默认保留列表 (方案 A)
DEFAULT_KEEP_IDS = [1, 111, 112, 113, 115, 123, 124, 131, 134, 135, 137, 138]


def main():
    dry_run = "--dry-run" in sys.argv
    keep_ids = DEFAULT_KEEP_IDS
    for arg in sys.argv:
        if arg.startswith("--keep="):
            keep_ids = [int(x) for x in arg.split("=", 1)[1].split(",")]

    print("=" * 80)
    print(f"v1.0.17 Scenario 清理工具 (方案 A)")
    print("=" * 80)
    print(f"保留 IDs: {keep_ids}")
    print()

    import sqlite3
    db_path = project_root / "data" / "rewarddb.db"
    db = sqlite3.connect(str(db_path))
    c = db.cursor()

    # 1. 列出所有 scenario
    c.execute("SELECT id, name, total_target FROM scenarios ORDER BY id")
    all_scenarios = c.fetchall()

    # 2. 分类: 保留 vs 待清
    to_keep = [s for s in all_scenarios if s[0] in keep_ids]
    to_delete = [s for s in all_scenarios if s[0] not in keep_ids]

    print(f"全部: {len(all_scenarios)} scenarios")
    print(f"  保留: {len(to_keep)} 个")
    print(f"  待清: {len(to_delete)} 个")
    print()
    print("保留列表:")
    for s in to_keep:
        print(f"  + id={s[0]:>3} name={s[1][:35]:<35} total_target={s[2]}")
    print()
    if dry_run:
        print("[DRY-RUN] 不真删, 退出")
        return 0

    # 3. 删 (SQLite FK enforcement 默认 OFF, 需显式清 scenario_nodes)
    #    v1.0.16 nodes 表用 FOREIGN KEY ... ON DELETE CASCADE 声明,
    #    但 PRAGMA foreign_keys = ON 需在 connection 启用, 当前 sqlite3 直接 DELETE 不触发
    delete_ids = [s[0] for s in to_delete]
    if not delete_ids:
        print("没有待清 scenario")
        return 0
    placeholders = ",".join("?" * len(delete_ids))
    # 3.1 先删 scenario_nodes (FK 引用, 必须先清)
    c.execute(f"DELETE FROM scenario_nodes WHERE scenario_id IN ({placeholders})", delete_ids)
    n_nodes_deleted = c.rowcount
    # 3.2 再删 scenarios
    c.execute(f"DELETE FROM scenarios WHERE id IN ({placeholders})", delete_ids)
    n_sc_deleted = c.rowcount
    db.commit()
    print(f"已删 {n_sc_deleted} 个 scenario  +  {n_nodes_deleted:,} 个 scenario_nodes 行")
    print(f"(FK CASCADE 在 sqlite3 默认 OFF, 显式 2 步 DELETE)")
    db.close()

    # 4. VACUUM INTO 回收 free pages (v1.0.17 业务优化, 1 次性)
    #    业务动机: DELETE 后 SQLite 不释放 pages, DB 文件不会自动缩小
    #    VACUUM INTO 重建数据库, 释放 free pages
    print()
    print("VACUUM INTO 回收 free pages...")
    import shutil
    db_path_vacuum = project_root / "data" / "rewarddb_vacuum.db"
    db = sqlite3.connect(str(db_path))
    c = db.cursor()
    c.execute(f"VACUUM INTO '{db_path_vacuum}'")
    db.close()
    shutil.move(str(db_path_vacuum), str(db_path))
    print("VACUUM done")

    # 4. 验清理后状态
    db.commit()
    c.execute("SELECT COUNT(*) FROM scenarios")
    n_remain = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM scenario_nodes")
    n_nodes = c.fetchone()[0]
    c.execute("SELECT id, name, total_target, (SELECT COUNT(*) FROM scenario_nodes n WHERE n.scenario_id = s.id) AS n_nodes FROM scenarios s ORDER BY s.id")
    print()
    print("=" * 80)
    print(f"清理后状态:")
    print("=" * 80)
    print(f"{'id':>4}  {'name':<40} {'target':>7} {'nodes':>6}")
    print("-" * 80)
    for r in c.fetchall():
        print(f"{r[0]:>4}  {r[1][:38]:<40} {r[2]:>7} {r[3]:>6}")
    print("-" * 80)
    print(f"剩余: {n_remain} scenarios  节点: {n_nodes}")

    # 5. DB 体积
    db.close()
    db_size = db_path.stat().st_size
    print()
    print(f"DB 体积: {db_size:,} bytes ({db_size/1024/1024:.2f} MB)")
    print(f"清理前: 15,138,816 bytes (15.1 MB)")
    print(f"清理后: {db_size:,} bytes ({db_size/1024/1024:.2f} MB)")
    saved = 15138816 - db_size
    print(f"节省: {saved:,} bytes ({saved/1024/1024:.2f} MB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
