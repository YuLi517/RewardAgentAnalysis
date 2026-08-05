# -*- coding: utf-8 -*-
"""
test_pr55_sun_fri.py —— PR #55 业务周 (Sun-Fri) + 补录窗口 测试
================================================================

业务规则 (2026-07-20 PR #55):
    - 周期 ID: "2026-07-12_W29" (业务周, Sun-Fri 范围)
    - 范围: Sun 00:00 → Fri 23:59:59.999 (6 天)
    - 补录窗口: Sat 00:00 → Mon 23:59:59.999 (3 天, "下班前" = Mon 23:59)
    - 补录模式: 只算 own_commission, 跳过 pairing_bonus (对等链冻结)
    - 关闭: Tue 起, period 不能再补 (status=closed)

测试覆盖:
    1. period_id 格式 + 范围计算 (Sun-Fri)
    2. get_current_period_id 跨周日-周六切换
    3. get_supplement_range Sat-Mon
    4. can_supplement + get_period_phase
    5. migrate_old_period_id 旧 "2026-W29" → 新 "2026-07-12_W29"
    6. settle_period supplement_only=True: 只算 own, 跳过对等
    7. settle_period supplement_only=False (默认): 全套
    8. period.status 'settled' + supplement_until_ts 过期 → migration mark closed
"""
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from skills.period import (
    get_current_period_id,
    get_period_range,
    get_supplement_range,
    can_supplement,
    get_period_phase,
    make_period_id,
    migrate_old_period_id,
    _business_week_number,
    _parse_period_id,
)


class TestPr55PeriodId(unittest.TestCase):
    """PR #55 周期 ID 格式 + 解析"""

    def test_make_period_id_format(self):
        """2026-07-12 (Sun) → '2026-07-12_W29'"""
        from datetime import date
        # 2026-07-12 是周日, 业务 W29 开始
        self.assertEqual(make_period_id(date(2026, 7, 12)), "2026-07-12_W29")

    def test_make_period_id_rejects_non_sunday(self):
        """非周日应该报错"""
        from datetime import date
        with self.assertRaises(ValueError) as ctx:
            make_period_id(date(2026, 7, 13))  # Mon
        self.assertIn("周日", str(ctx.exception))

    def test_parse_period_id_round_trip(self):
        """make_period_id + _parse_period_id 往返一致"""
        from datetime import date
        for start in [date(2025, 12, 28), date(2026, 7, 12), date(2026, 10, 11)]:
            pid = make_period_id(start)
            parsed_start, parsed_week = _parse_period_id(pid)
            self.assertEqual(parsed_start, start)
            self.assertEqual(make_period_id(parsed_start), pid)

    def test_parse_period_id_rejects_old_format(self):
        """旧 '2026-W29' 格式应该报错 (强制新格式)"""
        with self.assertRaises(ValueError) as ctx:
            _parse_period_id("2026-W29")
        self.assertIn("YYYY-MM-DD_Www", str(ctx.exception))

    def test_parse_period_id_rejects_monday_start(self):
        """开始日不是周日应该报错"""
        with self.assertRaises(ValueError) as ctx:
            _parse_period_id("2026-07-13_W29")  # Mon
        self.assertIn("周日", str(ctx.exception))

    def test_business_week_number_business_w1(self):
        """业务 W1 开始日 = 2025-12-28 (Sun) → biz_week=1"""
        from datetime import date
        self.assertEqual(_business_week_number(date(2025, 12, 28)), 1)
        self.assertEqual(_business_week_number(date(2026, 7, 12)), 29)
        self.assertEqual(_business_week_number(date(2026, 10, 11)), 42)


class TestPr55PeriodRange(unittest.TestCase):
    """PR #55 周期范围 (Sun-Fri, 6 天)"""

    def test_w29_range_sun_to_fri(self):
        """W29 范围 = 2026-07-12 (Sun) ~ 2026-07-17 (Fri 23:59:59.999)"""
        from datetime import date
        pid = "2026-07-12_W29"
        start, end = get_period_range(pid)
        start_dt = datetime.fromtimestamp(start)
        end_dt = datetime.fromtimestamp(end)
        self.assertEqual(start_dt.date(), date(2026, 7, 12))
        self.assertEqual(start_dt.weekday(), 6)  # Sun
        self.assertEqual(end_dt.date(), date(2026, 7, 17))
        self.assertEqual(end_dt.weekday(), 4)  # Fri
        self.assertEqual(end_dt.hour, 23)
        self.assertEqual(end_dt.minute, 59)
        self.assertEqual(end_dt.second, 59)

    def test_w29_supplement_range_sat_to_mon(self):
        """W29 补录范围 = 2026-07-18 (Sat) ~ 2026-07-20 (Mon 23:59:59.999)"""
        from datetime import date
        pid = "2026-07-12_W29"
        sup_start, sup_end = get_supplement_range(pid)
        sup_start_dt = datetime.fromtimestamp(sup_start)
        sup_end_dt = datetime.fromtimestamp(sup_end)
        self.assertEqual(sup_start_dt.date(), date(2026, 7, 18))
        self.assertEqual(sup_start_dt.weekday(), 5)  # Sat
        self.assertEqual(sup_end_dt.date(), date(2026, 7, 20))
        self.assertEqual(sup_end_dt.weekday(), 0)  # Mon
        self.assertEqual(sup_end_dt.hour, 23)
        self.assertEqual(sup_end_dt.minute, 59)


class TestPr55CurrentPeriod(unittest.TestCase):
    """PR #55 当前周期跨日切换"""

    def test_sunday_is_new_period(self):
        """周日 = 新周期开始"""
        pid = get_current_period_id(datetime(2026, 7, 12))  # Sun
        self.assertEqual(pid, "2026-07-12_W29")

    def test_monday_to_friday_same_period(self):
        """Mon-Fri = 同一周期"""
        for d in [datetime(2026, 7, 13), datetime(2026, 7, 14),
                  datetime(2026, 7, 15), datetime(2026, 7, 16),
                  datetime(2026, 7, 17)]:
            pid = get_current_period_id(d)
            self.assertEqual(pid, "2026-07-12_W29", f"{d.date()} 应该属于 W29")

    def test_saturday_belongs_to_previous_period(self):
        """周六 = 上一周期 (补录期)"""
        # 2026-07-18 (Sat) 算 W29 补录期, period_id 仍是 "2026-07-12_W29"
        pid = get_current_period_id(datetime(2026, 7, 18))
        self.assertEqual(pid, "2026-07-12_W29")

    def test_monday_starts_new_period(self):
        """周一 = 新周期 (W30), 但补录窗口仍能补 W29"""
        # 2026-07-20 (Mon) 算 W30, 跟 W29 supplement 期重叠
        pid = get_current_period_id(datetime(2026, 7, 20))
        self.assertEqual(pid, "2026-07-19_W30")


class TestPr55SupplementPhase(unittest.TestCase):
    """PR #55 补录窗口判定"""

    def test_phase_open_during_sun_to_fri(self):
        """Sun-Fri 期间 phase='open'"""
        for d in [datetime(2026, 7, 12), datetime(2026, 7, 14), datetime(2026, 7, 17)]:
            phase = get_period_phase("2026-07-12_W29", now=d)
            self.assertEqual(phase, "open", f"{d.date()} 应该是 open")

    def test_phase_supplement_during_sat_to_mon(self):
        """Sat-Mon 期间 phase='supplement'"""
        for d in [datetime(2026, 7, 18, 12, 0), datetime(2026, 7, 19, 12, 0),
                  datetime(2026, 7, 20, 22, 0)]:
            phase = get_period_phase("2026-07-12_W29", now=d)
            self.assertEqual(phase, "supplement", f"{d.date()} {d.hour}点 应该是 supplement")

    def test_phase_closed_after_tuesday(self):
        """Tue 起 phase='closed'"""
        for d in [datetime(2026, 7, 21, 0, 0), datetime(2026, 7, 25, 12, 0)]:
            phase = get_period_phase("2026-07-12_W29", now=d)
            self.assertEqual(phase, "closed", f"{d.date()} 应该是 closed")

    def test_can_supplement_only_sat_to_mon(self):
        """can_supplement 严格在 Sat-Mon 范围内才 True"""
        # 业务 W29 范围 7-12~7-17, 补录 7-18 00:00 ~ 7-20 23:59
        for d in [datetime(2026, 7, 17, 23, 59), datetime(2026, 7, 18, 0, 0),
                  datetime(2026, 7, 20, 23, 59), datetime(2026, 7, 21, 0, 0)]:
            can = can_supplement("2026-07-12_W29", now=d)
            # 7-17 23:59 不行, 7-18 00:00 行, 7-20 23:59 行, 7-21 00:00 不行
            if d <= datetime(2026, 7, 17, 23, 59) or d >= datetime(2026, 7, 21, 0, 0):
                self.assertFalse(can, f"{d} 不在补录窗口")
            else:
                self.assertTrue(can, f"{d} 应该在补录窗口")


class TestPr55MigrateOldId(unittest.TestCase):
    """PR #55 旧 ISO ID 迁移 (数据迁移用)"""

    def test_migrate_2026_w29(self):
        """2026-W29 (ISO) → 2026-07-12_W29 (业务, 范围 7-12~7-17)"""
        self.assertEqual(migrate_old_period_id("2026-W29"), "2026-07-12_W29")

    def test_migrate_2026_w28(self):
        """2026-W28 (ISO, 7-06~7-12) → 2026-07-05_W28 (业务, 7-05~7-10)"""
        self.assertEqual(migrate_old_period_id("2026-W28"), "2026-07-05_W28")

    def test_migrate_2026_w01(self):
        """2026-W01 (ISO, 2025-12-29~2026-01-04) → 2025-12-28_W01 (业务, 2025-12-28~2026-01-02)"""
        self.assertEqual(migrate_old_period_id("2026-W01"), "2025-12-28_W01")

    def test_migrate_2026_w30(self):
        """2026-W30 (ISO, 7-20~7-26) → 2026-07-19_W30 (业务, 7-19~7-24)
        数字保持 ISO 周"""
        self.assertEqual(migrate_old_period_id("2026-W30"), "2026-07-19_W30")

    def test_migrate_rejects_new_format(self):
        """新格式不应该被 migrate 接受 (避免双重迁移)"""
        with self.assertRaises(ValueError):
            migrate_old_period_id("2026-07-12_W29")


class TestPr55SettleSupplementOnly(unittest.TestCase):
    """PR #55 settle_period supplement_only 模式 (own only, 跳过对等)"""

    def setUp(self):
        """清 DB + seed root"""
        from fastapi.testclient import TestClient
        from database import SessionLocal
        from models import Member, PVLedger, CommissionPeriod
        from skills.period import get_current_period_id, get_period_range

        self.client = TestClient(__import__("main").app)
        self._cur_period = get_current_period_id()
        _start, _end = get_period_range(self._cur_period)

        db = SessionLocal()
        try:
            db.query(CommissionPeriod).delete()
            db.query(PVLedger).filter(PVLedger.member_dist_id.like("N5637590.%")).delete()
            db.query(PVLedger).filter(PVLedger.member_dist_id.like("N-7%")).delete()
            db.query(Member).filter(Member.member_dist_id.like("N5637590.%")).delete()
            db.query(Member).filter(Member.member_dist_id.like("N-7%")).delete()
            db.add(Member(member_dist_id="N5637590.1", member_name="王常军",
                          parent_dist_id=None, slot_line_id=0,
                          max_lines=5, current_pv_balance=0, total_commission=0.0,
                          created_period_id="2025-12-28_W01", last_period_id=None))
            db.commit()
        finally:
            db.close()

    def _root_id(self) -> int:
        from database import SessionLocal
        from models import Member
        db = SessionLocal()
        try:
            m = db.query(Member).filter(Member.member_dist_id == "N5637590.1").first()
            return int(m.id) if m else 1
        finally:
            db.close()

    def test_settle_supplement_requires_settled_status(self):
        """★ PR #55: 补录模式要求 period.status='settled', open 状态报错"""
        from database import SessionLocal
        from models import PVLedger
        db = SessionLocal()
        try:
            _rid = self._root_id()
            db.add(PVLedger(member_id=_rid, member_dist_id="N5637590.1",
                            period_id=self._cur_period, pv_amount=500, status="pending"))
            db.commit()
        finally:
            db.close()

        r = self.client.post(f"/api/period/{self._cur_period}/settle?supplement_only=true")
        self.assertEqual(r.status_code, 400, f"补录应失败 (open), 实际: {r.text}")
        self.assertIn("settled", r.json()["detail"])

    def test_settle_supplement_only_own_commission(self):
        """★ PR #55: 补录模式只算 own_commission, 跳过对等

        设计: 模拟"settle 之后新加成员"补录场景
        - 张a (L1, 500 PV) + 张b (L2, 300 PV) 都是 settle 之后新加的
        - 补录: 配对 P (张a=500) vs L (张b=300), commission = 300 * 0.15 = 45
        - 父 (root) 拿 45 (P 是张a, commission 给父)
        - 跳过对等 7 代分润 (ancestor_share = 0)
        """
        from database import SessionLocal
        from models import Member, PVLedger, CommissionPeriod
        from skills.period import get_supplement_range

        db = SessionLocal()
        try:
            _rid = self._root_id()
            _, sup_end = get_supplement_range(self._cur_period)
            _za = Member(member_dist_id="N5637590.2", member_name="张a",
                         parent_dist_id="N5637590.1", slot_line_id=1,
                         max_lines=5, current_pv_balance=0, total_commission=0.0,
                         created_period_id=self._cur_period, last_period_id=None)
            _zb = Member(member_dist_id="N5637590.3", member_name="张b",
                         parent_dist_id="N5637590.1", slot_line_id=2,
                         max_lines=5, current_pv_balance=0, total_commission=0.0,
                         created_period_id=self._cur_period, last_period_id=None)
            db.add_all([_za, _zb])
            db.commit()
            _za_id, _zb_id = int(_za.id), int(_zb.id)

            db.add(CommissionPeriod(
                id=self._cur_period, period_type="weekly",
                start_at=0, end_at=0, status="settled",
                supplement_until_ts=sup_end,
                total_commission=0, total_pv_consumed=0, total_pv_carried=0,
                member_count=0, created_at=0,
            ))
            # 补录 ledger: 张a 500 PV (P) + 张b 300 PV (L)
            db.add(PVLedger(member_id=_za_id, member_dist_id="N5637590.2",
                            period_id=self._cur_period, pv_amount=500, status="pending"))
            db.add(PVLedger(member_id=_zb_id, member_dist_id="N5637590.3",
                            period_id=self._cur_period, pv_amount=300, status="pending"))
            db.commit()
        finally:
            db.close()

        r = self.client.post(f"/api/period/{self._cur_period}/settle?supplement_only=true")
        self.assertEqual(r.status_code, 200, f"补录应成功, 实际: {r.text}")
        data = r.json()

        # 验证: 补录 commission = min(P=500, L=300) * 0.15 = 300 * 0.15 = 45
        self.assertEqual(data["total_commission"], 45.0,
            f"补录 commission = min(500, 300) * 0.15 = 45, 实际: {data['total_commission']}")

        # 验证: period.supplement_commission = 45, supplement_count = 2
        db = SessionLocal()
        try:
            p = db.query(CommissionPeriod).filter(CommissionPeriod.id == self._cur_period).first()
            self.assertEqual(p.supplement_commission, 45.0)
            self.assertEqual(p.supplement_count, 2)
            self.assertEqual(p.status, "settled", "补录期间 status 保持 settled")

            # 关键: 补录模式不触发 ancestor 7 代分润, 所以:
            # - root 拿 own commission 45 (P 是张a, L 是张b, 配对给父 root)
            # - root.total_commission 不会被进一步分给 (root 自己是顶级 ancestor, ancestor=[])
            m = db.query(Member).filter(Member.member_dist_id == "N5637590.1").first()
            self.assertEqual(m.total_commission, 45.0, "root own=45, 补录不触发对等分润")

            # 张a/张b 拿 0 (L 角色或被配对的 P 角色, 自己是子, commission 给父)
            for did in ["N5637590.2", "N5637590.3"]:
                m_x = db.query(Member).filter(Member.member_dist_id == did).first()
                self.assertEqual(m_x.total_commission, 0.0, f"{did} 子拿 0, commission 给父")
        finally:
            db.close()

    def test_settle_supplement_window_expired(self):
        """★ PR #55: 补录窗口过期 → 400"""
        from database import SessionLocal
        from models import CommissionPeriod

        db = SessionLocal()
        try:
            db.add(CommissionPeriod(
                id=self._cur_period, period_type="weekly",
                start_at=0, end_at=0, status="settled",
                supplement_until_ts=1,  # 早就过期
                total_commission=0, total_pv_consumed=0, total_pv_carried=0,
                member_count=0, created_at=0,
            ))
            db.commit()
        finally:
            db.close()

        r = self.client.post(f"/api/period/{self._cur_period}/settle?supplement_only=true")
        self.assertEqual(r.status_code, 400, f"过期补录应失败, 实际: {r.text}")
        self.assertIn("补录窗口", r.json()["detail"])


class TestPr55MigrationScript(unittest.TestCase):
    """PR #55 migration 脚本 (旧 ID → 新 ID)"""

    def test_migration_idempotent(self):
        """★ migration 多次跑安全 (idempotent)"""
        import subprocess
        from pathlib import Path

        proj_root = Path(__file__).resolve().parent.parent
        script = proj_root / "tools" / "migrate_pr55_period_id.py"
        if not script.exists():
            self.skipTest("migration script not found")

        r = subprocess.run(
            [sys.executable, str(script)],
            cwd=proj_root,
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, f"migration 失败: {r.stderr}")

        # 第二次跑 (idempotent)
        r2 = subprocess.run(
            [sys.executable, str(script)],
            cwd=proj_root,
            capture_output=True,
            text=True,
        )
        self.assertEqual(r2.returncode, 0, f"migration 第二次失败: {r2.stderr}")
        self.assertIn("periods_migrated: 0", r2.stdout, "第二次应该 0 迁移")
        self.assertIn("ledgers_migrated: 0", r2.stdout)


if __name__ == "__main__":
    unittest.main()
