# -*- coding: utf-8 -*-
"""
test_pr60_pv_stepper.py —— PR #60 PV stepper 按钮 (+/- 100) 测试

业务背景 (2026-07-21):
  PR #59 改 type=text + inputmode=numeric, 自由输入整数 (1, 50, 99, 任意)
  用户反馈 (PR #60): "PV值旁边怎么没有上下点击的按钮了？之前的按钮还是需要,
  只是每次点击加100或者减少100 (100整数倍)"

PR #60 修复:
  - 给 5 个 PV input 加自定义 +/- 按钮 (步进 100)
  - 按钮位置: input 右侧, 上下叠 (跟 native number spinner 一样)
  - input 保持 type="text" (PR #59 改动) — 仍可自由输入任意整数
  - 按钮 click: 读 input 当前值 ± 100, 触发 input 事件
  - 5 个位置:
    1. id="skillPvInput" (skill modal)
    2. name="pv" (tvCompactForm)
    3. id="qaPv" (单加成员)
    4. class="row-input row-pv" (批量添加 row)
    5. class="batch-pv" (skill 批量)

测试:
  T1: 5 个 PV input 都在 .pv-stepper wrapper 内
  T2: 每个 stepper 含 + / - 按钮 (data-step=100 / -100)
  T3: 按钮位置 (CSS): 右侧内嵌, 上下叠
  T4: JS _bindPvStepperEvents 初始化逻辑存在
  T5: 按钮 click 事件逻辑正确 (读 input + step, 写回, 触发 input)
  T6: input 仍是 type="text" (PR #59 兼容)
"""
import re
import sys
import unittest
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ))

INDEX_HTML = (PROJ / "static" / "index.html").read_text(encoding="utf-8")


def _find_pv_inputs():
    """找所有 PV input 上下文, 返回 (selector_hint, full_match) 列表"""
    results = []
    for m in re.finditer(
        r'<input[^>]*?(?:name="pv"|id="qaPv"|id="skillPvInput"|class="row-input\s+row-pv"|class="batch-pv")[^>]*?/?>',
        INDEX_HTML,
    ):
        results.append((m.start(), m.group(0)))
    return results


class TestPr60PvStepperStructure(unittest.TestCase):
    """T1+T2: 5 个 PV input 都在 .pv-stepper wrapper 内, 含 + / - 按钮"""

    def test_five_pv_inputs_in_stepper(self):
        """5 个 PV input 都包在 .pv-stepper 内"""
        # 用非贪婪 + 平衡: 找 .pv-stepper 开始, 然后计数 span, 找到平衡
        # 简化: 数 .pv-stepper 出现次数 (开标签), 跟 PV input 数 (5) 匹配
        # batch-pv 的 stepper 是字符串拼接, 不算 HTML 节点, 我们用 batch-pv 出现次数验证
        n_stepper = INDEX_HTML.count('<span class="pv-stepper">')
        n_pv_in_stepper = 0
        for hint in ['id="skillPvInput"', 'name="pv"', 'id="qaPv"', 'class="row-input row-pv"', 'class="batch-pv"']:
            # 找包含这个 hint 的 stepper 数量
            for m in re.finditer(
                r'<span\s+class="pv-stepper">.*?(?:id="skillPvInput"|name="pv"\s+inputmode|id="qaPv"|class="row-input\s+row-pv"|class="batch-pv")',
                INDEX_HTML, re.DOTALL,
            ):
                if hint in m.group(0):
                    n_pv_in_stepper += 1
                    break
        # 5 个 PV input 都应该在 stepper 内
        self.assertEqual(n_pv_in_stepper, 5,
            f"应 5 个 PV input 都在 .pv-stepper 内, 实际: {n_pv_in_stepper}")
        # 总 stepper 数量 ≥ 5
        self.assertGreaterEqual(n_stepper, 5,
            f"应至少 5 个 .pv-stepper 标签, 实际: {n_stepper}")

    def test_each_stepper_has_plus_minus_buttons(self):
        """每个 stepper 含 + 和 - 按钮"""
        # 找所有 stepper (不依赖 regex 平衡)
        # 简化: 找 stepper 块 — 用 "<span class=\"pv-stepper\">" 开始, 找对应的 "−</button>" 和 "+</button>"
        stepper_count = INDEX_HTML.count('<span class="pv-stepper">')
        plus_count = INDEX_HTML.count('class="pv-step-btn plus" data-step="100"')
        minus_count = INDEX_HTML.count('class="pv-step-btn minus" data-step="-100"')
        # 至少有 5 个 stepper, 每个含 + 和 -, 加起来 = stepper 数量
        self.assertEqual(plus_count, stepper_count,
            f"加按钮数应 = stepper 数 ({stepper_count}), 实际: {plus_count}")
        self.assertEqual(minus_count, stepper_count,
            f"减按钮数应 = stepper 数 ({stepper_count}), 实际: {minus_count}")
        self.assertGreaterEqual(stepper_count, 5)

    def test_button_text_unicode(self):
        """按钮文本用 unicode + / − (不依赖 SVG / icon font)"""
        # 检查 + 按钮文本
        self.assertIn(">+</button>", INDEX_HTML, "加按钮应含 + 字符")
        # 检查 − 按钮文本 (unicode U+2212)
        self.assertIn("−</button>", INDEX_HTML, "减按钮应含 − 字符 (unicode U+2212)")


class TestPr60PvStepperCss(unittest.TestCase):
    """T3: CSS .pv-stepper + 按钮位置"""

    def test_stepper_position_relative(self):
        """CSS .pv-stepper { position: relative; display: inline-block }"""
        # ★ PR #61: 不再带 .tree-view scope (modal/form 也要生效)
        m = re.search(r'\.pv-stepper\s*\{[^}]+\}', INDEX_HTML, re.DOTALL)
        self.assertIsNotNone(m, ".pv-stepper CSS 必须存在 (通用, 不带 .tree-view 前缀)")
        css = m.group(0)
        self.assertIn("position: relative", css)
        self.assertIn("display: inline-block", css)

    def test_step_btn_absolute_positioned(self):
        """CSS .pv-step-btn { position: absolute } 按钮绝对定位"""
        m = re.search(r'\.pv-stepper\s+\.pv-step-btn\s*\{[^}]+\}', INDEX_HTML, re.DOTALL)
        self.assertIsNotNone(m, ".pv-step-btn CSS 必须存在 (通用)")
        css = m.group(0)
        self.assertIn("position: absolute", css)
        self.assertIn("right: 1px", css)

    def test_minus_and_plus_height_50_percent(self):
        """按钮高度 = input 高度 / 2 (上下叠) — 基础 .pv-step-btn 设 height: 50%
        ★ PR #62: 互换 +/- 位置 (+ 上, - 下)
        """
        m_base = re.search(
            r'\.pv-stepper\s+\.pv-step-btn\s*\{([^}]+)\}',
            INDEX_HTML, re.DOTALL
        )
        self.assertIsNotNone(m_base, ".pv-stepper .pv-step-btn 基础 CSS 必须存在")
        self.assertIn("height: 50%", m_base.group(0), "基础按钮 height: 50%")
        m_minus = re.search(
            r'\.pv-stepper\s+\.pv-step-btn\.minus\s*\{([^}]+)\}',
            INDEX_HTML, re.DOTALL
        )
        m_plus = re.search(
            r'\.pv-stepper\s+\.pv-step-btn\.plus\s*\{([^}]+)\}',
            INDEX_HTML, re.DOTALL
        )
        self.assertIsNotNone(m_minus, ".pv-stepper .pv-step-btn.minus CSS 必须存在")
        self.assertIsNotNone(m_plus, ".pv-stepper .pv-step-btn.plus CSS 必须存在")
        # ★ PR #62: + 在上 (top: 1px), - 在下 (bottom: 1px)
        self.assertIn("top: 1px", m_plus.group(0), "PR #62: + 在上 (top: 1px)")
        self.assertIn("bottom: 1px", m_minus.group(0), "PR #62: - 在下 (bottom: 1px)")

    def test_8pt_grid_compliance(self):
        """CSS 间距 2 倍数步进 (PR #57 教训一致)"""
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


class TestPr60PvStepperJs(unittest.TestCase):
    """T4+T5: JS _bindPvStepperEvents 逻辑"""

    def test_bind_function_exists(self):
        """_bindPvStepperEvents 函数存在"""
        self.assertIn("function _bindPvStepperEvents", INDEX_HTML)

    def test_bind_function_uses_dataset_bound(self):
        """_bindPvStepperEvents 用 dataset.bound 防止重复绑定"""
        self.assertIn("dataset.bound", INDEX_HTML,
            "应检查 dataset.bound 防止重复绑定")

    def test_click_handler_reads_input_and_step(self):
        """click 事件读 input 当前值 + data-step"""
        # 找 click handler 函数体 — 用 {} 平衡
        m = re.search(
            r"function _bindPvStepperEvents\s*\(\s*\)\s*\{",
            INDEX_HTML
        )
        self.assertIsNotNone(m)
        # 从 m.end() 开始计数 {} 找函数体结束
        start = m.end()
        depth = 1
        i = start
        while i < len(INDEX_HTML) and depth > 0:
            if INDEX_HTML[i] == '{': depth += 1
            elif INDEX_HTML[i] == '}': depth -= 1
            i += 1
        body = INDEX_HTML[start:i-1]
        self.assertIn("parseInt(input.value", body)
        self.assertIn("dataset.step", body, "JS 用 btn.dataset.step 读 data-step 属性")
        self.assertIn("dispatchEvent", body, "应触发 input 事件让监听者知道")

    def test_min_value_zero_clamp(self):
        """减法不能 < 0 (clamp)"""
        m = re.search(
            r"function _bindPvStepperEvents\(\)\s*\{(.*?)^\}",
            INDEX_HTML, re.DOTALL | re.MULTILINE
        )
        body = m.group(1)
        self.assertIn("next < 0", body, "应 clamp 到 0 (PV 业务 ≥ 0)")

    def test_mutation_observer_for_dynamic_steppers(self):
        """动态添加的 stepper (MutationObserver) 也绑"""
        self.assertIn("MutationObserver", INDEX_HTML)
        self.assertIn("_bindPvStepperEvents", INDEX_HTML)


class TestPr60PvInputStillText(unittest.TestCase):
    """T6: 兼容 PR #59 — input 仍是 type='text' inputmode='numeric'"""

    def test_inputs_still_type_text(self):
        """5 个 PV input 仍是 type='text' (PR #59 兼容)"""
        inputs = _find_pv_inputs()
        self.assertEqual(len(inputs), 5, f"应 5 个 PV input, 实际: {len(inputs)}")
        for pos, inp in inputs:
            self.assertIn('type="text"', inp, f"PV input 应 type='text', 实际: {inp}")
            self.assertIn('inputmode="numeric"', inp, f"应 inputmode='numeric', 实际: {inp}")
            self.assertIn('pattern="[0-9]+"', inp, f"应 pattern='[0-9]+', 实际: {inp}")


if __name__ == "__main__":
    unittest.main()
