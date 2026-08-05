# -*- coding: utf-8 -*-
r"""
test_migrate_original_to_members.py —— 原树迁入 members 迁移脚本测试 (2026-08-05)
=====================================================================================

业务背景:
  - tools/migrate_original_to_members.py 把 original_tree_nodes (264 节点真实网体,
    root=万陵洋 A8066781.1) 迁进 members 表
  - 保留原编号 (不重编号), PV 全置 0, max_lines 钳到 5

测试覆盖 (全部用 tmp_path 临时 DB, 不打 live DB):
    1. 行数 = original_tree_nodes 节点数
    2. root (parent_id NULL) → slot_line_id=0, max_lines 8 钳到 5
    3. parent_dist_id / slot_line_id 映射正确 (含 A 格式 dist_id)
    4. role 默认 '消费股东', current_pv_balance=0, total_commission=0.0
    5. 幂等保护: members 非空时拒绝执行 (SystemExit code 1)
    6. --force 重跑: 先清 pv_ledger + members, 再插入
"""
import sqlite3
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.migrate_original_to_members import migrate  # noqa: E402


DDL_ORIGINAL = """
CREATE TABLE original_tree_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dist_id VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(128),
    level INTEGER,
    max_lines INTEGER,
    parent_id VARCHAR(64),
    parent_line_id INTEGER
)
"""

DDL_MEMBERS = """
CREATE TABLE members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_dist_id VARCHAR(64) NOT NULL UNIQUE,
    member_name VARCHAR(128),
    parent_dist_id VARCHAR(64),
    slot_line_id INTEGER,
    max_lines INTEGER NOT NULL DEFAULT 2,
    current_pv_balance INTEGER NOT NULL DEFAULT 0,
    total_commission FLOAT NOT NULL DEFAULT 0.0,
    role VARCHAR(64) NOT NULL DEFAULT '消费股东',
    created_period_id VARCHAR(16),
    last_period_id VARCHAR(16),
    created_at FLOAT NOT NULL,
    updated_at FLOAT NOT NULL
)
"""

DDL_PV_LEDGER = """
CREATE TABLE pv_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    member_dist_id VARCHAR(64) NOT NULL,
    period_id VARCHAR(16) NOT NULL,
    pv_amount INTEGER NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending'
)
"""


class TestMigrateOriginalToMembers(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(self.id().replace(".", "_"))
        # 用 pytest tmp_path 不方便 (unittest), 改用 tempfile
        import tempfile
        self._dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._dir.name) / "test.db"
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(DDL_ORIGINAL)
            conn.execute(DDL_MEMBERS)
            conn.execute(DDL_PV_LEDGER)
            # 小样例: root (A 格式, max_lines=8) + 2 直推 + 1 孙
            rows = [
                # dist_id, name, level, max_lines, parent_id, parent_line_id
                ("A8066781.1", " 万陵洋 ", 0, 8, None, None),          # root, name 带空格测 strip
                ("A8066781.2", "直推甲", 1, 5, "A8066781.1", 1),
                ("N6000671.1", "直推乙", 1, 5, "A8066781.1", 2),
                ("A8066781.3", "孙丙", 2, 5, "A8066781.2", 1),
            ]
            conn.executemany(
                "INSERT INTO original_tree_nodes (dist_id, name, level, max_lines, parent_id, parent_line_id)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        self._dir.cleanup()

    def _conn(self):
        return sqlite3.connect(str(self.db_path))

    def _members(self):
        conn = self._conn()
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(members)").fetchall()]
            out = {}
            for r in conn.execute("SELECT * FROM members").fetchall():
                d = dict(zip(cols, r))
                out[d["member_dist_id"]] = d
            return out
        finally:
            conn.close()

    def test_insert_count(self):
        inserted = migrate(self.db_path, verbose=False)
        self.assertEqual(inserted, 4)
        self.assertEqual(len(self._members()), 4)

    def test_root_fields(self):
        migrate(self.db_path, verbose=False)
        root = self._members()["A8066781.1"]
        self.assertIsNone(root["parent_dist_id"])
        self.assertEqual(root["slot_line_id"], 0)          # root → 0
        self.assertEqual(root["max_lines"], 5)             # 原值 8 钳到 5
        self.assertEqual(root["member_name"], "万陵洋")     # strip
        self.assertEqual(root["current_pv_balance"], 0)    # 原 pv 不带入
        self.assertEqual(root["total_commission"], 0.0)
        self.assertEqual(root["role"], "消费股东")
        self.assertIsNone(root["last_period_id"])
        self.assertTrue(root["created_period_id"])          # 当前业务周

    def test_parent_slot_mapping(self):
        migrate(self.db_path, verbose=False)
        ms = self._members()
        self.assertEqual(ms["A8066781.2"]["parent_dist_id"], "A8066781.1")
        self.assertEqual(ms["A8066781.2"]["slot_line_id"], 1)
        self.assertEqual(ms["N6000671.1"]["parent_dist_id"], "A8066781.1")
        self.assertEqual(ms["N6000671.1"]["slot_line_id"], 2)
        self.assertEqual(ms["A8066781.3"]["parent_dist_id"], "A8066781.2")
        self.assertEqual(ms["A8066781.3"]["slot_line_id"], 1)

    def test_idempotent_refuse_when_members_not_empty(self):
        migrate(self.db_path, verbose=False)
        # 第二次跑: members 非空, 拒绝
        with self.assertRaises(SystemExit) as ctx:
            migrate(self.db_path, verbose=False)
        self.assertEqual(ctx.exception.code, 1)
        # 数据没变
        self.assertEqual(len(self._members()), 4)

    def test_force_rerun(self):
        migrate(self.db_path, verbose=False)
        # 塞一条 pv_ledger, 验证 --force 会先清
        conn = self._conn()
        conn.execute(
            "INSERT INTO pv_ledger (member_id, member_dist_id, period_id, pv_amount, status)"
            " VALUES (1, 'A8066781.1', '2026-08-02_W32', 500, 'pending')"
        )
        conn.commit()
        conn.close()
        inserted = migrate(self.db_path, force=True, verbose=False)
        self.assertEqual(inserted, 4)
        self.assertEqual(len(self._members()), 4)
        conn = self._conn()
        ledger_cnt = conn.execute("SELECT COUNT(*) FROM pv_ledger").fetchone()[0]
        conn.close()
        self.assertEqual(ledger_cnt, 0)  # force 清掉了

    def test_missing_db_exit_1(self):
        with self.assertRaises(SystemExit) as ctx:
            migrate(Path(self._dir.name) / "nonexistent.db", verbose=False)
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
