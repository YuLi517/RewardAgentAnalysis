# -*- coding: utf-8 -*-
"""
migrate_pr75_business_level.py — PR #75: 加 members.business_level 字段
====================================================================

业务 (2026-08-06 用户拍板截图):
  - 4 档位: 激活 / 商务 / 精英 / 至尊 (跟 PR #71 teamBonus 4 档对应)
  - 独立列 business_level 存, 跟 role 字段独立
  - default = '激活' (最普通档位)

迁移:
  1. ALTER TABLE members ADD COLUMN business_level VARCHAR(32) NOT NULL DEFAULT '激活'
  2. backfill 0 行 (新字段 default 已 '激活', 旧 2144 节点全部默认 '激活')
  3. 加索引 idx_business_level (跟 role 字段索引一致)
  4. 幂等: 字段已存在则跳过 ALTER
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

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
    if "business_level" in cols:
        print("[migrate_pr75_business_level] members.business_level 字段已存在, 跳过 ALTER (幂等)")
    else:
        print("[migrate_pr75_business_level] ALTER TABLE members ADD COLUMN business_level VARCHAR(32) NOT NULL DEFAULT '激活'")
        cur.execute("ALTER TABLE members ADD COLUMN business_level VARCHAR(32) NOT NULL DEFAULT '激活'")
        conn.commit()
        print("[migrate_pr75_business_level] ALTER 成功")

    # 2. backfill (新字段 default 已 '激活', 旧 2144 节点全部默认 '激活', 保险跑一下)
    cur.execute("UPDATE members SET business_level = '激活' WHERE business_level IS NULL OR business_level = ''")
    conn.commit()
    print("[migrate_pr75_business_level] backfill '激活' 完成")

    # 3. 加索引 (idx_business_level, 跟 role 字段 idx_role 一致)
    cur.execute("PRAGMA index_list(members)")
    indexes = [row[1] for row in cur.fetchall()]
    if "ix_members_business_level" not in indexes:
        print("[migrate_pr75_business_level] CREATE INDEX ix_members_business_level")
        cur.execute("CREATE INDEX ix_members_business_level ON members (business_level)")
        conn.commit()
        print("[migrate_pr75_business_level] 索引创建成功")
    else:
        print("[migrate_pr75_business_level] 索引 ix_members_business_level 已存在, 跳过")

    # 4. 验证
    cur.execute("SELECT COUNT(*) FROM members")
    total = cur.fetchone()[0]
    cur.execute("SELECT business_level, COUNT(*) FROM members GROUP BY business_level")
    by_level = cur.fetchall()
    print(f"[migrate_pr75_business_level] 验证: 共 {total} 行")
    for level, n in by_level:
        print(f"  {level}: {n}")

    conn.close()
    print("[migrate_pr75_business_level] DONE")


if __name__ == "__main__":
    main()
