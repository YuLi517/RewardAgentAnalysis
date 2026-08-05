# -*- coding: utf-8 -*-
"""
test_pr61_batch_ui_redesign.py —— PR #61 批量添加页面重新设计测试

业务背景 (2026-07-21):
  PR #60 加了 +/- spinner 按钮, 但 CSS 用 .tree-view scope, modal/form 内不生效
  用户反馈: 重新设计这个页面 (UI design skill)

PR #61 修复:
  1. CSS scope bug: 去掉 .tree-view 前缀, .pv-stepper 通用 (modal/form/skill 都生效)
  2. 加 focus state: input 边框变蓝绿 (主色), box-shadow 0 0 0 2px
  3. 加 hover state: row-input 边框略深 (提示可交互)
  4. 加 disabled state: submit 按钮 0 行时 opacity 0.5 + cursor not-allowed
  5. 加 focus-visible: 按钮键盘 focus 可见 (accessibility)
  6. 严格 8pt grid (2/4/6/8/12/16/24)

测试:
  T1: .pv-stepper CSS 通用 (不带 .tree-view scope)
  T2: input focus state (主色 #5AA4AE + box-shadow)
  T3: input.invalid focus state (红色 #EF4444)
  T4: row-input hover state (边框 #B5C9CE)
  T5: row-input focus state (主色边框 + box-shadow)
  T6: row-input.invalid focus state
  T7: row-del focus-visible (主色 outline)
  T8: submit 按钮 disabled 状态
  T9: 8pt grid 严格 (2 倍数步进)
  T10: input padding-right 22px (给按钮留位)
"""
import re
import sys
import unittest
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ))

INDEX_HTML = (PROJ / "static" / "index.html").read_text(encoding="utf-8")


class TestPr61StepperScopeFixed(unittest.TestCase):
    """T1: .pv-stepper CSS 通用 (不带 .tree-view scope) — modal/form 生效"""

    def test_pv_stepper_css_no_tree_view_prefix(self):
        """CSS 选择器不应再有 .tree-view 前缀 (通用)"""
        # 找所有 .pv-stepper 之前的 selector (可能含 :hover/:focus 等修饰)
        # 简化: 找 "selector { ... }" 模式, selector 包含 .pv-stepper
        # 找 .pv-stepper 紧跟的 (可能的修饰) 后面是 {
        selectors = re.findall(
            r'([\s\S]{0,80}?\.pv-stepper[^{}\n]*)\{',
            INDEX_HTML
        )
        # 过滤: 至少含 .pv-stepper, 不含 .tree-view (在 selector 范围内)
        pv_selectors = [s.strip() for s in selectors if '.pv-stepper' in s]
        self.assertGreater(len(pv_selectors), 0,
            f"应至少 1 个 .pv-stepper CSS 块, 实际找到: {pv_selectors[:3]}")
        for selector in pv_selectors:
            # selector 是 { 之前的 80 字符, 可能含注释; 检查 .tree-view 不在
            self.assertNotIn(".tree-view", selector,
                f".pv-stepper 选择器不应带 .tree-view 前缀 (modal/form 也要生效), 实际: {selector!r}")

    def test_pv_stepper_works_in_modal(self):
        """.pv-stepper CSS 适用于 modal (用 .quick-modal-body 容器)"""
        # 检查 quick-modal-body 内能找到 .pv-stepper CSS 规则
        m = re.search(
            r'\.pv-stepper\s*\{([^}]+)\}',
            INDEX_HTML
        )
        self.assertIsNotNone(m, ".pv-stepper 通用 CSS 必须存在 (modal 容器内能用)")
        css = m.group(0)
        self.assertIn("position: relative", css)
        self.assertIn("display: inline-block", css)
        self.assertIn("width: 100%", css)


class TestPr61InputFocusState(unittest.TestCase):
    """T2-T3: input focus / invalid focus 状态"""

    def test_input_focus_state_main_color(self):
        """.pv-stepper > input:focus { border-color: #5AA4AE; box-shadow }"""
        m = re.search(
            r'\.pv-stepper\s+>\s*input:focus\s*\{([^}]+)\}',
            INDEX_HTML, re.DOTALL
        )
        self.assertIsNotNone(m, ".pv-stepper > input:focus CSS 必须存在")
        css = m.group(0)
        self.assertIn("#5AA4AE", css, "focus 边框用主色 #5AA4AE")
        self.assertIn("box-shadow", css, "focus 加 box-shadow 视觉反馈")
        self.assertIn("rgba", css, "box-shadow 用 rgba 半透明")

    def test_input_invalid_focus_state(self):
        """.pv-stepper > input.invalid:focus { border-color: #EF4444 }"""
        m = re.search(
            r'\.pv-stepper\s+>\s*input\.invalid:focus\s*\{([^}]+)\}',
            INDEX_HTML, re.DOTALL
        )
        self.assertIsNotNone(m, ".pv-stepper > input.invalid:focus CSS 必须存在")
        css = m.group(0)
        self.assertIn("#EF4444", css, "invalid focus 边框用红色 #EF4444")


class TestPr61RowInputFocusHover(unittest.TestCase):
    """T4-T7: row-input hover / focus / invalid / row-del focus"""

    def test_row_input_hover_state(self):
        """.role-batch-table .row-input:hover { border-color: #B5C9CE }"""
        m = re.search(
            r'\.role-batch-table\s+\.row-input:hover[^{]*\{([^}]+)\}',
            INDEX_HTML, re.DOTALL
        )
        self.assertIsNotNone(m, ".row-input:hover CSS 必须存在")
        css = m.group(0)
        self.assertIn("#B5C9CE", css, "hover 边框用略深灰 #B5C9CE")

    def test_row_input_focus_state(self):
        """.role-batch-table .row-name:focus { 主色边框 + box-shadow }"""
        # 找含 .row-name:focus 的 CSS 块 (跨多行, 合并 .row-pv / .row-role)
        idx = INDEX_HTML.find('.role-batch-table .row-name:focus')
        self.assertNotEqual(idx, -1, ".role-batch-table .row-name:focus 规则必须存在")
        # 找 { 开始 (可能在多行后面)
        brace_start = INDEX_HTML.find('{', idx)
        self.assertNotEqual(brace_start, -1)
        # 平衡找 }
        depth = 1
        i = brace_start + 1
        while i < len(INDEX_HTML) and depth > 0:
            if INDEX_HTML[i] == '{': depth += 1
            elif INDEX_HTML[i] == '}': depth -= 1
            i += 1
        block = INDEX_HTML[idx:i]
        self.assertIn("#5AA4AE", block, "row-* focus 边框用主色 #5AA4AE")
        self.assertIn("box-shadow", block, "row-* focus 加 box-shadow")
        for cls in ['.row-name', '.row-pv', '.row-role']:
            self.assertIn(cls, block, f"{cls} 应在合并 focus 规则里")

    def test_row_input_invalid_state(self):
        """.row-input.invalid { border-color: #EF4444; background: #FEF2F2 }"""
        m = re.search(
            r'\.role-batch-table\s+\.row-input\.invalid[^{]*\{([^}]+)\}',
            INDEX_HTML, re.DOTALL
        )
        self.assertIsNotNone(m, ".row-input.invalid CSS 必须存在")
        css = m.group(0)
        self.assertIn("#EF4444", css, "invalid 边框红色")
        self.assertIn("#FEF2F2", css, "invalid 背景浅红")

    def test_row_del_focus_visible(self):
        """.row-del:focus-visible { outline: 2px solid #5AA4AE }"""
        m = re.search(
            r'\.role-batch-table\s+\.row-del:focus-visible\s*\{([^}]+)\}',
            INDEX_HTML, re.DOTALL
        )
        self.assertIsNotNone(m, ".row-del:focus-visible CSS 必须存在")
        css = m.group(0)
        self.assertIn("outline", css, "focus-visible 用 outline (键盘可访问)")


class TestPr61SubmitDisabledState(unittest.TestCase):
    """T8: submit 按钮 disabled 状态"""

    def test_submit_disabled_state(self):
        """#qaSubmit:disabled { opacity: 0.5; cursor: not-allowed }"""
        m = re.search(
            r'#qaSubmit:disabled\s*\{([^}]+)\}',
            INDEX_HTML, re.DOTALL
        )
        self.assertIsNotNone(m, "#qaSubmit:disabled CSS 必须存在 (0 行时 disabled)")
        css = m.group(0)
        self.assertIn("opacity", css, "disabled 用 opacity 弱化")
        self.assertIn("cursor: not-allowed", css, "disabled 用 not-allowed cursor")


class TestPr61EightPointGrid(unittest.TestCase):
    """T9: PR #57 8pt grid 严格 (2 倍数步进)"""

    def test_pv_stepper_grid_compliance(self):
        """所有 .pv-stepper 相关 padding/margin 2 倍数"""
        blocks = re.findall(
            r'\.pv-stepper[^{]*\{[^}]+\}',
            INDEX_HTML, re.DOTALL
        )
        self.assertGreater(len(blocks), 0)
        for block in blocks:
            paddings = re.findall(r'padding:\s*(\d+)px(?:\s+(\d+)px)?', block)
            margins = re.findall(r'margin:\s*(\d+)px(?:\s+(\d+)px)?', block)
            for nums in paddings + margins:
                for v in nums:
                    if not v: continue
                    v_int = int(v)
                    if v_int == 1: continue
                    self.assertEqual(v_int % 2, 0, f"CSS 间距 {v_int}px 不是 2 倍数")

    def test_row_input_grid_compliance(self):
        """.row-input padding 2 倍数 (4px 8px)"""
        m = re.search(
            r'\.role-batch-table\s+\.row-input\s*\{([^}]+)\}',
            INDEX_HTML, re.DOTALL
        )
        self.assertIsNotNone(m)
        css = m.group(0)
        paddings = re.findall(r'padding:\s*(\d+)px(?:\s+(\d+)px)?', css)
        for nums in paddings:
            for v in nums:
                if not v: continue
                v_int = int(v)
                self.assertEqual(v_int % 2, 0, f".row-input padding {v_int}px 不是 2 倍数")


class TestPr61Accessibility(unittest.TestCase):
    """T10: 键盘 accessibility + 视觉反馈"""

    def test_step_btn_focus_visible(self):
        """.pv-step-btn:focus-visible { outline: 2px solid 主色 }"""
        m = re.search(
            r'\.pv-stepper\s+\.pv-step-btn:focus-visible\s*\{([^}]+)\}',
            INDEX_HTML, re.DOTALL
        )
        self.assertIsNotNone(m, ".pv-step-btn:focus-visible CSS 必须存在")
        css = m.group(0)
        self.assertIn("outline", css)
        # focus 用主色 #5AA4AE
        self.assertIn("#5AA4AE", css)

    def test_step_btn_disabled_state(self):
        """.pv-step-btn:disabled { color: #D1D5DB; cursor: not-allowed }"""
        m = re.search(
            r'\.pv-stepper\s+\.pv-step-btn:disabled\s*\{([^}]+)\}',
            INDEX_HTML, re.DOTALL
        )
        self.assertIsNotNone(m, ".pv-step-btn:disabled CSS 必须存在")
        css = m.group(0)
        self.assertIn("cursor: not-allowed", css)

    def test_input_padding_right_22px(self):
        """.pv-stepper > input { padding-right: 22px } 给按钮留位"""
        m = re.search(
            r'\.pv-stepper\s+>\s*input\s*\{([^}]+)\}',
            INDEX_HTML, re.DOTALL
        )
        self.assertIsNotNone(m)
        self.assertIn("padding-right: 22px", m.group(0),
            "input padding-right 22px (给 20px 按钮 + 2px 间距)")


if __name__ == "__main__":
    unittest.main()
