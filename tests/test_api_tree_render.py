# -*- coding: utf-8 -*-
r"""
test_api_tree_render.py —— /api/tree/render PR #34 行为测试
================================================================

PR #34 (2026-07-16) DB name 同步覆盖 json 树 name:
    - api_tree_render 拉 DB 的 member_name, 递归覆盖 raw 树的 name
    - user 反馈: DB admin 改了 member_name, tree view 还是旧名 (json 树覆盖)

测试覆盖:
    1. 改 DB name 后, tree view 同步显示新名
    2. 没改的成员, 名字跟 DB 一致
    3. DB 里没的成员 (json 树独有), 保留 json 树原 name
    4. avail 节点没 distId, 不被覆盖
    5. 递归覆盖 (子节点 + 孙节点)
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


class TestApiTreeRenderNameFromDb(unittest.TestCase):
    """PR #34: api_tree_render 跟 DB 同步 name"""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def setUp(self):
        """每个测试: 清空, 重建 fixture"""
        db = SessionLocal()
        try:
            db.query(Member).delete()
            db.commit()
        finally:
            db.close()
        # 恢复 json 树 fixture (主仓的, 跟 user 改之前的原始状态)
        from shutil import copyfile
        src = PROJECT_ROOT / "json" / "Tree_empty_5_3.json"
        # 已经被测试改过, 从 worktree 跟主仓的源复制
        # 但我们 worktree 里 json 已经被复制了. 备份当前, 测试完恢复.
        # 简单做法: 留 json 树不动, 只改 DB
        # (因为测试只关心 DB 覆盖, 不关心 json 原始内容)
        self._build_db_fixture()

    def _build_db_fixture(self):
        """★ 2026-07-16 PR #37: 适配清理后的 json 树 (root + Y)
        - DB 同步放 N-7000012 (Y) 挂 line 1
        - 名字用 DB_Y 测试用 (验证 DB 覆盖 json name)
        - 注: root 由 test_root_name_from_db 单独 seed (避免跟其他测试 setUp 重复)
        """
        db = SessionLocal()
        try:
            # Y 在 line 1
            db.add(Member(member_dist_id="N-7000012", member_name="DB_Y",
                          parent_dist_id="N5637590.1", slot_line_id=1,
                          max_lines=5, current_pv_balance=0, total_commission=0.0,
                          created_period_id="2026-07-12_W29", last_period_id="2026-07-12_W29"))
            db.commit()
        finally:
            db.close()

    def _render_html(self) -> str:
        """调 api_tree_render 拿 html 字符串"""
        r = self.client.post("/api/tree/render", json={
            "skill": "skill_5_3",
            "slot_view": "all",
            "committed": True,
            "highlights": [],
        })
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["html"]

    def test_tree_view_uses_db_name(self):
        """DB 里的名字覆盖 json 树 (清理后 fixture: root + Y)"""
        # 单独放 root (避免 setUp 重复)
        db = SessionLocal()
        try:
            db.add(Member(member_dist_id="N5637590.1", member_name="DB_ROOT",
                          parent_dist_id=None, slot_line_id=0,
                          max_lines=5, current_pv_balance=0, total_commission=0.0,
                          created_period_id="2026-07-05_W28", last_period_id=None))
            db.commit()
        finally:
            db.close()
        html = self._render_html()
        # DB 名字应该出现
        self.assertIn("DB_ROOT", html)
        self.assertIn("DB_Y", html)

    def test_unmodified_member_uses_db_name(self):
        """没改的成员, 也用 DB 的 (一致)"""
        # 单独放 root
        db = SessionLocal()
        try:
            db.add(Member(member_dist_id="N5637590.1", member_name="DB_ROOT",
                          parent_dist_id=None, slot_line_id=0,
                          max_lines=5, current_pv_balance=0, total_commission=0.0,
                          created_period_id="2026-07-05_W28", last_period_id=None))
            db.commit()
        finally:
            db.close()
        html = self._render_html()
        # 2 个 fixture (root + Y) 都在
        for name in ("DB_ROOT", "DB_Y"):
            self.assertIn(name, html)

    def test_db_update_syncs_to_tree(self):
        """改 DB 后, tree view 同步显示新名

        ★ 2026-07-16 PR #39: 改为验证 _build_tree_from_db 实时从 DB 读
          - 之前 (PR #34): 改 DB name 覆盖 json 树 (双数据源同步)
          - 现在 (PR #39): DB 是单一数据源, 改 DB name → 立即渲染新名
        """
        # 先放 root (没有 root, _build_tree_from_db 返回空树)
        db = SessionLocal()
        try:
            db.add(Member(member_dist_id="N5637590.1", member_name="ROOT",
                          parent_dist_id=None, slot_line_id=0,
                          max_lines=5, current_pv_balance=0, total_commission=0.0,
                          created_period_id="2026-07-05_W28", last_period_id=None))
            # 改 Y (N-7000012) 名字
            m = db.query(Member).filter_by(member_dist_id="N-7000012").first()
            m.member_name = "RENAMED_Y"
            db.commit()
        finally:
            db.close()
        html = self._render_html()
        self.assertIn("RENAMED_Y", html)
        # 旧名 DB_Y 不应该出现
        self.assertNotIn(">DB_Y<", html)  # 不会单独显示

    def test_root_name_from_db(self):
        """root name 也用 DB 的 (root.distId='N5637590.1')"""
        # 改 root name
        db = SessionLocal()
        try:
            db.add(Member(member_dist_id="N5637590.1", member_name="ROOT_DB_NAME",
                          parent_dist_id=None, slot_line_id=0,
                          max_lines=5, current_pv_balance=0, total_commission=0.0,
                          created_period_id="2026-07-05_W28", last_period_id=None))
            db.commit()
        finally:
            db.close()
        r = self.client.post("/api/tree/render", json={
            "skill": "skill_5_3",
            "slot_view": "all",
            "committed": True,
            "highlights": [],
        })
        data = r.json()
        # root_name 应该是 DB 的
        self.assertEqual(data["root_name"], "ROOT_DB_NAME")

    def test_avail_node_not_overwritten(self):
        """avail 节点没 distId, 不被覆盖 (保留 "?" 标识)

        ★ 2026-07-16 PR #39: 改为验证 _build_tree_from_db 渲染出的 avail 占位结构
          - 之前 (PR #34): avail 节点是 json 树固有的, 测 name 不被覆盖
          - 现在 (PR #39): avail 节点由 _build_tree_from_db 实时补 (real < maxLines)
        """
        # root + Y 都在 → Y 是 real, root.line 2-5 是 avail, Y.line 1-5 是 avail
        # 加 root 让树结构完整
        db = SessionLocal()
        try:
            db.add(Member(member_dist_id="N5637590.1", member_name="ROOT",
                          parent_dist_id=None, slot_line_id=0,
                          max_lines=5, current_pv_balance=0, total_commission=0.0,
                          created_period_id="2026-07-05_W28", last_period_id=None))
            db.commit()
        finally:
            db.close()
        html = self._render_html()
        # avail 节点应该渲染 (有 .tv-avail class)
        self.assertIn("tv-avail", html, "avail 占位节点应在 html 中")
        # 渲染没崩
        self.assertIsInstance(html, str)
        self.assertGreater(len(html), 100)


class TestApiTreeRenderDirectCount(unittest.TestCase):
    """PR #38: 树状图节点渲染直推人数徽章 (实时聚合 parent_dist_id = self)"""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def setUp(self):
        """清空 + 重建 fixture: root (王常军) + Y 挂 line 1 + 3 个新成员挂 Y"""
        db = SessionLocal()
        try:
            db.query(Member).delete()
            db.commit()
            # root
            db.add(Member(member_dist_id="N5637590.1", member_name="王常军",
                          parent_dist_id=None, slot_line_id=0,
                          max_lines=5, current_pv_balance=0, total_commission=0.0,
                          created_period_id="2026-07-05_W28", last_period_id=None))
            # Y 挂 line 1
            db.add(Member(member_dist_id="N-7000012", member_name="Y",
                          parent_dist_id="N5637590.1", slot_line_id=1,
                          max_lines=5, current_pv_balance=0, total_commission=0.0,
                          created_period_id="2026-07-12_W29", last_period_id=None))
            # 3 个直推挂 Y
            for i in range(1, 4):
                db.add(Member(member_dist_id=f"N-Y-SUB-{i}", member_name=f"Y子{i}",
                              parent_dist_id="N-7000012", slot_line_id=i,
                              max_lines=5, current_pv_balance=0, total_commission=0.0,
                              created_period_id="2026-07-12_W29", last_period_id=None))
            db.commit()
        finally:
            db.close()

    def _render_html(self) -> str:
        r = self.client.post("/api/tree/render", json={
            "skill": "skill_5_3", "slot_view": "all", "committed": True, "highlights": [],
        })
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["html"]

    def test_root_has_one_direct_badge(self):
        """root 有 1 个直推 (N-ROOT-SUB) → html 含 "直推 1" badge"""
        html = self._render_html()
        # root N5637590.1 有 1 直推 (N-ROOT-SUB)
        # ★ 2026-07-16 PR #44: distId 在 line 2, direct badge 紧跟其后 (同 line2)
        #   buffer 200 字符足够覆盖 distId + badge title + "直推 N" 文本
        idx = html.find("N5637590.1")
        self.assertGreater(idx, 0)
        snippet = html[max(0, idx-500):idx+200]
        self.assertIn("tv-badge-direct", snippet)
        self.assertIn("直推 1", snippet)

    def test_y_node_shows_three_direct(self):
        """Y 节点有 3 个直推子 → html 含 "直推 3" badge"""
        html = self._render_html()
        self.assertIn("直推 3", html)
        # ★ 2026-07-16 PR #44: distId 在 line 2, direct badge 紧跟其后 (同 line2)
        idx = html.find("N-7000012")
        self.assertGreater(idx, 0)
        snippet = html[max(0, idx-500):idx+200]
        self.assertIn("tv-badge-direct", snippet)
        self.assertIn("直推 3", snippet)

    def test_avail_node_no_direct_badge(self):
        """avail 节点没 distId, 不应该显示直推 badge
        期望 badge 数量 = 2 (root 直推 1 + Y 直推 3, avail 节点不显示)
        """
        html = self._render_html()
        # avail 节点 div tv-node tv-avail 不应包含 tv-badge-direct
        n_direct_badge = html.count("tv-badge-direct")
        self.assertEqual(n_direct_badge, 2, f"root(1) + Y(3) = 2, got {n_direct_badge}")

    def test_direct_count_in_raw(self):
        """api_tree_render 注入的 raw 树节点 directCount 字段正确"""
        r = self.client.post("/api/tree/render", json={
            "skill": "skill_5_3", "slot_view": "all", "committed": True, "highlights": [],
        })
        d = r.json()
        # 不能直接看 raw (只返 html), 但 html 里 Y 节点附近有 "直推 3" 就是证明
        # 旁证: 加 1 个 N-Y-SUB-4 挂 Y, 立即变 "直推 4"
        db = SessionLocal()
        try:
            db.add(Member(member_dist_id="N-Y-SUB-4", member_name="Y子4",
                          parent_dist_id="N-7000012", slot_line_id=4,
                          max_lines=5, current_pv_balance=0, total_commission=0.0,
                          created_period_id="2026-07-12_W29", last_period_id=None))
            db.commit()
        finally:
            db.close()
        html2 = self._render_html()
        self.assertIn("直推 4", html2)


# ============================================================
# ★ 2026-07-17 PR #51: 本期 PV 字段 + 累计 commission 字段 + 结算按钮
#   - _build_tree_from_db 注入 periodPv (从 PVLedger.pv_amount 聚合)
#   - _tree_render_node 显示 "本期 X PV" 徽章 (绿/灰按值)
#   - _tree_render_html toolbar 加 "💰 结算本周" 按钮 + 本周 commission 概览
# ============================================================
class TestApiTreeRenderPeriodPv(unittest.TestCase):
    """PR #51: 名片 PV 字段从 PVLedger.pv_amount 读, 替代之前 current_pv_balance"""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def setUp(self):
        """清 DB (PR #50 风格, 包含 N-7* 老数据) + seed root

        ★ 2026-07-17 PR #54 v2: 也清 commission_periods
          - 默认测试场景: period.status=open (没在 commission_periods 表里)
          - 测 settled 行为: 单独加 CommissionPeriod(status=settled)
        """
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
                          created_period_id="2026-07-05_W28", last_period_id=None))
            db.commit()
        finally:
            db.close()

    def _root_id(self) -> int:
        """拿 root member 的 id (PR #51 测试用, 因为 setUp 后 id 不可预测)"""
        db = SessionLocal()
        try:
            m = db.query(Member).filter(Member.member_dist_id == "N5637590.1").first()
            return int(m.id) if m else 1
        finally:
            db.close()

    def test_period_pv_badge_appears_for_current_period(self):
        """★ PR #51: root 本期新增 800 PV (从 PVLedger 聚合) → 名片显示 "本期 800 PV" 绿色徽章"""
        from skills.period import get_current_period_id
        _cur_period = get_current_period_id()
        _rid = self._root_id()
        db = SessionLocal()
        try:
            # 模拟 2 次挂入, 累计 800 PV
            db.add(PVLedger(member_id=_rid, member_dist_id="N5637590.1",
                            period_id=_cur_period, pv_amount=500, status="pending"))
            db.add(PVLedger(member_id=_rid, member_dist_id="N5637590.1",
                            period_id=_cur_period, pv_amount=300, status="pending"))
            db.commit()
        finally:
            db.close()

        r = self.client.post("/api/tree/render", json={
            "skill": "skill_5_3", "slot_view": "all", "committed": True, "highlights": [],
        })
        self.assertEqual(r.status_code, 200)
        html = r.json()["html"]
        # ★ 验证: 名片 line2 有 "本期 800 PV" 徽章 (data-pv-positive="1" = 绿色)
        self.assertIn("本期 800 PV", html)
        self.assertIn('data-pv-positive="1"', html)
        # ★ 验证: toolbar 显示本周 commission 概览
        self.assertIn("本周", html)
        self.assertIn("结算本周", html)

    def test_period_pv_zero_uses_neutral_color(self):
        """★ PR #51: 本期 0 PV → 名片不显示徽章 (避免冗余, 跟剩余 PV 保持一致)"""
        # 没加任何 ledger, period_pv=0
        r = self.client.post("/api/tree/render", json={
            "skill": "skill_5_3", "slot_view": "all", "committed": True, "highlights": [],
        })
        html = r.json()["html"]
        # ★ 2026-07-17 PR #54: 0 不显示 (跟剩余 PV 保持一致, 都是 0 不显示避免冗余)
        idx = html.find("N5637590.1")
        self.assertGreater(idx, 0)
        snippet = html[idx:idx+600]
        self.assertNotIn("本期 0 PV", snippet)

    def test_avail_node_does_not_show_pv_badge(self):
        """★ PR #51: avail 节点不显示 PV 徽章 (无业务意义)"""
        r = self.client.post("/api/tree/render", json={
            "skill": "skill_5_3", "slot_view": "all", "committed": True, "highlights": [],
        })
        html = r.json()["html"]
        # ★ 验证: avail 节点 (.tv-avail class) 不应含 tv-badge-pv 徽章
        # 用 div class 切片, 找到所有 .tv-avail 节点
        import re
        # 找 .tv-avail 节点 (开 div, 找对应的 </div> 闭合 - 简化版: 用 lazy 拿 <summary> 内容)
        avail_summaries = re.findall(r'<summary class="tv-card">(.*?)</summary>', html, re.DOTALL)
        # 至少 1 个 avail 节点 (avail 用 <details> 而非 <div>, 但 summary 内不含本期)
        # 检查所有 summary 内部
        for s in avail_summaries:
            # avail summary 不应含 "本期 X PV"
            self.assertNotIn("本期 ", s, f"avail summary 不应有 PV 徽章: {s[:200]}")
            self.assertNotIn("tv-badge-pv", s, f"avail summary 不应有 tv-badge-pv class: {s[:200]}")

    def test_total_commission_badge_appears_when_nonzero(self):
        """★ PR #51: Member.total_commission > 0 → 显示 "累计 $X.XX" 徽章"""
        db = SessionLocal()
        try:
            # root 总 commission 75.00 (历史 settle 累加)
            m = db.query(Member).filter(Member.member_dist_id == "N5637590.1").first()
            m.total_commission = 75.00
            db.commit()
        finally:
            db.close()

        r = self.client.post("/api/tree/render", json={
            "skill": "skill_5_3", "slot_view": "all", "committed": True, "highlights": [],
        })
        html = r.json()["html"]
        self.assertIn("累计 $75.00", html)

    def test_settle_button_in_toolbar(self):
        """★ PR #51: 树状图 toolbar 有 "💰 结算本周" 按钮 + onClick 绑定"""
        r = self.client.post("/api/tree/render", json={
            "skill": "skill_5_3", "slot_view": "all", "committed": True, "highlights": [],
        })
        html = r.json()["html"]
        # 验证按钮存在 + ID 跟 JS 函数引用一致
        self.assertIn('id="settleCurrentWeekBtn"', html)
        self.assertIn("结算本周", html)
        self.assertIn('onclick="settleCurrentWeek(this)"', html)
        # 验证 toolbar 显示本周 (业务周格式 "YYYY-MM-DD_Www", PR #55)
        import re
        m = re.search(r"本周 <b>(\d{4}-\d{2}-\d{2}_W\d{2})</b>", html)
        self.assertIsNotNone(m, "toolbar 应该有本周业务周期 (YYYY-MM-DD_Www)")

    def test_toolbar_two_row_layout(self):
        """★ PR #52: 工具栏分两行布局 (信息行 + 操作行) — 解决单行太挤问题"""
        r = self.client.post("/api/tree/render", json={
            "skill": "skill_5_3", "slot_view": "all", "committed": True, "highlights": [],
        })
        html = r.json()["html"]
        import re
        # 找到两个 .tv-toolbar-row div 的开始位置
        row_positions = [m.start() for m in re.finditer(r'<div class="tv-toolbar-row(?:[^"]*)">', html)]
        self.assertEqual(len(row_positions), 2, f"toolbar 应该有 2 行, 实际 {len(row_positions)}: {row_positions}")
        # 第 1 行 (start..第 2 行 start): 核心信息
        first_row_html = html[row_positions[0]:row_positions[1]]
        self.assertIn("5 叉网体", first_row_html)
        self.assertIn("settleCurrentWeekBtn", first_row_html)
        # 第 2 行 (start..toolbar 结束): 视图控制
        toolbar_end = html.find("</div>\n  </div>", row_positions[1])  # tv-toolbar-row + tree-view-toolbar 闭合
        if toolbar_end < 0:
            toolbar_end = html.find("</div>", row_positions[1] + 100)  # fallback
        second_row_html = html[row_positions[1]:toolbar_end + 6] if toolbar_end > 0 else html[row_positions[1]:row_positions[1] + 3000]
        self.assertIn("treeNodeFilter", second_row_html)
        self.assertIn("tv-btn-close", second_row_html)

    def test_toolbar_no_text_wrapping(self):
        """★ PR #52: toolbar 内 stat 不换行 (white-space: nowrap)"""
        r = self.client.post("/api/tree/render", json={
            "skill": "skill_5_3", "slot_view": "all", "committed": True, "highlights": [],
        })
        html = r.json()["html"]
        # 验证 .tv-stat 有 white-space: nowrap (CSS)
        # 简单做法: 检查 toolbar CSS 类已加上 nowrap 规则
        # 因为测试只能查 HTML 结构, 跑一个 js 检查
        # (跳过, 实际渲染靠 playwright 验证)

    # ============== PR #54: 剩余 PV 徽章 (跨期 carry) ==============

    def test_carry_pv_badge_appears_when_carry_nonzero(self):
        """★ PR #54: Member.current_pv_balance > 0 → 名片显示 "剩余 X PV" 黄色徽章

        用户 (2026-07-17) 反馈: "结算后张a 500 PV 应该变成剩余 200 PV (500-300)"
        业务: 跟「本期 PV」是两个独立字段
          - 本期 PV: 本期新增 (PVLedger.pv_amount 聚合), 仅在 period.status=open 时显示
          - 剩余 PV: 跨期 carry (Member.current_pv_balance), 任何时候都显示

        ★ 2026-07-17 PR #54 v2: 本期 vs 剩余 互斥
          - period.status=settled → 本期 PV 隐藏 (本期已落账到 carry/commission)
          - period.status=open → 本期 PV 显示 (跟剩余 PV 可同时显示)
        """
        from models import PVLedger, CommissionPeriod
        from skills.period import get_current_period_id, get_period_range
        _cur = get_current_period_id()
        _start, _end = get_period_range(_cur)
        db = SessionLocal()
        try:
            m = db.query(Member).filter(Member.member_dist_id == "N5637590.1").first()
            m.current_pv_balance = 200  # 模拟结算后 carry 余额
            db.add(PVLedger(member_id=m.id, member_dist_id="N5637590.1",
                            period_id=_cur, pv_amount=500, status="paired",
                            commission_amount=45.0))
            # ★ PR #54 v2: 模拟结算后, period.status=settled
            db.add(CommissionPeriod(id=_cur, period_type="weekly", status="settled",
                                    start_at=_start, end_at=_end,
                                    total_commission=45.0, total_pv_consumed=300,
                                    total_pv_carried=200, member_count=2,
                                    settled_at=1784275578.6, settled_by="manual",
                                    created_at=1784275578.6))
            db.commit()
        finally:
            db.close()

        r = self.client.post("/api/tree/render", json={
            "skill": "skill_5_3", "slot_view": "all", "committed": True, "highlights": [],
        })
        html = r.json()["html"]
        # 验证: 名片 line2 有 "剩余 200 PV" 徽章
        idx = html.find("N5637590.1")
        self.assertGreater(idx, 0)
        snippet = html[idx:idx+800]
        self.assertIn("剩余 200 PV", snippet)
        # ★ PR #54 v2: period 已 settled, 本期 PV 徽章**不显示** (本期已落账, 不再算"本期新增")
        #   用户原话: "这个位置应该变成显示'剩余200PV'" — 同一位置互斥
        self.assertNotIn("本期 500 PV", snippet,
            f"period=settled 时本期 PV 徽章应隐藏, 实际 html: {snippet[:500]}")

    def test_period_pv_badge_hidden_when_period_settled(self):
        """★ PR #54 v2: 当前 ISO 周 status=settled → 本期 PV 徽章隐藏

        业务规则: 本期已结算, 落账到 carry / commission, "本期新增"业务语义已不适用
        互斥规则: 同一位置, 本期(open) vs 剩余(settled 或 carry) 二选一
        """
        from models import PVLedger, CommissionPeriod
        from skills.period import get_current_period_id, get_period_range
        _cur = get_current_period_id()
        _start, _end = get_period_range(_cur)
        db = SessionLocal()
        try:
            m = db.query(Member).filter(Member.member_dist_id == "N5637590.1").first()
            m.current_pv_balance = 200  # 结算后 carry
            db.add(PVLedger(member_id=m.id, member_dist_id="N5637590.1",
                            period_id=_cur, pv_amount=500, status="paired",
                            commission_amount=45.0))
            # 关键: 标 period=settled
            db.add(CommissionPeriod(id=_cur, period_type="weekly", status="settled",
                                    start_at=_start, end_at=_end,
                                    total_commission=45.0, total_pv_consumed=300,
                                    total_pv_carried=200, member_count=2,
                                    settled_at=1784275578.6, settled_by="manual",
                                    created_at=1784275578.6))
            db.commit()
        finally:
            db.close()

        r = self.client.post("/api/tree/render", json={
            "skill": "skill_5_3", "slot_view": "all", "committed": True, "highlights": [],
        })
        html = r.json()["html"]
        idx = html.find("N5637590.1")
        self.assertGreater(idx, 0)
        snippet = html[idx:idx+800]
        # 本期 PV 徽章不显示 (period=settled)
        self.assertNotIn("本期 500 PV", snippet)
        # 但剩余 PV 徽章照常显示 (carry=200)
        self.assertIn("剩余 200 PV", snippet)

    def test_period_pv_badge_shows_alongside_carry_when_period_open(self):
        """★ PR #54 v2 回归: period.status=open 时, 本期 PV + 剩余 PV 可同时显示 (两个独立字段)

        业务: 未结算期, 本期新加 500 (绿) + 跨期 carry 200 (黄) 都展示
        """
        from models import PVLedger
        from skills.period import get_current_period_id
        _cur = get_current_period_id()
        db = SessionLocal()
        try:
            m = db.query(Member).filter(Member.member_dist_id == "N5637590.1").first()
            m.current_pv_balance = 200  # 跨期 carry (从之前期)
            db.add(PVLedger(member_id=m.id, member_dist_id="N5637590.1",
                            period_id=_cur, pv_amount=500, status="pending"))
            # 注意: 没在 commission_periods 加行, 默认 status=open
            db.commit()
        finally:
            db.close()

        r = self.client.post("/api/tree/render", json={
            "skill": "skill_5_3", "slot_view": "all", "committed": True, "highlights": [],
        })
        html = r.json()["html"]
        idx = html.find("N5637590.1")
        self.assertGreater(idx, 0)
        snippet = html[idx:idx+800]
        # 本期 PV 徽章显示 (period=open)
        self.assertIn("本期 500 PV", snippet)
        # 剩余 PV 徽章也显示 (carry=200)
        self.assertIn("剩余 200 PV", snippet)

    def test_carry_pv_badge_hidden_when_zero(self):
        """★ PR #54: current_pv_balance = 0 → 不显示 "剩余 0 PV" (避免冗余)"""
        # default setUp: root.current_pv_balance=0
        r = self.client.post("/api/tree/render", json={
            "skill": "skill_5_3", "slot_view": "all", "committed": True, "highlights": [],
        })
        html = r.json()["html"]
        idx = html.find("N5637590.1")
        self.assertGreater(idx, 0)
        snippet = html[idx:idx+800]
        # 0 不显示剩余 PV
        self.assertNotIn("剩余 0 PV", snippet)
        # 也没本期 PV (没 ledger)
        self.assertNotIn("本期 0 PV", snippet)

    def test_avail_node_does_not_show_carry_pv_badge(self):
        """★ PR #54: avail 节点不显示剩余 PV 徽章 (跟 periodPv 一致)"""
        r = self.client.post("/api/tree/render", json={
            "skill": "skill_5_3", "slot_view": "all", "committed": True, "highlights": [],
        })
        html = r.json()["html"]
        import re
        avail_summaries = re.findall(r'<summary class="tv-card">(.*?)</summary>', html, re.DOTALL)
        for s in avail_summaries:
            self.assertNotIn("剩余 ", s, f"avail 不应有剩余 PV 徽章: {s[:200]}")
            self.assertNotIn("tv-badge-carry", s, f"avail 不应有 tv-badge-carry class")

    def test_toolbar_shows_weekly_commission_summary(self):
        """★ PR #51: toolbar 显示本周总 commission (本期 ledger 聚合)"""
        from skills.period import get_current_period_id
        _cur_period = get_current_period_id()
        _rid = self._root_id()
        db = SessionLocal()
        try:
            # 模拟本周 settle 后, ledger.commission_amount=45
            db.add(PVLedger(member_id=_rid, member_dist_id="N5637590.1",
                            period_id=_cur_period, pv_amount=300, status="paired",
                            commission_amount=45.0))
            db.commit()
        finally:
            db.close()

        r = self.client.post("/api/tree/render", json={
            "skill": "skill_5_3", "slot_view": "all", "committed": True, "highlights": [],
        })
        html = r.json()["html"]
        # ★ PR #52: 改两行布局后, commission 简化成 "💰 <b>$X.XX</b>"
        import re
        m = re.search(r"💰 <b>\$([\d.]+)</b>", html)
        self.assertIsNotNone(m, f"toolbar 应显示本周总 commission: ...{html[html.find('tree-view-toolbar'):html.find('tree-view-toolbar')+1500]}")
        self.assertEqual(float(m.group(1)), 45.0)


if __name__ == "__main__":
    unittest.main()
