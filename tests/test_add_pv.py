# -*- coding: utf-8 -*-
r"""
test_add_pv.py —— POST /api/members/add_pv 端点测试 (2026-08-05)
================================================================

业务背景:
  - 原版网体 (original_tree_nodes, 264 节点, root=万陵洋 A8066781.1) 迁入 members 后,
    所有成员 current_pv_balance=0, 本期 PV 用 /api/members/add_pv 逐个补录
  - 端点只插 PVLedger(status="pending"), 不动 current_pv_balance (结算时才落账)

测试覆盖:
    1. 成员不存在 → 404
    2. pv_amount <= 0 → 422 (Pydantic gt=0)
    3. 成功: ledger 行写入, period_id == get_current_period_id(),
       current_pv_balance 不变, 返回字段完整
    4. _member_to_uid A 号段 (7×10^12 起): A 格式唯一大整数 / 两 A 不撞 /
       跟 N5637590.X 号段不撞 / N6000671.1 保持旧 fallback 行为

注意 (AGENTS.md §11): 本测试用 worktree 自己的 data/ DB (database.py 按 __file__
锚定路径), setUp 全清 members/pv_ledger, 不污染主仓 live DB。
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
from models import Member, PVLedger, CommissionPeriod  # noqa: E402
from skills.period import get_current_period_id  # noqa: E402


class TestAddPvApi(unittest.TestCase):
    """POST /api/members/add_pv"""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def setUp(self):
        """每个测试: 清空 + seed root (A 格式) + 1 个成员"""
        db = SessionLocal()
        try:
            db.query(PVLedger).delete()
            db.query(Member).delete()
            db.query(CommissionPeriod).delete()
            db.add(Member(
                member_dist_id="A8066781.1", member_name="万陵洋",
                parent_dist_id=None, slot_line_id=0,
                max_lines=5, current_pv_balance=0, total_commission=0.0,
                created_period_id="2026-08-02_W32", last_period_id=None,
            ))
            db.add(Member(
                member_dist_id="A8066781.2", member_name="直推甲",
                parent_dist_id="A8066781.1", slot_line_id=1,
                max_lines=5, current_pv_balance=123, total_commission=0.0,
                created_period_id="2026-08-02_W32", last_period_id=None,
            ))
            db.commit()
        finally:
            db.close()

    def test_member_not_found_404(self):
        r = self.client.post("/api/members/add_pv", json={
            "member_dist_id": "A9999999.9", "pv_amount": 500,
        })
        self.assertEqual(r.status_code, 404)

    def test_pv_zero_422(self):
        r = self.client.post("/api/members/add_pv", json={
            "member_dist_id": "A8066781.1", "pv_amount": 0,
        })
        self.assertEqual(r.status_code, 422)

    def test_pv_negative_422(self):
        r = self.client.post("/api/members/add_pv", json={
            "member_dist_id": "A8066781.1", "pv_amount": -100,
        })
        self.assertEqual(r.status_code, 422)

    def test_success_writes_pending_ledger(self):
        r = self.client.post("/api/members/add_pv", json={
            "member_dist_id": "A8066781.2", "pv_amount": 500, "note": "补录",
        })
        self.assertEqual(r.status_code, 200)
        data = r.json()
        current_period = get_current_period_id()
        self.assertTrue(data["ok"])
        self.assertEqual(data["member_dist_id"], "A8066781.2")
        self.assertEqual(data["member_name"], "直推甲")
        self.assertEqual(data["pv_amount"], 500)
        self.assertEqual(data["period_id"], current_period)
        self.assertTrue(data["ledger_id"])

        db = SessionLocal()
        try:
            ledger = db.query(PVLedger).filter_by(member_dist_id="A8066781.2").one()
            self.assertEqual(ledger.pv_amount, 500)
            self.assertEqual(ledger.status, "pending")
            self.assertEqual(ledger.period_id, current_period)
            self.assertEqual(ledger.note, "补录")
            # current_pv_balance 不动 (结算时才落账)
            m = db.query(Member).filter_by(member_dist_id="A8066781.2").one()
            self.assertEqual(m.current_pv_balance, 123)
        finally:
            db.close()


class TestMemberToUidASegment(unittest.TestCase):
    """_member_to_uid A 号段 (7×10^12 起) — 通过 _build_node5_tree_from_db 的
    uid_to_dist_id 反查表验证 (嵌套闭包, 不能直接 import)"""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def setUp(self):
        db = SessionLocal()
        try:
            db.query(PVLedger).delete()
            db.query(Member).delete()
            db.query(CommissionPeriod).delete()
            # root A 格式 + 3 个子 (A / N 旧格式 / N5637590 新格式)
            db.add(Member(
                member_dist_id="A8066781.1", member_name="万陵洋",
                parent_dist_id=None, slot_line_id=0,
                max_lines=5, current_pv_balance=0, total_commission=0.0,
                created_period_id="2026-08-02_W32", last_period_id=None,
            ))
            db.add(Member(
                member_dist_id="A8066781.2", member_name="甲",
                parent_dist_id="A8066781.1", slot_line_id=1,
                max_lines=5, current_pv_balance=0, total_commission=0.0,
                created_period_id="2026-08-02_W32", last_period_id=None,
            ))
            db.add(Member(
                member_dist_id="N6000671.1", member_name="乙",
                parent_dist_id="A8066781.1", slot_line_id=2,
                max_lines=5, current_pv_balance=0, total_commission=0.0,
                created_period_id="2026-08-02_W32", last_period_id=None,
            ))
            db.add(Member(
                member_dist_id="N5637590.7", member_name="丙",
                parent_dist_id="A8066781.1", slot_line_id=3,
                max_lines=5, current_pv_balance=0, total_commission=0.0,
                created_period_id="2026-08-02_W32", last_period_id=None,
            ))
            db.commit()
        finally:
            db.close()

    def _uid_map(self):
        db = SessionLocal()
        try:
            _root, uid_to_dist_id = main._build_node5_tree_from_db(db)
            # 反转: dist_id → uid
            return {v: k for k, v in uid_to_dist_id.items()}
        finally:
            db.close()

    def test_a_format_uid_large_unique(self):
        dist_to_uid = self._uid_map()
        uid_a1 = dist_to_uid["A8066781.1"]
        # 7×10^12 + 8066781*100 + 1
        self.assertEqual(uid_a1, 7_000_000_000_000 + 8066781 * 100 + 1)

    def test_two_a_ids_no_collision(self):
        dist_to_uid = self._uid_map()
        self.assertNotEqual(dist_to_uid["A8066781.1"], dist_to_uid["A8066781.2"])
        # uid 非 0 (不撞 avail 占位保留值)
        self.assertNotEqual(dist_to_uid["A8066781.1"], 0)
        self.assertNotEqual(dist_to_uid["A8066781.2"], 0)

    def test_a_segment_no_collision_with_n5637590(self):
        dist_to_uid = self._uid_map()
        uid_n = dist_to_uid["N5637590.7"]
        self.assertEqual(uid_n, 5637590 * 100_000_000 + 7)
        self.assertNotEqual(dist_to_uid["A8066781.1"], uid_n)
        self.assertNotEqual(dist_to_uid["A8066781.2"], uid_n)

    def test_n_old_format_fallback_unchanged(self):
        dist_to_uid = self._uid_map()
        # N6000671.1 → fallback: "6000671.1".split(".")[0] = 6000671 (旧行为)
        self.assertEqual(dist_to_uid["N6000671.1"], 6000671)


if __name__ == "__main__":
    unittest.main()
