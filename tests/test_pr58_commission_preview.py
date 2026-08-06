# -*- coding: utf-8 -*-
"""
test_pr58_commission_preview.py —— PR #58 父节点 commission preview 测试
"""
import re
import sys
import unittest
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from database import init_db  # noqa: E402
from main import _build_tree_from_db, _build_tree_render_html  # noqa: E402
from models import Base, Member, PVLedger, CommissionPeriod  # noqa: E402

INDEX_HTML = (PROJ / "static" / "index.html").read_text(encoding="utf-8")
MAIN_PY = (PROJ / "main.py").read_text(encoding="utf-8")


def _make_test_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return engine, Session


class TestPr58CommissionField(unittest.TestCase):
    """T1+T2: commissionPreview 字段 + z1=500 + z2=300 → 王常军 $45"""

    def setUp(self):
        self.engine, Session = _make_test_db()
        self.db = Session()
        self.db.query(CommissionPeriod).delete()
        self.db.query(PVLedger).delete()
        self.db.query(Member).delete()
        self.db.add(Member(
            member_dist_id="N5637590.1", member_name="王常军",
            parent_dist_id=None, slot_line_id=0,
            max_lines=2, current_pv_balance=0, total_commission=0.0,
        ))
        self.db.add(Member(
            member_dist_id="N5637590.2", member_name="z1",
            parent_dist_id="N5637590.1", slot_line_id=1,
            max_lines=5, current_pv_balance=0, total_commission=0.0,
        ))
        self.db.add(Member(
            member_dist_id="N5637590.3", member_name="z2",
            parent_dist_id="N5637590.1", slot_line_id=2,
            max_lines=5, current_pv_balance=0, total_commission=0.0,
        ))
        from skills.period import get_current_period_id
        self._cur = get_current_period_id()
        z1 = self.db.query(Member).filter_by(member_dist_id="N5637590.2").first()
        z2 = self.db.query(Member).filter_by(member_dist_id="N5637590.3").first()
        self.db.add(PVLedger(member_id=z1.id, member_dist_id="N5637590.2",
                              period_id=self._cur, pv_amount=500, status="pending"))
        self.db.add(PVLedger(member_id=z2.id, member_dist_id="N5637590.3",
                              period_id=self._cur, pv_amount=300, status="pending"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_root_commission_preview_45(self):
        """z1=500 + z2=300 → 王常军 ownBasic = 45, teamBonus (PR #71 4 档精确匹配):
        1区: z1.1=500 → 500×20% = 100, 2区: z2.1=300 → 0 (300 不在 4 档)
        total teamBonus = 100 + 0 = 100
        total = 45 + 0 + 100 = 145
        """
        tree = _build_tree_from_db(self.db)
        self.assertEqual(tree["distId"], "N5637590.1")
        self.assertAlmostEqual(tree["ownBasic"], 45.0, places=2)
        # ★ PR #71: commissionPreview = ownBasic + pairBonus + teamBonus (4 档精确匹配)
        #   1区: z1.1=500 → 100, 2区: z2.1=300 → 0
        #   total = 45 + 0 + 100 = 145
        self.assertAlmostEqual(tree["teamBonus"], 100.0, places=2)
        self.assertAlmostEqual(tree["commissionPreview"], 145.0, places=2)

    def test_z1_z2_ownbasic_zero(self):
        """z1/z2 没 L2 子, ownBasic = 0"""
        tree = _build_tree_from_db(self.db)
        for child in tree["children"]:
            if not child.get("available"):
                self.assertAlmostEqual(child["ownBasic"], 0.0, places=2)
                self.assertAlmostEqual(child["commissionPreview"], 0.0, places=2)

    def test_zero_pv_zero_commission(self):
        """T4: 0 PV → 0 commission"""
        self.db.query(PVLedger).delete()
        self.db.commit()
        tree = _build_tree_from_db(self.db)
        self.assertAlmostEqual(tree["ownBasic"], 0.0, places=2)
        self.assertAlmostEqual(tree["commissionPreview"], 0.0, places=2)

    def test_render_html_shows_preview_badge(self):
        """HTML 渲染含 '本期可拿 $145.00' (PR #71 4 档精确匹配 teamBonus 100)"""
        tree = _build_tree_from_db(self.db)
        html = _build_tree_render_html(tree, highlight_map={})
        self.assertIn("本期可拿 $145.00", html,
            f"HTML 应渲染 '本期可拿 $145.00' 徽章 (PR #71 teamBonus=100). HTML excerpt: {html[:500]}")


class TestPr58PairBonus(unittest.TestCase):
    """T3: 7 层对等累加 (3 层 tree: root→z1→z1.1)"""

    def setUp(self):
        self.engine, Session = _make_test_db()
        self.db = Session()
        self.db.query(CommissionPeriod).delete()
        self.db.query(PVLedger).delete()
        self.db.query(Member).delete()
        self.db.add(Member(
            member_dist_id="N5637590.1", member_name="王常军",
            parent_dist_id=None, slot_line_id=0,
            max_lines=2, current_pv_balance=0, total_commission=0.0,
        ))
        self.db.add(Member(
            member_dist_id="N5637590.2", member_name="z1",
            parent_dist_id="N5637590.1", slot_line_id=1,
            max_lines=2, current_pv_balance=0, total_commission=0.0,
        ))
        self.db.add(Member(
            member_dist_id="N5637590.3", member_name="z1.1",
            parent_dist_id="N5637590.2", slot_line_id=1,
            max_lines=5, current_pv_balance=0, total_commission=0.0,
        ))
        self.db.add(Member(
            member_dist_id="N5637590.4", member_name="z1.2",
            parent_dist_id="N5637590.2", slot_line_id=2,
            max_lines=5, current_pv_balance=0, total_commission=0.0,
        ))
        from skills.period import get_current_period_id
        self._cur = get_current_period_id()
        z11 = self.db.query(Member).filter_by(member_dist_id="N5637590.3").first()
        z12 = self.db.query(Member).filter_by(member_dist_id="N5637590.4").first()
        self.db.add(PVLedger(member_id=z11.id, member_dist_id="N5637590.3",
                              period_id=self._cur, pv_amount=500, status="pending"))
        self.db.add(PVLedger(member_id=z12.id, member_dist_id="N5637590.4",
                              period_id=self._cur, pv_amount=300, status="pending"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_z1_ownbasic_45(self):
        """z1: 子区 [z1.1=500, z1.2=300], P=500, L=300, ownBasic = 45"""
        tree = _build_tree_from_db(self.db)
        z1 = next(c for c in tree["children"] if not c.get("available") and c["distId"] == "N5637590.2")
        self.assertAlmostEqual(z1["ownBasic"], 45.0, places=2)

    def test_root_ownbasic_0(self):
        """root: 子区 [z1=0 (z1 自己没 PV)], P=0, L=0, ownBasic = 0"""
        tree = _build_tree_from_db(self.db)
        self.assertAlmostEqual(tree["ownBasic"], 0.0, places=2)

    def test_root_pair_bonus_675(self):
        """★ PR #58 核心: 王常军 pairBonus 来自 z1.ownBasic=45 × 0.15 = 6.75
        ★ PR #71: teamBonus 4 档精确匹配 — 1区: z1.1=500 → 500×20% = 100
        total = 0 + 6.75 + 100 = 106.75
        """
        tree = _build_tree_from_db(self.db)
        # ★ PR #71: 1区: z1.1=500 → 500×20% = 100, z1.2=300 → 0
        #   teamBonus = 100
        self.assertAlmostEqual(tree["teamBonus"], 100.0, places=2)
        self.assertAlmostEqual(tree["commissionPreview"], 106.75, places=2,
            msg=f"王常军 commissionPreview 应 = 0 + 6.75 + 100 = 106.75, 实际: {tree['commissionPreview']}")


class TestPr58Depth7Pairing(unittest.TestCase):
    """T3 延伸: 4 层 tree, depth=2 累加 (ratio=0.10)"""

    def setUp(self):
        self.engine, Session = _make_test_db()
        self.db = Session()
        self.db.query(CommissionPeriod).delete()
        self.db.query(PVLedger).delete()
        self.db.query(Member).delete()
        # root → a → b → c/d
        for did, parent, line, name in [
            ("N5637590.1", None, 0, "root"),
            ("N5637590.2", "N5637590.1", 1, "a"),
            ("N5637590.3", "N5637590.2", 1, "b"),
            ("N5637590.4", "N5637590.3", 1, "c"),
            ("N5637590.5", "N5637590.3", 2, "d"),
        ]:
            self.db.add(Member(
                member_dist_id=did, member_name=name,
                parent_dist_id=parent, slot_line_id=line,
                max_lines=2, current_pv_balance=0, total_commission=0.0,
            ))
        from skills.period import get_current_period_id
        self._cur = get_current_period_id()
        c = self.db.query(Member).filter_by(member_dist_id="N5637590.4").first()
        d = self.db.query(Member).filter_by(member_dist_id="N5637590.5").first()
        self.db.add(PVLedger(member_id=c.id, member_dist_id="N5637590.4",
                              period_id=self._cur, pv_amount=500, status="pending"))
        self.db.add(PVLedger(member_id=d.id, member_dist_id="N5637590.5",
                              period_id=self._cur, pv_amount=300, status="pending"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_4_level_pair_bonus(self):
        """4 层: c+d 配对 → b.ownBasic=45 → a.pair=6.75, root.pair=4.50
        ★ PR #71: teamBonus 4 档精确匹配 — 1区: c=500 → 500×20%=100, d=300 → 0
        - a: 1区 = b subtree (b=0, c=500, d=300), tier-based: c 100 + d 0 + b 0 = 100
        - root: 1区 = a subtree (a=0, b=0, c=500, d=300), tier-based: 100
        - a.commissionPreview = 0 + 6.75 + 100 = 106.75
        - root.commissionPreview = 0 + 4.50 + 100 = 104.50
        """
        tree = _build_tree_from_db(self.db)
        a = next(c for c in tree["children"] if not c.get("available"))
        b = next(c for c in a["children"] if not c.get("available"))
        # b.ownBasic = 45 (c+d 配对)
        self.assertAlmostEqual(b["ownBasic"], 45.0, places=2)
        # a.commissionPreview = a.ownBasic(0) + pair from b(45 × 0.15) + a.teamBonus(100) = 106.75
        self.assertAlmostEqual(a["teamBonus"], 100.0, places=2)
        self.assertAlmostEqual(a["commissionPreview"], 106.75, places=2)
        # root.commissionPreview = pair from b(45 × 0.10) + root.teamBonus(100) = 104.50
        self.assertAlmostEqual(tree["teamBonus"], 100.0, places=2)
        self.assertAlmostEqual(tree["commissionPreview"], 104.50, places=2)


class TestPr58UI(unittest.TestCase):
    """T8/T9: UI 渲染紫色徽章"""

    def test_main_py_uses_tv_commission_preview_class(self):
        """main.py _tree_render_node 渲染 .tv-commission-preview class"""
        self.assertIn('"tv-commission-preview"', MAIN_PY,
            "main.py _tree_render_node 渲染应含 'tv-commission-preview' class")

    def test_main_py_has_本期可拿_label(self):
        """main.py 徽章文本 '本期可拿 $X.XX' (PR #73 commission 直接当美元)"""
        self.assertIn("本期可拿 $", MAIN_PY,
            "main.py 徽章应包含 '本期可拿 $X.XX' 文本 (PR #73: commission 数字直接当美元)")

    def test_main_py_has_own_pair_tooltip(self):
        """★ PR #69: tooltip 文案 — 基本佣金 + 对等奖金 + 团队培育奖金
        (旧 PR #58 用 own basic + 7层对等, PR #69 用户拍板改名)
        """
        self.assertIn("基本佣金", MAIN_PY,
            "tooltip 应说明 '基本佣金' 分解 (PR #69)")
        self.assertIn("对等奖金", MAIN_PY,
            "tooltip 应说明 '对等奖金' 分解 (PR #69)")
        self.assertIn("团队培育奖金", MAIN_PY,
            "tooltip 应说明 '团队培育奖金' 分解 (PR #69)")

    def test_css_purple_in_index_html(self):
        """static/index.html CSS .tv-commission-preview 用紫色"""
        m = re.search(r'\.tree-view\s+\.tv-commission-preview\s*\{[^}]+\}', INDEX_HTML, re.DOTALL)
        self.assertIsNotNone(m, "CSS .tv-commission-preview 必须存在")
        css = m.group(0)
        self.assertTrue(
            "#6D28D9" in css or "#EDE9FE" in css or "#C4B5FD" in css,
            f"CSS 必须用紫色, 实际: {css[:200]}"
        )

    def test_css_2px_grid_compliance(self):
        """CSS padding/margin 走 2 倍数步进"""
        m = re.search(r'\.tree-view\s+\.tv-commission-preview\s*\{[^}]+\}', INDEX_HTML, re.DOTALL)
        self.assertIsNotNone(m)
        css = m.group(0)
        paddings = re.findall(r'padding:\s*(\d+)px\s*(\d+)px', css)
        margins = re.findall(r'margin:\s*(\d+)px(?:\s+(\d+)px)?', css)
        for nums in paddings + margins:
            for v in nums:
                if not v: continue
                v_int = int(v)
                self.assertEqual(v_int % 2, 0, f"CSS 间距 {v_int}px 不是 2 倍数")


class TestPr58SettledHidesPreview(unittest.TestCase):
    """T5: settled 期徽章不显示"""

    def setUp(self):
        self.engine, Session = _make_test_db()
        self.db = Session()
        self.db.query(CommissionPeriod).delete()
        self.db.query(PVLedger).delete()
        self.db.query(Member).delete()
        self.db.add(Member(
            member_dist_id="N5637590.1", member_name="王常军",
            parent_dist_id=None, slot_line_id=0,
            max_lines=2, current_pv_balance=0, total_commission=0.0,
        ))
        self.db.add(Member(
            member_dist_id="N5637590.2", member_name="z1",
            parent_dist_id="N5637590.1", slot_line_id=1,
            max_lines=5, current_pv_balance=0, total_commission=0.0,
        ))
        self.db.add(Member(
            member_dist_id="N5637590.3", member_name="z2",
            parent_dist_id="N5637590.1", slot_line_id=2,
            max_lines=5, current_pv_balance=0, total_commission=0.0,
        ))
        from skills.period import get_current_period_id
        self._cur = get_current_period_id()
        z1 = self.db.query(Member).filter_by(member_dist_id="N5637590.2").first()
        z2 = self.db.query(Member).filter_by(member_dist_id="N5637590.3").first()
        self.db.add(PVLedger(member_id=z1.id, member_dist_id="N5637590.2",
                              period_id=self._cur, pv_amount=500, status="paired"))
        self.db.add(PVLedger(member_id=z2.id, member_dist_id="N5637590.3",
                              period_id=self._cur, pv_amount=300, status="paired"))
        self.db.add(CommissionPeriod(
            id=self._cur, period_type="weekly", status="settled",
            start_at=0, end_at=99999999999,
            total_commission=45.0, total_pv_consumed=300, total_pv_carried=500,
        ))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_settled_hides_preview_in_html(self):
        tree = _build_tree_from_db(self.db)
        # ★ PR #71: commissionPreview = ownBasic 45 + pairBonus 0 + teamBonus 100 (4 档精确) = 145
        self.assertAlmostEqual(tree["commissionPreview"], 145.0, places=2)
        self.assertEqual(tree["currentPeriodStatus"], "settled")
        # HTML 渲染: 不显示徽章
        html = _build_tree_render_html(tree, highlight_map={})
        self.assertNotIn("本期可拿", html,
            f"settled 期不应显示 '本期可拿' 徽章. HTML excerpt: {html[:500]}")


if __name__ == "__main__":
    unittest.main()
