# -*- coding: utf-8 -*-
"""
migrate_original_to_members.py —— 原版网体 (original_tree_nodes) 迁入 members 表
================================================================================

业务背景 (2026-08-05):
  - original_tree_nodes 表存了真实网体 (264 节点, root=万陵洋 A8066781.1,
    4 条直推线, 最深 13 层)
  - 用户拍板: 把这棵树直接迁进 members 表, 作为 commission 系统的正式网体
    1. 保留原编号 (A8066781.1 / N6000671.1 等直接进 members, 不重编号)
    2. 原 pv 字段不带入, members 全部 current_pv_balance=0
    3. 本期 PV 用新增的 POST /api/members/add_pv 逐个补录

字段映射:
  - member_dist_id    = dist_id (原编号, 不重编号)
  - member_name       = name.strip()
  - parent_dist_id    = parent_id (root 为 NULL)
  - slot_line_id      = root (parent_id IS NULL) → 0; 其余 → parent_line_id
  - max_lines         = min(max_lines or 5, 5) (root 原值 8, 钳到 5)
  - current_pv_balance= 0
  - total_commission  = 0.0
  - role              = '消费股东' (默认)
  - created_period_id = get_current_period_id() (当前业务周)
  - last_period_id    = None

幂等保护:
  - members 非空 → 拒绝执行, 退出码 1
  - --force → 先 DELETE pv_ledger 再 DELETE members (FK 顺序), 再插入

跑前自动备份 DB 到 data/rewarddb.db.bak-YYYY-MM-DD-pre-members-import (已存在则覆盖)

用法:
  python tools/migrate_original_to_members.py
  python tools/migrate_original_to_members.py --force
  python tools/migrate_original_to_members.py --db-path /path/to/db.db
"""
import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# PowerShell GBK 控制台兼容 (跟 AGENTS.md §5.13 一致)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from skills.period import get_current_period_id  # noqa: E402


def backup_db(db_path: Path) -> Path:
    """备份 DB 到 data/rewarddb.db.bak-YYYY-MM-DD-pre-members-import (已存在则覆盖)"""
    today = datetime.now().strftime("%Y-%m-%d")
    bak = db_path.parent / f"{db_path.name}.bak-{today}-pre-members-import"
    shutil.copy2(str(db_path), str(bak))
    return bak


def migrate(db_path, force: bool = False, verbose: bool = True) -> int:
    """核心迁移逻辑 (可 import, 测试用). 返回插入行数.

    members 非空且未 force → raise SystemExit(1)
    """
    db_path = Path(db_path)
    if not db_path.exists():
        print(f"ERROR: DB 不存在: {db_path}")
        raise SystemExit(1)

    conn = sqlite3.connect(str(db_path))
    try:
        # 1. 现状
        orig_cnt = conn.execute("SELECT COUNT(*) FROM original_tree_nodes").fetchone()[0]
        member_cnt = conn.execute("SELECT COUNT(*) FROM members").fetchone()[0]
        if verbose:
            print(f"original_tree_nodes: {orig_cnt} 行")
            print(f"members:             {member_cnt} 行")

        if orig_cnt == 0:
            print("ERROR: original_tree_nodes 是空的, 先跑 tools/migrate_original_tree.py")
            raise SystemExit(1)

        if member_cnt > 0:
            if not force:
                print(f"ERROR: members 表非空 ({member_cnt} 行), 拒绝执行 (幂等保护)")
                print("       确认要重跑时加 --force (会先 DELETE pv_ledger + members)")
                raise SystemExit(1)
            # force: 按 FK 顺序清 (pv_ledger 引用 members)
            n_ledger = conn.execute("DELETE FROM pv_ledger").rowcount
            n_members = conn.execute("DELETE FROM members").rowcount
            conn.commit()
            if verbose:
                print(f"--force: DELETE pv_ledger {n_ledger} 行, members {n_members} 行")

        # 2. 按 level 升序读 original_tree_nodes
        rows = conn.execute("""
            SELECT dist_id, name, level, max_lines, parent_id, parent_line_id
            FROM original_tree_nodes
            ORDER BY COALESCE(level, 999) ASC, id ASC
        """).fetchall()

        period_id = get_current_period_id()
        now = datetime.now().timestamp()

        # 3. 插入 members
        insert_sql = """
            INSERT INTO members (
                member_dist_id, member_name, parent_dist_id, slot_line_id,
                max_lines, current_pv_balance, total_commission, role,
                created_period_id, last_period_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 0, 0.0, '消费股东', ?, NULL, ?, ?)
        """
        inserted = 0
        for dist_id, name, level, max_lines, parent_id, parent_line_id in rows:
            is_root = parent_id is None
            slot_line_id = 0 if is_root else (parent_line_id or 0)
            ml = min(max_lines or 5, 5)
            conn.execute(insert_sql, (
                dist_id,
                (name or "").strip(),
                parent_id,
                slot_line_id,
                ml,
                period_id,
                now,
                now,
            ))
            inserted += 1
        conn.commit()

        if verbose:
            print(f"插入 members: {inserted} 行 (created_period_id={period_id})")

        # 4. 验证
        stats = verify(conn)
        if verbose:
            print(f"验证: root 数={stats['roots']} (期望 1), "
                  f"孤儿={stats['orphans']} (期望 0), "
                  f"重复槽位={stats['dup_slots']} (期望 0)")
            print("root + 4 条 L2 线抽样:")
            for r in stats["sample"]:
                print(f"  {r}")
        return inserted
    finally:
        conn.close()


def verify(conn) -> dict:
    """迁移后验证: root 唯一性 / 0 孤儿 / 0 重复槽位 / root+L2 抽样"""
    roots = conn.execute("""
        SELECT COUNT(*) FROM members
        WHERE parent_dist_id IS NULL AND (slot_line_id IS NULL OR slot_line_id = 0)
    """).fetchone()[0]
    orphans = conn.execute("""
        SELECT COUNT(*) FROM members c
        WHERE c.parent_dist_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM members p WHERE p.member_dist_id = c.parent_dist_id)
    """).fetchone()[0]
    dup_slots = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT parent_dist_id, slot_line_id, COUNT(*) AS n
            FROM members
            WHERE parent_dist_id IS NOT NULL
            GROUP BY parent_dist_id, slot_line_id
            HAVING n > 1
        )
    """).fetchone()[0]
    # root + 直推线抽样
    root_row = conn.execute("""
        SELECT member_dist_id, member_name FROM members
        WHERE parent_dist_id IS NULL AND (slot_line_id IS NULL OR slot_line_id = 0)
        LIMIT 1
    """).fetchone()
    sample = []
    if root_row:
        sample.append(f"root: {root_row[0]} ({root_row[1]})")
        for r in conn.execute("""
            SELECT member_dist_id, member_name, slot_line_id FROM members
            WHERE parent_dist_id = ?
            ORDER BY slot_line_id ASC
        """, (root_row[0],)).fetchall():
            sample.append(f"L{r[2]}: {r[0]} ({r[1]})")
    return {
        "roots": roots,
        "orphans": orphans,
        "dup_slots": dup_slots,
        "sample": sample,
    }


def main():
    ap = argparse.ArgumentParser(
        description="原版网体 (original_tree_nodes) 迁入 members 表 (幂等, 跑前自动备份 DB)",
    )
    ap.add_argument("--force", action="store_true",
                    help="members 非空时强制执行 (先 DELETE pv_ledger + members)")
    ap.add_argument("--db-path", default=None,
                    help="DB 路径, 默认 data/rewarddb.db")
    args = ap.parse_args()

    db_path = Path(args.db_path) if args.db_path else (PROJECT_ROOT / "data" / "rewarddb.db")
    print(f"DB: {db_path}")
    if not db_path.exists():
        print(f"ERROR: DB 不存在: {db_path}")
        sys.exit(1)

    bak = backup_db(db_path)
    print(f"备份: {bak}")

    inserted = migrate(db_path, force=args.force)
    print(f"\nmigration 完成 ({inserted} 行)")


if __name__ == "__main__":
    main()
