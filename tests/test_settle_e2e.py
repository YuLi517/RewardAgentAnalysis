# -*- coding: utf-8 -*-
r"""
test_settle_e2e.py —— 结算 API 端到端测试 (PR #9)
=====================================================

PR #9 增强:
    1. POST /api/period/{id}/settle 响应增加 members 列表
    2. GET  /api/period/{id}/summary 响应增加 members 列表
    3. GET  /api/members 列出所有成员 + 余额

测试覆盖:
    1. settle 响应含 members (按 dist_id 排序)
    2. members 含 carry_out + own_commission + ancestor_share + total_commission
    3. summary 响应含 members (不论是否 settle)
    4. /api/members 列出所有成员
    5. 跨期 carry 流转 (W1 settle → W2 settle) — 验证 M1.current_pv_balance 流转
"""
import os
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


class TestSettleAPI(unittest.TestCase):
    """结算 API 端到端测试"""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def setUp(self):
        """每个测试: 清空所有数据, 重新 init"""
        db = SessionLocal()
        try:
            db.query(PVLedger).delete()
            db.query(Member).delete()
            db.query(CommissionPeriod).delete()
            db.commit()
        finally:
            db.close()

    def _add_member(self, dist_id: str, name: str, pv: int, period_id: str):
        """辅助: 加 member + 写 ledger"""
        db = SessionLocal()
        try:
            m = Member(
                member_dist_id=dist_id,
                member_name=name,
                parent_dist_id="N-PARENT",
                slot_line_id=1,
                max_lines=5,
                current_pv_balance=0,
                total_commission=0.0,
                created_period_id=period_id,
            )
            db.add(m)
            db.commit()
            db.refresh(m)
            ledger = PVLedger(
                member_id=m.id,
                member_dist_id=dist_id,
                period_id=period_id,
                pv_amount=pv,
                status="pending",
            )
            db.add(ledger)
            db.commit()
            return m.id
        finally:
            db.close()

    # ============== Test 1: settle 响应含 members ==============

    def test_settle_response_includes_members(self):
        """settle 响应必须含 members 列表, 每位成员含 carry + commission 字段"""
        period = "2026-09-27_W40"
        self._add_member("N-7000001", "M1", 500, period)
        self._add_member("N-7000002", "M2", 300, period)

        r = self.client.post(f"/api/period/{period}/settle")
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertIn("members", data)
        self.assertEqual(len(data["members"]), 2)

        # 按 dist_id 排序
        dist_ids = [m["member_dist_id"] for m in data["members"]]
        self.assertEqual(dist_ids, sorted(dist_ids))

        # 每位成员字段
        for m in data["members"]:
            self.assertIn("member_dist_id", m)
            self.assertIn("member_name", m)
            self.assertIn("carry_out", m)
            self.assertIn("own_commission", m)
            self.assertIn("ancestor_share", m)
            self.assertIn("total_commission", m)
            self.assertIn("last_period_id", m)
            self.assertEqual(m["last_period_id"], period)

    # ============== Test 2: members carry/commission 计算正确 ==============

    def test_settle_members_carry_and_commission(self):
        """M1 (PV=500) carry=200, M2 (PV=300) carry=0, total_commission=45

        算法: MAX=500 (M1), SUM_rest=300 (M2)
              pair = MIN(500, 300) = 300
              commission = 300 × 0.15 = 45
              MAX 剩 = 500 - 300 = 200 (M1 carry)
              SUM_rest 剩 = 300 - 300 = 0 (M2 carry)
        """
        period = "2026-10-04_W41"
        self._add_member("N-7000001", "M1", 500, period)
        self._add_member("N-7000002", "M2", 300, period)

        r = self.client.post(f"/api/period/{period}/settle")
        data = r.json()
        self.assertEqual(data["total_commission"], 45.0)
        self.assertEqual(data["total_pv_consumed"], 300)
        self.assertEqual(data["total_pv_carried"], 200)

        m1 = next(m for m in data["members"] if m["member_dist_id"] == "N-7000001")
        m2 = next(m for m in data["members"] if m["member_dist_id"] == "N-7000002")
        # M1 是 MAX, carry=200; total_commission 含 own + ancestor share
        self.assertEqual(m1["carry_out"], 200)
        # M2 是 L, carry=0
        self.assertEqual(m2["carry_out"], 0)

    # ============== Test 3: summary 响应含 members ==============

    def test_summary_includes_all_members(self):
        """summary 响应含 members (不论是否 settle)"""
        period = "2026-10-11_W42"
        self._add_member("N-7000001", "M1", 500, period)
        self._add_member("N-7000002", "M2", 300, period)
        # 第三个成员没 PV ledger, 但应该在 members 列表里
        db = SessionLocal()
        try:
            m3 = Member(
                member_dist_id="N-7000003", member_name="M3",
                parent_dist_id="N-PARENT", slot_line_id=2, max_lines=5,
                current_pv_balance=100, total_commission=0.0,
                created_period_id=period,
            )
            db.add(m3)
            db.commit()
        finally:
            db.close()

        r = self.client.get(f"/api/period/{period}/summary")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("members", data)
        self.assertEqual(len(data["members"]), 3)
        # M3 current_pv_balance=100 (跨期 carry 留下来的)
        m3 = next(m for m in data["members"] if m["member_dist_id"] == "N-7000003")
        self.assertEqual(m3["current_pv_balance"], 100)
        self.assertIn("total_commission", m3)

    # ============== Test 4: /api/members 列出所有成员 ==============

    def test_members_list_endpoint(self):
        """GET /api/members 列所有成员 + 余额"""
        period = "2026-10-18_W43"
        self._add_member("N-7000001", "M1", 500, period)
        self._add_member("N-7000002", "M2", 300, period)

        r = self.client.get("/api/members")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["count"], 2)
        for m in data["members"]:
            self.assertIn("member_dist_id", m)
            self.assertIn("member_name", m)
            self.assertIn("current_pv_balance", m)
            self.assertIn("total_commission", m)
            self.assertIn("created_period_id", m)
            self.assertIn("last_period_id", m)

    # ============== Test 5: 跨期 carry 流转 (W1 → W2) ==============

    def test_cross_period_carry_through_api(self):
        """W1 settle 后 M1 carry=200 写到 DB, W2 settle 时 M1.current_pv_balance=200 进新一期

        端到端 (走 HTTP API):
          W1: M1 PV=500, M2 PV=300 → M1 carry 200, M2 carry 0
          W2: M1 再加 100 (total carry 200+100=300), M2 不加
          W2 结算: M1 carry 300, M2 carry 0
        """
        w1 = "2026-10-25_W44"
        w2 = "2026-11-01_W45"

        # W1: 加 M1, M2 各 500/300
        self._add_member("N-7000001", "M1", 500, w1)
        self._add_member("N-7000002", "M2", 300, w1)

        r = self.client.post(f"/api/period/{w1}/settle")
        self.assertEqual(r.status_code, 200, r.text)
        w1_result = r.json()
        self.assertEqual(w1_result["total_commission"], 45.0)
        m1_w1 = next(m for m in w1_result["members"] if m["member_dist_id"] == "N-7000001")
        self.assertEqual(m1_w1["carry_out"], 200)

        # W2: M1 再加 100, M2 不加
        db = SessionLocal()
        try:
            m1 = db.query(Member).filter(Member.member_dist_id == "N-7000001").first()
            self.assertEqual(m1.current_pv_balance, 200)  # W1 留下的 carry
            # 加 W2 的 PV ledger
            ledger = PVLedger(
                member_id=m1.id,
                member_dist_id="N-7000001",
                period_id=w2,
                pv_amount=100,
                status="pending",
            )
            db.add(ledger)
            db.commit()
        finally:
            db.close()

        # W2 settle: M1 carry 200 + 100 = 300 (无配对, 全部 carry)
        #          M2 没有本期 PV ledger, 不参与结算
        r = self.client.post(f"/api/period/{w2}/settle")
        self.assertEqual(r.status_code, 200, r.text)
        w2_result = r.json()
        # M1 一个人, 无配对对象, 全部 carry
        self.assertEqual(w2_result["total_commission"], 0.0)
        self.assertEqual(w2_result["total_pv_carried"], 300)
        m1_w2 = next(m for m in w2_result["members"] if m["member_dist_id"] == "N-7000001")
        self.assertEqual(m1_w2["carry_out"], 300)  # ★ 关键: 200 + 100 = 300

        # DB 验证
        r = self.client.get("/api/members")
        members = r.json()["members"]
        m1 = next(m for m in members if m["member_dist_id"] == "N-7000001")
        self.assertEqual(m1["current_pv_balance"], 300)  # ★ 跨期 carry 流转到 DB
        self.assertEqual(m1["last_period_id"], w2)

    # ============== Test 6: /api/period/current + /settle 完整流程 ==============

    def test_settle_current_period_full_flow(self):
        """完整流程: 1. 获取当前期 2. 加 member 3. settle 4. 查 members 确认"""
        # 1. 当前期
        r = self.client.get("/api/period/current")
        self.assertEqual(r.status_code, 200)
        current = r.json()
        period_id = current["period_id"]
        # ★ 2026-07-20 PR #55: 业务周期格式 "YYYY-MM-DD_Www"
        self.assertRegex(period_id, r"^\d{4}-\d{2}-\d{2}_W\d{2}$")

        # 2. 加 member (用当前期)
        self._add_member("N-7000001", "M1", 500, period_id)
        self._add_member("N-7000002", "M2", 300, period_id)

        # 3. settle
        r = self.client.post(f"/api/period/{period_id}/settle")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["period_id"], period_id)
        self.assertEqual(data["total_commission"], 45.0)

        # 4. 查 members 确认
        r = self.client.get("/api/members")
        members_data = r.json()["members"]
        m1 = next(m for m in members_data if m["member_dist_id"] == "N-7000001")
        self.assertEqual(m1["current_pv_balance"], 200)


if __name__ == "__main__":
    unittest.main()
