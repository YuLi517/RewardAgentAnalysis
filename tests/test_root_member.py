# -*- coding: utf-8 -*-
r"""
test_root_member.py —— 验证根节点 (王常军 N5637590.1) 在 members 表里
====================================================================

PR #28 验证:
    1. /api/members 包含根节点 (10 行)
    2. 根节点字段正确: name=王常军, parent_dist_id="", slot_line_id=0
    3. 根节点的子 (N-7000001/N-7000002) 的 parent_dist_id 仍然是 N5637590.1 (没破坏)
    4. 重复跑 init_root_member 幂等 (不会重复插入)
"""
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

import main  # noqa: E402
from database import SessionLocal
from models import Member  # noqa: E402
from tools.init_root_member import (  # noqa: E402
    ROOT_DIST_ID, ROOT_NAME, ROOT_CREATED_PERIOD,
    main as run_migration,
)


class TestRootMember(unittest.TestCase):
    """PR #28: 根节点 (王常军) 加到 members 表"""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def setUp(self):
        """每个测试: 清空 + 重建 fixture (无 root) + 跑 migration"""
        db = SessionLocal()
        try:
            db.query(Member).filter(Member.member_dist_id == ROOT_DIST_ID).delete()
            db.query(Member).filter(Member.member_dist_id.like("N-700%")).delete()
            db.commit()
        finally:
            db.close()
        # 跑 migration 插 root
        rc = run_migration()
        self.assertEqual(rc, 0)
        # 加 9 个 fixture 成员
        db = SessionLocal()
        try:
            for i in range(1, 10):
                db.add(Member(
                    member_dist_id=f"N-700000{i}",
                    member_name=f"张{i}",
                    parent_dist_id=ROOT_DIST_ID if i <= 2 else f"N-700000{i-1}",
                    slot_line_id=1 if i % 2 == 1 else 2,
                    max_lines=5, current_pv_balance=0, total_commission=0.0,
                    created_period_id="2026-07-12_W29", last_period_id="2026-07-12_W29",
                ))
            db.commit()
        finally:
            db.close()

    def tearDown(self):
        """每个测试: 清掉 root 和 fixture 成员"""
        db = SessionLocal()
        try:
            db.query(Member).filter(Member.member_dist_id == ROOT_DIST_ID).delete()
            db.query(Member).filter(Member.member_dist_id.like("N-700%")).delete()
            db.commit()
        finally:
            db.close()

    # ---------- migration 行为 ----------

    def test_migration_inserts_root(self):
        db = SessionLocal()
        try:
            m = db.query(Member).filter_by(member_dist_id=ROOT_DIST_ID).first()
            self.assertIsNotNone(m, "root 不在 members")
            self.assertEqual(m.member_name, ROOT_NAME)
            self.assertIsNone(m.parent_dist_id)  # 根, 无父
            self.assertEqual(m.slot_line_id, 0)  # 根, 无挂线
            self.assertEqual(m.max_lines, 5)
            self.assertEqual(m.current_pv_balance, 0)
            self.assertEqual(m.total_commission, 0.0)
            self.assertEqual(m.created_period_id, ROOT_CREATED_PERIOD)
            self.assertIsNone(m.last_period_id)
        finally:
            db.close()

    def test_migration_is_idempotent(self):
        """重跑 migration 不会重复插入 (应该 print '已在' 不报错)"""
        rc = run_migration()
        self.assertEqual(rc, 0)
        db = SessionLocal()
        try:
            cnt = db.query(Member).filter_by(member_dist_id=ROOT_DIST_ID).count()
            self.assertEqual(cnt, 1, "root 应该是 1 行, 不能有重复")
        finally:
            db.close()

    # ---------- /api/members 包含 root ----------

    def test_api_members_includes_root(self):
        r = self.client.get("/api/members")
        data = r.json()
        self.assertEqual(data["count"], 10)
        root = next((m for m in data["members"] if m["member_dist_id"] == ROOT_DIST_ID), None)
        self.assertIsNotNone(root, "root 不在 /api/members 返回里")
        self.assertEqual(root["member_name"], ROOT_NAME)
        self.assertEqual(root["parent_dist_id"], "")  # None → ""
        self.assertEqual(root["slot_line_id"], 0)

    def test_root_children_still_link_to_root(self):
        """加 root 行不能破坏现有 N-7000001/N-7000002 的 parent_dist_id"""
        r = self.client.get("/api/members")
        by_dist = {m["member_dist_id"]: m for m in r.json()["members"]}
        # 真实 fixture: N-7000001/2 是 root 的 L1 子
        self.assertEqual(by_dist["N-7000001"]["parent_dist_id"], ROOT_DIST_ID)
        self.assertEqual(by_dist["N-7000002"]["parent_dist_id"], ROOT_DIST_ID)
        # N-7000003 是 N-7000002 的子 (fixture: parent="N-700000{i-1}" when i>2)
        self.assertEqual(by_dist["N-7000003"]["parent_dist_id"], "N-7000002")

    def test_root_no_parent_display(self):
        """root 的 parent_dist_id 是空字符串, 前端会渲染成 '-'"""
        r = self.client.get("/api/members")
        root = next(m for m in r.json()["members"] if m["member_dist_id"] == ROOT_DIST_ID)
        self.assertEqual(root["parent_dist_id"], "")
        # 跟 other member 对比
        non_root = next(m for m in r.json()["members"] if m["member_dist_id"] == "N-7000001")
        self.assertNotEqual(non_root["parent_dist_id"], "")
        self.assertEqual(non_root["parent_dist_id"], ROOT_DIST_ID)


if __name__ == "__main__":
    unittest.main()
