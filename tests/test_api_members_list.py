# -*- coding: utf-8 -*-
r"""
test_api_members_list.py —— /api/members 端点测试 (PR #27)
==============================================================

PR #27 (2026-07-16) 加 4 个返回字段:
    - parent_dist_id          : 父节点 distId (空 = root)
    - slot_line_id            : 在父节点的第几条线 (1..maxLines)
    - last_period_remaining_pv: 上周结算后剩余 PV (= current_pv_balance)
    - last_period_deducted_pv : 上周结算时本成员被 paired 消耗的 PV 之和
                                  (从 pv_ledger 聚合: status=paired AND period_id=last_period_id,
                                   SUM(contribution_pv))

测试覆盖:
    1. 字段完整性: 9 个字段都在 (含新 4 个)
    2. parent_dist_id / slot_line_id 跟 DB 一致
    3. last_period_remaining_pv == current_pv_balance
    4. last_period_deducted_pv 聚合正确 (按 member+period group sum contribution_pv)
    5. 没有 last_period_id 的成员: deducted=0
    6. 没有 paired ledger 的成员: deducted=0
    7. carried ledger 不算进 deducted (只算 paired)
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


class TestApiMembersListPR27(unittest.TestCase):
    """PR #27: /api/members 加 4 字段"""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def setUp(self):
        """每个测试: 清空, 重建 fixture"""
        db = SessionLocal()
        try:
            db.query(PVLedger).delete()
            db.query(Member).delete()
            db.query(CommissionPeriod).delete()
            db.commit()
        finally:
            db.close()
        self._build_fixture()

    def _build_fixture(self):
        """3 个成员, 1 个 period, 4 条 ledger:
            M1: paired 2500 (W29)
            M1: carried 1500 (W29)  ← 不算进 deducted
            M2: paired 700 (W29)
            M3: pending 800 (W29)  ← pending 不算
        """
        db = SessionLocal()
        try:
            period = CommissionPeriod(
                id="2026-07-12_W29", period_type="weekly",
                start_at=1783872000.0, end_at=1784476799.999,
                status="settled", total_commission=0.0,
                total_pv_consumed=3200, total_pv_carried=1500,
                member_count=3, settled_at=1784171112.0, settled_by="system",
            )
            db.add(period)

            m1 = Member(member_dist_id="N-7000001", member_name="甲",
                        parent_dist_id="N-ROOT", slot_line_id=1,
                        max_lines=5, current_pv_balance=100,
                        total_commission=0.0,
                        created_period_id="2026-07-12_W29", last_period_id="2026-07-12_W29")
            m2 = Member(member_dist_id="N-7000002", member_name="乙",
                        parent_dist_id="N-ROOT", slot_line_id=2,
                        max_lines=5, current_pv_balance=200,
                        total_commission=0.0,
                        created_period_id="2026-07-12_W29", last_period_id="2026-07-12_W29")
            m3 = Member(member_dist_id="N-7000003", member_name="丙",
                        parent_dist_id="N-7000001", slot_line_id=1,
                        max_lines=5, current_pv_balance=300,
                        total_commission=0.0,
                        created_period_id="2026-07-12_W29", last_period_id="2026-07-12_W29")
            db.add_all([m1, m2, m3])
            db.flush()

            # M1: 1 paired (2500) + 1 carried (1500) → deducted=2500
            db.add(PVLedger(member_id=m1.id, member_dist_id="N-7000001",
                            period_id="2026-07-12_W29", pv_amount=2500,
                            status="paired", contribution_pv=2500,
                            commission_amount=100.0))
            db.add(PVLedger(member_id=m1.id, member_dist_id="N-7000001",
                            period_id="2026-07-12_W29", pv_amount=1500,
                            status="carried", contribution_pv=0,
                            commission_amount=0.0))
            # M2: 1 paired (700) → deducted=700
            db.add(PVLedger(member_id=m2.id, member_dist_id="N-7000002",
                            period_id="2026-07-12_W29", pv_amount=700,
                            status="paired", contribution_pv=700,
                            commission_amount=50.0))
            # M3: 1 pending (800) → 不算 deducted
            db.add(PVLedger(member_id=m3.id, member_dist_id="N-7000003",
                            period_id="2026-07-12_W29", pv_amount=800,
                            status="pending", contribution_pv=0,
                            commission_amount=0.0))
            db.commit()
        finally:
            db.close()

    # ---------- 字段完整性 ----------

    def test_count_equals_member_count(self):
        r = self.client.get("/api/members")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["count"], 3)
        self.assertEqual(len(data["members"]), 3)

    def test_required_fields_present(self):
        """9 个字段都在 (PR #27 新加 4 个)"""
        r = self.client.get("/api/members")
        data = r.json()
        for m in data["members"]:
            for key in [
                "member_dist_id", "member_name",
                "parent_dist_id", "slot_line_id",
                "current_pv_balance", "last_period_remaining_pv",
                "last_period_deducted_pv",
                "total_commission", "created_period_id", "last_period_id",
            ]:
                self.assertIn(key, m, f"缺少字段: {key}")

    # ---------- parent_dist_id / slot_line_id ----------

    def test_parent_dist_id_from_db(self):
        r = self.client.get("/api/members")
        by_dist = {m["member_dist_id"]: m for m in r.json()["members"]}
        self.assertEqual(by_dist["N-7000001"]["parent_dist_id"], "N-ROOT")
        self.assertEqual(by_dist["N-7000002"]["parent_dist_id"], "N-ROOT")
        self.assertEqual(by_dist["N-7000003"]["parent_dist_id"], "N-7000001")

    def test_slot_line_id_from_db(self):
        r = self.client.get("/api/members")
        by_dist = {m["member_dist_id"]: m for m in r.json()["members"]}
        self.assertEqual(by_dist["N-7000001"]["slot_line_id"], 1)
        self.assertEqual(by_dist["N-7000002"]["slot_line_id"], 2)
        self.assertEqual(by_dist["N-7000003"]["slot_line_id"], 1)

    def test_root_member_parent_dist_id_empty(self):
        """parent 为 root 的成员, parent_dist_id="" (不是 None)"""
        db = SessionLocal()
        try:
            db.add(Member(member_dist_id="N-ROOT-SUB", member_name="根下",
                          parent_dist_id="", slot_line_id=1,
                          max_lines=5, current_pv_balance=0,
                          total_commission=0.0,
                          created_period_id="2026-07-12_W29", last_period_id="2026-07-12_W29"))
            db.commit()
        finally:
            db.close()
        r = self.client.get("/api/members")
        m = next(x for x in r.json()["members"] if x["member_dist_id"] == "N-ROOT-SUB")
        self.assertEqual(m["parent_dist_id"], "")
        self.assertEqual(m["slot_line_id"], 1)

    # ---------- last_period_remaining_pv ----------

    def test_remaining_pv_equals_current_balance(self):
        """last_period_remaining_pv == current_pv_balance (同名别名)"""
        r = self.client.get("/api/members")
        for m in r.json()["members"]:
            self.assertEqual(
                m["last_period_remaining_pv"], m["current_pv_balance"],
                f"{m['member_dist_id']}: remaining={m['last_period_remaining_pv']} != "
                f"current={m['current_pv_balance']}",
            )

    def test_remaining_pv_values(self):
        r = self.client.get("/api/members")
        by_dist = {m["member_dist_id"]: m for m in r.json()["members"]}
        self.assertEqual(by_dist["N-7000001"]["last_period_remaining_pv"], 100)
        self.assertEqual(by_dist["N-7000002"]["last_period_remaining_pv"], 200)
        self.assertEqual(by_dist["N-7000003"]["last_period_remaining_pv"], 300)

    # ---------- last_period_deducted_pv (核心) ----------

    def test_deducted_pv_aggregation(self):
        """聚合: paired status + sum(contribution_pv)"""
        r = self.client.get("/api/members")
        by_dist = {m["member_dist_id"]: m for m in r.json()["members"]}
        self.assertEqual(by_dist["N-7000001"]["last_period_deducted_pv"], 2500)
        self.assertEqual(by_dist["N-7000002"]["last_period_deducted_pv"], 700)
        self.assertEqual(by_dist["N-7000003"]["last_period_deducted_pv"], 0)  # pending 不算

    def test_deducted_excludes_carried(self):
        """M1 的 carried ledger 1500 不算进 deducted (只算 paired)"""
        r = self.client.get("/api/members")
        m1 = next(x for x in r.json()["members"] if x["member_dist_id"] == "N-7000001")
        # M1: paired 2500 + carried 1500, deducted 只算 paired = 2500
        self.assertEqual(m1["last_period_deducted_pv"], 2500)

    def test_deducted_zero_when_no_last_period(self):
        """没 last_period_id 的成员, deducted=0"""
        db = SessionLocal()
        try:
            db.add(Member(member_dist_id="N-NEW", member_name="新人",
                          parent_dist_id="N-ROOT", slot_line_id=1,
                          max_lines=5, current_pv_balance=0,
                          total_commission=0.0,
                          created_period_id="2026-07-12_W29", last_period_id=None))
            db.commit()
        finally:
            db.close()
        r = self.client.get("/api/members")
        m = next(x for x in r.json()["members"] if x["member_dist_id"] == "N-NEW")
        self.assertEqual(m["last_period_deducted_pv"], 0)

    def test_deducted_zero_when_no_ledger(self):
        """有 last_period_id 但没 paired ledger 的成员, deducted=0"""
        # fixture 里 3 个成员都有 ledger, 这里 M3 只有 pending, 所以 deducted=0
        r = self.client.get("/api/members")
        m3 = next(x for x in r.json()["members"] if x["member_dist_id"] == "N-7000003")
        self.assertEqual(m3["last_period_deducted_pv"], 0)
        self.assertEqual(m3["last_period_id"], "2026-07-12_W29")  # 但有 last_period_id

    def test_deducted_only_matching_period(self):
        """deducted 只算 last_period_id 这一期, 不算其它期"""
        # 给 M2 加一条 W28 的 paired ledger (1000), 不应该算进 M2 的 deducted
        db = SessionLocal()
        try:
            m2 = db.query(Member).filter_by(member_dist_id="N-7000002").first()
            db.add(PVLedger(member_id=m2.id, member_dist_id="N-7000002",
                            period_id="2026-07-05_W28", pv_amount=1000,
                            status="paired", contribution_pv=1000,
                            commission_amount=0.0))
            db.commit()
        finally:
            db.close()
        r = self.client.get("/api/members")
        m2 = next(x for x in r.json()["members"] if x["member_dist_id"] == "N-7000002")
        # M2 last_period_id=W29, 只算 W29 的 paired = 700
        self.assertEqual(m2["last_period_deducted_pv"], 700)


class TestDirectCount(unittest.TestCase):
    """PR #38: /api/members 加 direct_count 字段 (实时聚合 parent_dist_id = self 的成员数)"""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def setUp(self):
        """每个测试: 清空 + 重建 fixture (root + N-ROOT-SUB + 3 个子挂 N-ROOT-SUB)"""
        db = SessionLocal()
        try:
            db.query(Member).delete()
            db.commit()
            # 1 个 root
            db.add(Member(member_dist_id="ROOT", member_name="王常军",
                          parent_dist_id=None, slot_line_id=0,
                          max_lines=5, current_pv_balance=0, total_commission=0.0,
                          created_period_id="2026-07-05_W28", last_period_id=None))
            # 1 个 root 下属
            db.add(Member(member_dist_id="N-ROOT-SUB", member_name="root下",
                          parent_dist_id="ROOT", slot_line_id=1,
                          max_lines=5, current_pv_balance=0, total_commission=0.0,
                          created_period_id="2026-07-12_W29", last_period_id=None))
            # 3 个直推挂 N-ROOT-SUB
            for i in range(1, 4):
                db.add(Member(member_dist_id=f"N-SUB-{i}", member_name=f"直推{i}",
                              parent_dist_id="N-ROOT-SUB", slot_line_id=i,
                              max_lines=5, current_pv_balance=0, total_commission=0.0,
                              created_period_id="2026-07-12_W29", last_period_id=None))
            db.commit()
        finally:
            db.close()

    def _by_dist(self):
        r = self.client.get("/api/members")
        self.assertEqual(r.status_code, 200)
        return {m["member_dist_id"]: m for m in r.json()["members"]}

    def test_root_has_one_direct(self):
        """root 被 N-ROOT-SUB 直推 → direct_count = 1"""
        bd = self._by_dist()
        self.assertEqual(bd["ROOT"]["direct_count"], 1)

    def test_sub_node_has_three_direct(self):
        """N-ROOT-SUB 被 3 个 N-SUB-{1,2,3} 挂 → direct_count = 3"""
        bd = self._by_dist()
        self.assertEqual(bd["N-ROOT-SUB"]["direct_count"], 3)

    def test_leaf_nodes_have_zero_direct(self):
        """N-SUB-1/2/3 都没人挂它们 → direct_count = 0"""
        bd = self._by_dist()
        for i in range(1, 4):
            self.assertEqual(bd[f"N-SUB-{i}"]["direct_count"], 0)

    def test_realtime_calc_no_db_storage(self):
        """不依赖 Member 表 direct_count 列, 实时聚合 parent_dist_id"""
        bd = self._by_dist()
        # 删掉 N-SUB-3, 应该 N-ROOT-SUB.direct_count 立即变 2
        db = SessionLocal()
        try:
            db.query(Member).filter_by(member_dist_id="N-SUB-3").delete()
            db.commit()
        finally:
            db.close()
        bd2 = self._by_dist()
        self.assertEqual(bd2["N-ROOT-SUB"]["direct_count"], 2)


if __name__ == "__main__":
    unittest.main()
