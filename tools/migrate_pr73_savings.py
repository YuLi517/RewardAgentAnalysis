# -*- coding: utf-8 -*-
"""
migrate_pr73_savings.py — PR #73: 加 members.savings_balance 字段
====================================================================

业务 (用户 2026-08-06 拍板):
  - 储蓄奖金 (Savings Bonus): ownBasic ≥ $250 时, savings = min(ownBasic × 15%, $500)
  - 跨期累计到 members.savings_balance 字段
  - 跟 current_pv_balance 独立, 不混

迁移:
  1. ALTER TABLE members ADD COLUMN savings_balance FLOAT NOT NULL DEFAULT 0.0
  2. backfill 0.0 (历史没有, 全部从 0 起步)
  3. 幂等: 字段已存在则跳过 ALTER (避免重跑报错)

部署:
  python tools/migrate_pr73_savings.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# DB 路径
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "rewarddb.db"


def main():
    if not DB_PATH.exists():
        print(f"DB 不存在: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # 1. 查字段是否已存在
    cur.execute("PRAGMA table_info(members)")
    cols = [row[1] for row in cur.fetchall()]
    if "savings_balance" in cols:
        print("[migrate_pr73_savings] members.savings_balance 字段已存在, 跳过 ALTER (幂等)")
    else:
        print("[migrate_pr73_savings] ALTER TABLE members ADD COLUMN savings_balance FLOAT NOT NULL DEFAULT 0.0")
        cur.execute("ALTER TABLE members ADD COLUMN savings_balance FLOAT NOT NULL DEFAULT 0.0")
        conn.commit()
        print("[migrate_pr73_savings] ALTER 成功")

    # 2. backfill 0.0 (新字段 default 已 0, 无需额外更新; 但保险跑一下)
    cur.execute("UPDATE members SET savings_balance = 0.0 WHERE savings_balance IS NULL")
    conn.commit()
    print("[migrate_pr73_savings] backfill 0.0 完成")

    # 3. 验证
    cur.execute("SELECT COUNT(*) FROM members")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*), SUM(savings_balance) FROM members")
    n, total_savings = cur.fetchone()
    print(f"[migrate_pr73_savings] 验证: 共 {n}/{total} 行, savings_balance 累加 = {total_savings or 0.0}")

    conn.close()
    print("[migrate_pr73_savings] DONE")


if __name__ == "__main__":
    main()
