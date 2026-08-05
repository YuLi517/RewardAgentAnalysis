# -*- coding: utf-8 -*-
"""
test_pr56_reset_test_data.py —— PR #56 批量重置测试数据 endpoint 测试
=======================================================================

业务规则 (2026-07-20 PR #56):
    - POST /api/admin/reset_test_data?confirm=true
    - 删所有非 root members
    - 全清 pv_ledger
    - 全清 commission_periods
    - 保留 root member (N5637590.1 王常军)
    - 重建当前 commission_period (PR #55 业务周)
    - confirm=false 时返回 400 (防误操作)
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
from models import Member, PVLedger, CommissionPeriod
from skills.period import get_current_period_id, get_period_range


class TestPr56ResetTestData(unittest.TestCase):
    """PR #56 reset_test_data 端点"""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def setUp(self):
        """每个测试: 清 DB + seed root + 2 测试成员 + 一些 ledger + 1 commission_period"""
        db = SessionLocal()
        try:
            # 清所有
            db.query(CommissionPeriod).delete()
            db.query(PVLedger).filter(PVLedger.member_dist_id.like("N5637590.%")).delete()
            db.query(PVLedger).filter(PVLedger.member_dist_id.like("N-7%")).delete()
            db.query(Member).filter(Member.member_dist_id.like("N5637590.%")).delete()
            db.query(Member).filter(Member.member_dist_id.like("N-7%")).delete()

            # Seed root
            root = Member(
                member_dist_id="N5637590.1", member_name="王常军",
                parent_dist_id=None, slot_line_id=0,
                max_lines=5, current_pv_balance=0, total_commission=0.0,
                created_period_id="2025-12-28_W01", last_period_id=None,
            )
            db.add(root)
            db.flush()
            root_id = int(root.id)

            # Seed 张a (L1)
            za = Member(
                member_dist_id="N5637590.2", member_name="张a",
                parent_dist_id="N5637590.1", slot_line_id=1,
                max_lines=5, current_pv_balance=500, total_commission=75.0,
                created_period_id="2026-07-12_W29", last_period_id="2026-07-12_W29",
            )
            db.add(za)
            db.flush()
            za_id = int(za.id)

            # Seed 张b (L2)
            zb = Member(
                member_dist_id="N5637590.3", member_name="张b",
                parent_dist_id="N5637590.1", slot_line_id=2,
                max_lines=5, current_pv_balance=300, total_commission=45.0,
                created_period_id="2026-07-12_W29", last_period_id="2026-07-12_W29",
            )
            db.add(zb)
            db.flush()
            zb_id = int(zb.id)

            # Seed PV ledger
            _cur = get_current_period_id()
            db.add(PVLedger(member_id=za_id, member_dist_id="N5637590.2",
                            period_id=_cur, pv_amount=500, status="paired",
                            commission_amount=75.0))
            db.add(PVLedger(member_id=zb_id, member_dist_id="N5637590.3",
                            period_id=_cur, pv_amount=300, status="paired",
                            commission_amount=45.0))

            # Seed commission_period
            _start, _end = get_period_range(_cur)
            db.add(CommissionPeriod(
                id=_cur, period_type="weekly",
                start_at=_start, end_at=_end, status="settled",
                total_commission=120.0, total_pv_consumed=800,
                total_pv_carried=0, member_count=2, settled_at=0,
            ))

            db.commit()
        finally:
            db.close()

    def _count(self, db) -> dict:
        """快照当前 DB 状态"""
        return {
            "members": db.query(Member).count(),
            "pv_ledger": db.query(PVLedger).count(),
            "commission_periods": db.query(CommissionPeriod).count(),
        }

    def test_reset_requires_confirm(self):
        """★ PR #56: confirm=false 应返回 400, 不删任何数据"""
        db = SessionLocal()
        try:
            before = self._count(db)
        finally:
            db.close()

        r = self.client.post("/api/admin/reset_test_data")  # 默认 confirm=False
        self.assertEqual(r.status_code, 400, f"应拒绝未确认请求, 实际: {r.text}")
        self.assertIn("confirm=true", r.json()["detail"])

        # 数据应未变
        db = SessionLocal()
        try:
            after = self._count(db)
            self.assertEqual(before, after, f"未确认不应删数据, before={before}, after={after}")
        finally:
            db.close()

    def test_reset_clears_non_root_members(self):
        """★ PR #56: confirm=true 应删所有非 root members, 保留 root"""
        db = SessionLocal()
        try:
            before = self._count(db)
            self.assertEqual(before["members"], 3)  # root + 张a + 张b
            self.assertEqual(before["pv_ledger"], 2)
            self.assertEqual(before["commission_periods"], 1)
        finally:
            db.close()

        r = self.client.post("/api/admin/reset_test_data?confirm=true")
        self.assertEqual(r.status_code, 200, f"重置应成功, 实际: {r.text}")
        data = r.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["root_preserved"])
        # 删除数量: members=2 (张a + 张b), pv_ledger=2, commission_periods=1
        self.assertEqual(data["deleted"]["members"], 2)
        self.assertEqual(data["deleted"]["pv_ledger"], 2)
        self.assertEqual(data["deleted"]["commission_periods"], 1)
        # 当前业务周 ID 应回填
        self.assertRegex(data["current_period_id"], r"^\d{4}-\d{2}-\d{2}_W\d{2}$")

        # 验证 DB 状态
        db = SessionLocal()
        try:
            after = self._count(db)
            self.assertEqual(after["members"], 1, f"只应剩 root, 实际: {after}")
            self.assertEqual(after["pv_ledger"], 0)
            self.assertEqual(after["commission_periods"], 1,
                f"应自动重建当前期, 实际: {after}")  # current 期

            # 验证 root 仍在
            root = db.query(Member).filter(Member.member_dist_id == "N5637590.1").first()
            self.assertIsNotNone(root, "root 必须保留")
            self.assertEqual(root.member_name, "王常军")
            self.assertIsNone(root.parent_dist_id)
            self.assertEqual(root.slot_line_id, 0)
            # reset 后 root 应该清空 carry / commission (跟 setUp 隔离)
            self.assertEqual(root.current_pv_balance, 0, "root carry 应重置为 0")
            self.assertEqual(root.total_commission, 0.0, "root commission 应重置为 0")
        finally:
            db.close()

    def test_reset_rebuilds_root_if_missing(self):
        """★ PR #56: 极端情况 — root 不存在, 重置应自动重建 root"""
        db = SessionLocal()
        try:
            # 删 root (测前先清)
            db.query(Member).filter(Member.member_dist_id == "N5637590.1").delete()
            db.commit()
            # 验证没 root 了
            self.assertEqual(
                db.query(Member).count(), 2,
                "只剩张a + 张b"
            )
        finally:
            db.close()

        r = self.client.post("/api/admin/reset_test_data?confirm=true")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertFalse(data["root_preserved"], "root 之前不存在, 应返回 False")
        self.assertEqual(data["deleted"]["members"], 2, "删了 张a + 张b")

        # 验证: root 重建了
        db = SessionLocal()
        try:
            root = db.query(Member).filter(Member.member_dist_id == "N5637590.1").first()
            self.assertIsNotNone(root, "root 应自动重建")
            self.assertEqual(root.member_name, "王常军")
            self.assertIsNone(root.parent_dist_id)
            self.assertEqual(root.slot_line_id, 0)
        finally:
            db.close()

    def test_reset_idempotent(self):
        """★ PR #56: 连续重置多次应该幂等 (业务数据 0 删, 但 commission_periods 总重建 current 期)"""
        r1 = self.client.post("/api/admin/reset_test_data?confirm=true")
        self.assertEqual(r1.status_code, 200)
        d1 = r1.json()
        # 第 1 次有数据删
        self.assertEqual(d1["deleted"]["members"], 2)
        self.assertEqual(d1["deleted"]["pv_ledger"], 2)
        self.assertEqual(d1["deleted"]["commission_periods"], 1)

        # 第 2 次: members / pv_ledger 应该 0 删
        # commission_periods 删 1 (上一步重建的 current) + 重建 1 (current), 净变化 0
        r2 = self.client.post("/api/admin/reset_test_data?confirm=true")
        self.assertEqual(r2.status_code, 200)
        d2 = r2.json()
        self.assertEqual(d2["deleted"]["members"], 0)
        self.assertEqual(d2["deleted"]["pv_ledger"], 0)
        self.assertEqual(d2["deleted"]["commission_periods"], 1,
            f"第 2 次: 删了 current 期 1 行 + 重建, stats 应 = 1, 实际: {d2}")

        # 验证 DB 状态稳定: 只剩 root + 1 个 current period
        db = SessionLocal()
        try:
            self.assertEqual(db.query(Member).count(), 1, "只剩 root")
            self.assertEqual(db.query(PVLedger).count(), 0)
            self.assertEqual(db.query(CommissionPeriod).count(), 1, "current 期重建")
        finally:
            db.close()

    def test_reset_preserves_root_data_integrity(self):
        """★ PR #56: 重置后, root 的字段都应该是干净状态 (carry=0, total_commission=0)"""
        # 先 setUp 时 root.total_commission=0, 但可能没 commission
        # 跑 settle 让 root 拿点 commission, 然后重置, 验证 commission 被清
        db = SessionLocal()
        try:
            root = db.query(Member).filter(Member.member_dist_id == "N5637590.1").first()
            root.total_commission = 999.0  # 模拟之前 settle 拿过
            db.commit()
        finally:
            db.close()

        self.client.post("/api/admin/reset_test_data?confirm=true")

        db = SessionLocal()
        try:
            root = db.query(Member).filter(Member.member_dist_id == "N5637590.1").first()
            self.assertEqual(root.total_commission, 0.0,
                "root.total_commission 应被重置为 0")
            self.assertEqual(root.current_pv_balance, 0)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
