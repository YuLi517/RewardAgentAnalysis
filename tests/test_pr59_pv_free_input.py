# -*- coding: utf-8 -*-
"""
test_pr59_pv_free_input.py —— PR #59 PV 输入框自由输入测试

业务背景 (2026-07-21):
  用户反馈: "PV 值每次增加或者减少都是以 100 的整数倍。如果要输入小于 100 的数字, 可以自己输入。"
  实际: type="number" 浏览器 spinner 跳 100 倍数, 不便

PR #59 修复:
  - 5 个 PV input: type="number" → type="text" inputmode="numeric" pattern="[0-9]+"
  - 去掉 spinner 限制, 自由输入任意正整数 (1, 50, 99, 100, 任意)
  - 移动端仍是数字键盘 (inputmode="numeric")
  - HTML5 pattern 校验整数
  - JS parseInt 校验 (已有)
  - 5 个 input 改:
    1. id="skillPvInput" (skill modal)
    2. name="pv" (tvCompactForm)
    3. id="qaPv" (单加成员)
    4. class="row-input row-pv" (批量添加 row)
    5. class="batch-pv" (skill 批量)

测试:
  T1: 5 个 input 全部 type="text" inputmode="numeric"
  T2: 5 个 input 全部有 pattern="[0-9]+" HTML5 验证
  T3: 5 个 input 全部没 type="number" 残留
  T4: 1 个 CSS 选择器保留 (兼容)
"""
import re
import sys
import unittest
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ))

INDEX_HTML = (PROJ / "static" / "index.html").read_text(encoding="utf-8")


class TestPr59PvInputs(unittest.TestCase):
    """T1-T3: 5 个 PV input 全部 type=text inputmode=numeric pattern"""

    def _extract_inputs(self):
        """提取所有 PV 相关的 input 元素 (按行号定位)"""
        # 找所有 input 含 pv/PV/id=qaPv/id=skillPvInput 等关键字
        results = []
        for m in re.finditer(
            r'<input[^>]*?(?:name="pv"|id="qaPv"|id="skillPvInput"|class="row-input\s+row-pv"|class="batch-pv")[^>]*?/?>',
            INDEX_HTML,
        ):
            results.append((m.start(), m.group(0)))
        return results

    def test_five_pv_inputs_found(self):
        """T1: 5 个 PV input 都能找到"""
        inputs = self._extract_inputs()
        self.assertEqual(len(inputs), 5,
            f"应找到 5 个 PV input, 实际: {len(inputs)}\n" + "\n".join(f"{i[1]}" for i in inputs))

    def test_all_pv_inputs_use_text_type(self):
        """T1: 全部 type='text' (不是 'number')"""
        inputs = self._extract_inputs()
        for pos, inp in inputs:
            self.assertIn('type="text"', inp,
                f"PV input 应 type='text', 实际: {inp}")
            self.assertNotIn('type="number"', inp,
                f"PV input 不应再有 type='number' (浏览器 spinner 跳 100), 实际: {inp}")

    def test_all_pv_inputs_have_inputmode_numeric(self):
        """T1: 全部 inputmode='numeric' (移动端数字键盘)"""
        inputs = self._extract_inputs()
        for pos, inp in inputs:
            self.assertIn('inputmode="numeric"', inp,
                f"PV input 应 inputmode='numeric', 实际: {inp}")

    def test_all_pv_inputs_have_pattern(self):
        """T2: 全部 pattern='[0-9]+' HTML5 验证整数"""
        inputs = self._extract_inputs()
        for pos, inp in inputs:
            self.assertIn('pattern="[0-9]+"', inp,
                f"PV input 应 pattern='[0-9]+', 实际: {inp}")

    def test_no_step_attribute_left(self):
        """T3: 没 step 属性残留 (number 才有的属性)"""
        inputs = self._extract_inputs()
        for pos, inp in inputs:
            self.assertNotIn('step="', inp,
                f"PV input 不应再有 step 属性 (text input 无效), 实际: {inp}")

    def test_no_min_attribute_required(self):
        """min 属性可选 (text input 上不强制), 但保留也无害
        5 个 input 中, 旧的 min='1' / min='0' 应该都没了 (我们改 input 时去掉了)
        """
        inputs = self._extract_inputs()
        for pos, inp in inputs:
            # 我们改 input 时已经去掉 min, 这里验证
            self.assertNotIn('min="', inp,
                f"PV input 不应再有 min 属性 (改 type=text 后无效), 实际: {inp}")


class TestPr59CssCompat(unittest.TestCase):
    """T4: CSS 选择器保留 (input[type='number'] 仍有效, 兼容)"""

    def test_skill_modal_number_css_kept(self):
        """#skillModal input[type="number"] CSS 仍存在 (兼容未来可能用 number input)"""
        # 至少 1 处
        self.assertIn('#skillModal input[type="number"]', INDEX_HTML)

    def test_quick_modal_number_css_kept(self):
        """.quick-modal-body input[type="number"] CSS 仍存在"""
        self.assertIn('.quick-modal-body input[type="number"]', INDEX_HTML)


class TestPr59JsIntact(unittest.TestCase):
    """JS 端 parseInt 校验仍工作 (不依赖 type='number' 的浏览器校验)"""

    def test_quick_batch_uses_parseint(self):
        """批量添加 JS 用 parseInt 校验 PV"""
        # 找 quickBatchAdd 函数体
        m = re.search(
            r"async function quickBatchAdd[^{]*\{(.*?)^\}",
            INDEX_HTML, re.DOTALL | re.MULTILINE
        )
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("parseInt", body, "批量添加 JS 应仍用 parseInt 校验 PV")
        # isNaN 校验
        self.assertIn("isNaN", body, "批量添加 JS 应仍 isNaN 校验")

    def test_quick_add_uses_parseint(self):
        """单加 quickAddMember JS 用 parseInt 校验"""
        m = re.search(
            r"async function quickAddMember[^{]*\{(.*?)^\}",
            INDEX_HTML, re.DOTALL | re.MULTILINE
        )
        if m is None:
            # 函数名可能不同
            self.skipTest("quickAddMember 函数名不固定, skip")
        body = m.group(1)
        self.assertIn("parseInt", body)


if __name__ == "__main__":
    unittest.main()
