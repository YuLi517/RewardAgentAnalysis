# -*- coding: utf-8 -*-
"""
migrate_pr55_period_id.py —— PR #55 业务周 (Sun-Fri) + 补录窗口 数据迁移
=============================================================================

PR #55 业务规则变更 (2026-07-20):
  - 周期 ID 格式: "2026-W29" (ISO 周) → "2026-07-12_W29" (业务周, Sun-Fri)
  - 范围: Mon-Sun → Sun-Fri (6 天)
  - 补录窗口: 新增 Sat-Mon (3 天), 只能补基本 commission
  - commission_periods 表加 supplement_until_ts / supplement_commission / supplement_count 列

迁移步骤 (idempotent, 多次跑安全):
  1. ALTER TABLE 加新列 (IF NOT EXISTS, SQLite 不支持, 用 try/except)
  2. UPDATE commission_periods.id (旧 ISO 格式 → 新业务格式)
  3. UPDATE pv_ledger.period_id (同上)
  4. UPDATE members.created_period_id (同上)
  5. UPDATE members.last_period_id (同上)
  6. UPDATE commission_periods.supplement_until_ts (settled 状态行 = end_at + 3 天)
  7. UPDATE commission_periods.status: 'settled' + supplement_until_ts 过期 → 'closed'

使用:
  python tools/migrate_pr55_period_id.py
  # 默认迁移 data/rewarddb.db, 可以传 --db-path 改路径

幂等性:
  - 新列已存在: ALTER TABLE 失败 (try/except skip)
  - 旧 ID 已迁移: id 字符串不匹配 "YYYY-Www" 模式, skip
  - 重复跑安全
"""
import argparse
import re
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from skills.period import (
    get_supplement_range,
    get_period_range,
    migrate_old_period_id,
)


# 旧 ID 格式: "2026-W29" (ISO 周)
_OLD_ID_RE = re.compile(r"^\d{4}-W\d{2}$")


def _get_existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """拿表的现有列名"""
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _safe_add_column(conn: sqlite3.Connection, table: str, column_def: str, column_name: str) -> bool:
    """加列 (已存在跳过, 返回 True=真加了, False=已存在跳过)"""
    if column_name in _get_existing_columns(conn, table):
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
    return True


def migrate(db_path: str) -> dict:
    """执行迁移, 返回统计 dict"""
    conn = sqlite3.connect(db_path)
    stats = {
        "columns_added": [],
        "periods_migrated": 0,
        "ledgers_migrated": 0,
        "members_created_updated": 0,
        "members_last_updated": 0,
        "supplement_until_set": 0,
        "statuses_updated": 0,
    }

    try:
        # ============== 1. 加新列 ==============
        if _safe_add_column(conn, "commission_periods",
                            "supplement_until_ts FLOAT", "supplement_until_ts"):
            stats["columns_added"].append("commission_periods.supplement_until_ts")
        if _safe_add_column(conn, "commission_periods",
                            "supplement_commission FLOAT NOT NULL DEFAULT 0", "supplement_commission"):
            stats["columns_added"].append("commission_periods.supplement_commission")
        if _safe_add_column(conn, "commission_periods",
                            "supplement_count INTEGER NOT NULL DEFAULT 0", "supplement_count"):
            stats["columns_added"].append("commission_periods.supplement_count")

        # 也扩大 id 字段长度 (SQLite 不支持 ALTER COLUMN, 重建表)
        # 但实际上 SQLite VARCHAR 类型只是 hint, 不强制长度, 可以不重建
        # 如果需要严格限制, 后续 PR 用 Alembic 迁移

        conn.commit()

        # ============== 2. UPDATE commission_periods.id ==============
        old_periods = [
            row[0] for row in
            conn.execute("SELECT id FROM commission_periods").fetchall()
            if _OLD_ID_RE.match(row[0])
        ]
        for old_id in old_periods:
            new_id = migrate_old_period_id(old_id)
            conn.execute(
                "UPDATE commission_periods SET id = ? WHERE id = ?",
                (new_id, old_id)
            )
            stats["periods_migrated"] += 1
        conn.commit()

        # ============== 3. UPDATE pv_ledger.period_id ==============
        # 收集所有出现过的旧 period_id (从 ledger + members.created_period_id + members.last_period_id)
        all_old_periods = set()
        for row in conn.execute("SELECT DISTINCT period_id FROM pv_ledger").fetchall():
            if _OLD_ID_RE.match(row[0]):
                all_old_periods.add(row[0])
        for col in ["created_period_id", "last_period_id"]:
            for row in conn.execute(f"SELECT DISTINCT {col} FROM members").fetchall():
                if row[0] and _OLD_ID_RE.match(row[0]):
                    all_old_periods.add(row[0])

        for old_id in all_old_periods:
            new_id = migrate_old_period_id(old_id)
            cursor = conn.execute(
                "UPDATE pv_ledger SET period_id = ? WHERE period_id = ?",
                (new_id, old_id)
            )
            stats["ledgers_migrated"] += cursor.rowcount
        conn.commit()

        # ============== 4. UPDATE members.created_period_id ==============
        for old_id in all_old_periods:
            new_id = migrate_old_period_id(old_id)
            cursor = conn.execute(
                "UPDATE members SET created_period_id = ? WHERE created_period_id = ?",
                (new_id, old_id)
            )
            stats["members_created_updated"] += cursor.rowcount
        conn.commit()

        # ============== 5. UPDATE members.last_period_id ==============
        for old_id in all_old_periods:
            new_id = migrate_old_period_id(old_id)
            cursor = conn.execute(
                "UPDATE members SET last_period_id = ? WHERE last_period_id = ?",
                (new_id, old_id)
            )
            stats["members_last_updated"] += cursor.rowcount
        conn.commit()

        # ============== 6. UPDATE start_at / end_at / supplement_until_ts (按业务周) ==============
        # 业务规则: 
        #   start_at = Sun 00:00 (旧 ISO 周是 Mon 00:00, 需改)
        #   end_at = Fri 23:59:59.999 (旧 ISO 周是 Sun 23:59:59.999, 需改)
        #   supplement_until_ts = Mon 23:59:59.999 (仅 settled 状态)
        all_rows = conn.execute("SELECT id, status FROM commission_periods").fetchall()
        for pid, status in all_rows:
            try:
                new_start, new_end = get_period_range(pid)
                conn.execute(
                    "UPDATE commission_periods SET start_at = ?, end_at = ? WHERE id = ?",
                    (new_start, new_end, pid)
                )
                stats["supplement_until_set"] += 1
            except ValueError as e:
                print(f"[WARN] period {pid!r} get_period_range failed: {e}, skip")
        conn.commit()

        # supplement_until_ts (仅 settled/closed 状态)
        settled_rows = conn.execute(
            "SELECT id FROM commission_periods WHERE status IN ('settled', 'closed') "
            "AND supplement_until_ts IS NULL"
        ).fetchall()
        for (pid,) in settled_rows:
            try:
                _, sup_end = get_supplement_range(pid)
                conn.execute(
                    "UPDATE commission_periods SET supplement_until_ts = ? WHERE id = ?",
                    (sup_end, pid)
                )
            except ValueError as e:
                print(f"[WARN] period {pid!r} get_supplement_range failed: {e}, skip")
        conn.commit()

        # ============== 7. UPDATE status: 跟补录窗口同步 ==============
        # 业务规则:
        #   - settled + supplement_until_ts 还没过期 → status = 'settled' (可补)
        #   - settled + supplement_until_ts 已过期 → status = 'closed' (不可补)
        #   - 老的 'closed' 状态 + supplement_until_ts 还在未来 → 回退 'settled' (兼容)
        import time
        now_ts = time.time()
        # settled → closed (过期)
        cursor = conn.execute(
            "UPDATE commission_periods SET status = 'closed' "
            "WHERE status = 'settled' AND supplement_until_ts IS NOT NULL AND supplement_until_ts < ?",
            (now_ts,)
        )
        stats["statuses_updated"] = cursor.rowcount
        # closed → settled (回退, 兼容之前被错标的)
        cursor2 = conn.execute(
            "UPDATE commission_periods SET status = 'settled' "
            "WHERE status = 'closed' AND supplement_until_ts IS NOT NULL AND supplement_until_ts >= ?",
            (now_ts,)
        )
        stats["statuses_updated"] += cursor2.rowcount
        conn.commit()

    finally:
        conn.close()

    return stats


def verify(db_path: str) -> None:
    """验证迁移结果"""
    conn = sqlite3.connect(db_path)
    try:
        print()
        print("=" * 60)
        print("验证: commission_periods (PR #55 业务周格式)")
        print("=" * 60)
        for row in conn.execute(
            "SELECT id, status, start_at, end_at, supplement_until_ts, "
            "       total_commission, supplement_commission, supplement_count "
            "FROM commission_periods ORDER BY id"
        ).fetchall():
            print(f"  {row}")
        print()
        print("=" * 60)
        print("验证: pv_ledger period_id (应全部业务周格式)")
        print("=" * 60)
        for row in conn.execute(
            "SELECT m.member_dist_id, l.period_id, l.pv_amount, l.status "
            "FROM pv_ledger l JOIN members m ON m.id=l.member_id "
            "ORDER BY m.member_dist_id, l.period_id"
        ).fetchall():
            print(f"  {row}")
        print()
        print("=" * 60)
        print("验证: 旧 ISO 周 ID 残留 (期望 0 行)")
        print("=" * 60)
        old_residue = []
        for table in ["commission_periods", "pv_ledger", "members"]:
            if table == "commission_periods":
                cols = ["id"]
            elif table == "pv_ledger":
                cols = ["period_id"]
            else:  # members
                cols = ["created_period_id", "last_period_id"]
            for col in cols:
                # 旧格式: "2026-W29" (10 字符, ISO 周)
                # 新格式: "2026-07-12_W29" (13 字符, 业务周)
                rows = conn.execute(
                    f"SELECT {col} FROM {table} "
                    f"WHERE {col} GLOB '????-W??' AND {col} NOT GLOB '????-??-??_W??'"
                ).fetchall()
                if rows:
                    old_residue.append((table, col, rows))
        if old_residue:
            for table, col, rows in old_residue:
                print(f"  [WARN] {table}.{col}: {[r[0] for r in rows]}")
        else:
            print("  [OK] 无旧 ID 残留")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="PR #55 业务周 (Sun-Fri) 数据迁移")
    parser.add_argument("--db-path", default=None, help="SQLite DB 路径 (默认 data/rewarddb.db)")
    args = parser.parse_args()

    if args.db_path:
        db_path = args.db_path
    else:
        db_path = str(PROJECT_ROOT / "data" / "rewarddb.db")

    print(f"迁移 DB: {db_path}")
    if not Path(db_path).exists():
        print(f"[ERROR] DB 不存在: {db_path}")
        sys.exit(1)

    stats = migrate(db_path)
    print()
    print("=" * 60)
    print("迁移统计:")
    print("=" * 60)
    for k, v in stats.items():
        print(f"  {k}: {v}")

    verify(db_path)


if __name__ == "__main__":
    main()
