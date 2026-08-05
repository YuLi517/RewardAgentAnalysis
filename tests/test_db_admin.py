# -*- coding: utf-8 -*-
r"""
test_db_admin.py —— /api/admin/* 端点测试 (PR #31)
====================================================

PR #31 (2026-07-16) DB Admin API:
    - GET /api/admin/tables: 列业务表 + columns + row count
    - GET /api/admin/tables/{name}: 查表数据
    - PUT /api/admin/tables/{name}/rows/{pk_value}: 更新一行

测试覆盖:
    1. list tables (只返白名单, 跳过 sessions/messages/alembic_version)
    2. list tables 含 row_count 跟 primary_key
    3. 查表数据 (limit 生效, 排序按主键)
    4. 查表数据 — 不存在的表 → 404
    5. 查表数据 — 不在白名单的表 → 403
    6. 更新一行 — 改一个字段, 验证 DB 改了
    7. 更新一行 — 改多个字段
    8. 更新一行 — 不允许改主键
    9. 更新一行 — 主键找不到 → 404
    10. 更新一行 — 类型强转 (int)
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


class TestDbAdminApi(unittest.TestCase):
    """PR #31: /api/admin/*"""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def setUp(self):
        """每个测试: 清空, 重建 3 个表 fixture"""
        db = SessionLocal()
        try:
            db.query(PVLedger).delete()
            db.query(Member).delete()
            db.query(CommissionPeriod).delete()
            db.commit()
        finally:
            db.close()
        self._build()

    def _build(self):
        db = SessionLocal()
        try:
            db.add(Member(member_dist_id="N-7000001", member_name="甲",
                          parent_dist_id="N5637590.1", slot_line_id=1,
                          max_lines=5, current_pv_balance=100,
                          total_commission=10.0,
                          created_period_id="2026-07-12_W29", last_period_id="2026-07-12_W29"))
            db.add(Member(member_dist_id="N-7000002", member_name="乙",
                          parent_dist_id="N5637590.1", slot_line_id=2,
                          max_lines=5, current_pv_balance=200,
                          total_commission=0.0,
                          created_period_id="2026-07-12_W29", last_period_id="2026-07-12_W29"))
            db.add(CommissionPeriod(id="2026-07-12_W29", period_type="weekly",
                                    start_at=1783872000.0, end_at=1784476799.999,
                                    status="settled", total_commission=0.0,
                                    total_pv_consumed=0, total_pv_carried=0,
                                    member_count=2, settled_at=1784171112.0,
                                    settled_by="system"))
            db.commit()
        finally:
            db.close()

    def _peek_member(self, dist_id: str):
        db = SessionLocal()
        try:
            return db.query(Member).filter_by(member_dist_id=dist_id).first()
        finally:
            db.close()

    # ---------- list tables ----------

    def test_list_tables_only_whitelist(self):
        r = self.client.get("/api/admin/tables")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        names = [t["name"] for t in data["tables"]]
        # 业务表 3 个都在
        self.assertIn("members", names)
        self.assertIn("pv_ledger", names)
        self.assertIn("commission_periods", names)
        # 非白名单表不在
        self.assertNotIn("sessions", names)
        self.assertNotIn("messages", names)
        self.assertNotIn("alembic_version", names)

    def test_list_tables_includes_metadata(self):
        r = self.client.get("/api/admin/tables")
        data = r.json()
        members = next(t for t in data["tables"] if t["name"] == "members")
        self.assertGreater(members["row_count"], 0)
        self.assertIn("id", members["primary_key"])
        col_names = [c["name"] for c in members["columns"]]
        for expected in ["id", "member_dist_id", "member_name", "parent_dist_id",
                         "slot_line_id", "current_pv_balance", "total_commission"]:
            self.assertIn(expected, col_names)

    # ---------- get table data ----------

    def test_get_table_data(self):
        r = self.client.get("/api/admin/tables/members")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["name"], "members")
        self.assertEqual(data["primary_key"], ["id"])
        self.assertEqual(data["row_count"], 2)
        self.assertEqual(len(data["rows"]), 2)
        # 字段都在
        for row in data["rows"]:
            for key in ("id", "member_dist_id", "member_name", "current_pv_balance"):
                self.assertIn(key, row)

    def test_get_table_data_limit(self):
        r = self.client.get("/api/admin/tables/members?limit=1")
        data = r.json()
        self.assertEqual(data["limit"], 1)
        self.assertEqual(len(data["rows"]), 1)

    def test_get_table_data_not_found(self):
        r = self.client.get("/api/admin/tables/does_not_exist")
        self.assertEqual(r.status_code, 404)

    def test_get_table_data_not_in_whitelist(self):
        """sessions/messages 不在白名单 → 403"""
        r = self.client.get("/api/admin/tables/sessions")
        self.assertEqual(r.status_code, 403)
        r2 = self.client.get("/api/admin/tables/messages")
        self.assertEqual(r2.status_code, 403)

    # ---------- update row ----------

    def test_update_row_single_field(self):
        r = self.client.put(
            "/api/admin/tables/members/rows/1",
            json={"member_name": "甲改名"},
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["updated"], 1)
        self.assertEqual(data["fields_changed"], ["member_name"])
        # 验证 DB 真的改了
        m = self._peek_member("N-7000001")
        self.assertEqual(m.member_name, "甲改名")
        # 其他字段没变
        self.assertEqual(m.current_pv_balance, 100)

    def test_update_row_multiple_fields(self):
        r = self.client.put(
            "/api/admin/tables/members/rows/2",
            json={"member_name": "乙改名", "current_pv_balance": 999, "slot_line_id": 3},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.json()["fields_changed"]), {"member_name", "current_pv_balance", "slot_line_id"})
        m = self._peek_member("N-7000002")
        self.assertEqual(m.member_name, "乙改名")
        self.assertEqual(m.current_pv_balance, 999)
        self.assertEqual(m.slot_line_id, 3)

    def test_update_row_cannot_change_pk(self):
        """传主键 id 会被忽略, 不会改"""
        r = self.client.put(
            "/api/admin/tables/members/rows/1",
            json={"id": 999, "member_name": "改主键尝试"},
        )
        self.assertEqual(r.status_code, 200)
        # id 没改, member_name 改了
        db = SessionLocal()
        try:
            m = db.query(Member).filter_by(id=1).first()
            self.assertIsNotNone(m)
            self.assertEqual(m.member_name, "改主键尝试")
            # id 仍 = 1
            self.assertEqual(m.id, 1)
        finally:
            db.close()

    def test_update_row_pk_not_found(self):
        r = self.client.put(
            "/api/admin/tables/members/rows/9999",
            json={"member_name": "找不到"},
        )
        self.assertEqual(r.status_code, 404)

    def test_update_row_type_coercion(self):
        """current_pv_balance 是 Integer, 传 string '500' 也能强转"""
        r = self.client.put(
            "/api/admin/tables/members/rows/1",
            json={"current_pv_balance": "500"},
        )
        self.assertEqual(r.status_code, 200)
        m = self._peek_member("N-7000001")
        self.assertEqual(m.current_pv_balance, 500)
        self.assertIsInstance(m.current_pv_balance, int)

    def test_update_row_empty_body(self):
        """body 空 → 400"""
        r = self.client.put("/api/admin/tables/members/rows/1", json={})
        self.assertEqual(r.status_code, 400)

    def test_update_row_not_in_whitelist(self):
        """sessions 不允许 PUT"""
        r = self.client.put("/api/admin/tables/sessions/rows/x", json={"title": "hack"})
        self.assertEqual(r.status_code, 403)

    # ---------- update row with datetime string (PR #49) ----------

    def test_update_row_float_accepts_datetime_string(self):
        """★ PR #49: Float 类型接受 datetime 字符串 ("YYYY-MM-DD HH:MM:SS")
        跟 PR #48 配套 — DB admin UI 把 *_at 列格式化成 datetime 显示, 用户编辑后
        保存发回 string, 后端 _db_admin_coerce 解析回 Unix timestamp float
        """
        from datetime import datetime
        # 1. 改 start_at 为 2026-01-15 14:30:00
        r = self.client.put(
            "/api/admin/tables/commission_periods/rows/2026-07-12_W29",
            json={"start_at": "2026-01-15 14:30:00"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        # 2. 验证 DB 里是 float timestamp (跟 2026-01-15 14:30:00 UTC 对应)
        expected_ts = datetime(2026, 1, 15, 14, 30, 0).timestamp()
        db = SessionLocal()
        try:
            p = db.query(CommissionPeriod).filter_by(id="2026-07-12_W29").first()
            self.assertIsNotNone(p)
            # SQLite Float 可能跟 expected 有 epsilon 误差, 但应非常接近
            self.assertAlmostEqual(p.start_at, expected_ts, delta=0.01)
        finally:
            db.close()

    def test_update_row_float_accepts_date_only_string(self):
        """★ PR #49: 只传日期 "YYYY-MM-DD" 也接受 (补 00:00:00)"""
        r = self.client.put(
            "/api/admin/tables/commission_periods/rows/2026-07-12_W29",
            json={"end_at": "2026-12-31"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        from datetime import datetime
        expected_ts = datetime(2026, 12, 31, 0, 0, 0).timestamp()
        db = SessionLocal()
        try:
            p = db.query(CommissionPeriod).filter_by(id="2026-07-12_W29").first()
            self.assertAlmostEqual(p.end_at, expected_ts, delta=0.01)
        finally:
            db.close()

    def test_update_row_float_accepts_iso_t_separator(self):
        """★ PR #49: "T" 分隔符也接受 (ISO 8601)"""
        r = self.client.put(
            "/api/admin/tables/commission_periods/rows/2026-07-12_W29",
            json={"settled_at": "2026-07-16T12:00:00"},
        )
        self.assertEqual(r.status_code, 200, r.text)

    def test_update_row_float_still_accepts_raw_float_string(self):
        """★ PR #49 兼容旧用法: 直接传 Unix timestamp string 也能强转"""
        r = self.client.put(
            "/api/admin/tables/commission_periods/rows/2026-07-12_W29",
            json={"start_at": "1736951400"},  # 2025-01-15 14:30:00 UTC
        )
        self.assertEqual(r.status_code, 200, r.text)
        db = SessionLocal()
        try:
            p = db.query(CommissionPeriod).filter_by(id="2026-07-12_W29").first()
            self.assertAlmostEqual(p.start_at, 1736951400, delta=0.01)
        finally:
            db.close()

    # ---------- delete row (PR #47) ----------

    def test_delete_row_success(self):
        """删除一行: 返 200, DB 真删了"""
        r = self.client.delete("/api/admin/tables/members/rows/1")
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["deleted"], 1)
        self.assertEqual(d["table"], "members")
        self.assertEqual(d["pk"], "id")
        self.assertEqual(d["pk_value"], "1")
        # DB 验证
        self.assertIsNone(self._peek_member("N-7000001"), "甲 应该被删除")
        # 乙 还在
        self.assertIsNotNone(self._peek_member("N-7000002"), "乙 不应受影响")

    def test_delete_row_cascades_pv_ledger(self):
        """★ PR #47: 删 member 级联清相关 PVLedger (SQLite FK ON DELETE CASCADE)

        models.py: PVLedger.member_id has ForeignKey("members.id", ondelete="CASCADE")
        """
        from models import PVLedger
        db = SessionLocal()
        try:
            # 给 甲 加一条 PVLedger
            from models import Member as _M
            m1 = db.query(_M).filter_by(member_dist_id="N-7000001").first()
            db.add(PVLedger(
                member_id=m1.id,
                member_dist_id=m1.member_dist_id,
                period_id="2026-07-12_W29",
                pv_amount=500,
                status="pending",
            ))
            db.commit()
            # 删 甲
            r = self.client.delete(f"/api/admin/tables/members/rows/{m1.id}")
            self.assertEqual(r.status_code, 200)
            # PVLedger 应该被级联删
            ledger_count = db.query(PVLedger).filter_by(member_id=m1.id).count()
            self.assertEqual(ledger_count, 0, "PVLedger 应该级联删除")
        finally:
            db.close()

    def test_delete_row_pk_not_found(self):
        r = self.client.delete("/api/admin/tables/members/rows/9999")
        self.assertEqual(r.status_code, 404)
        self.assertIn("找不到", r.json()["detail"])

    def test_delete_row_not_in_whitelist(self):
        """sessions 不允许 DELETE"""
        r = self.client.delete("/api/admin/tables/sessions/rows/x")
        self.assertEqual(r.status_code, 403)

    def test_delete_row_table_not_found(self):
        r = self.client.delete("/api/admin/tables/does_not_exist/rows/1")
        self.assertEqual(r.status_code, 404)

    def test_delete_row_commission_periods(self):
        """★ 删 commission_periods 也能工作 (业务表白名单第 3 个)"""
        # fixture 里有 1 条 period
        r = self.client.get("/api/admin/tables/commission_periods")
        period_id = r.json()["rows"][0]["id"]
        r = self.client.delete(f"/api/admin/tables/commission_periods/rows/{period_id}")
        self.assertEqual(r.status_code, 200)
        # 删后查不到
        r2 = self.client.get("/api/admin/tables/commission_periods")
        self.assertEqual(r2.json()["row_count"], 0)


if __name__ == "__main__":
    unittest.main()
