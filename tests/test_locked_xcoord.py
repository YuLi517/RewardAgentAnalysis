# -*- coding: utf-8 -*-
r"""
test_locked_xcoord.py —— 业务规则「挂满 9 层」渐进解锁 (PR #18 + PR #25 修复)

业务规则 (用户拍板 2026-07-15):
    - 默认 effective_max_active_lines = 2 (L1+L2 激活, line 3+ 锁)
    - L1+L2 都「line 满」→ eff 升 4 (L3+L4 解锁)
    - L1-L4 都「line 满」→ eff 升 5 (L5 解锁)
    - 「line 满」定义: line 父下面 max_depth >= 9 (5 叉树 9 层 = depth 1..9, 不含 line 自己)
    - avail 占位**不算**真实成员 (跟 Node5.is_avail 逻辑一致)
    - 上限 max_lines (5 叉 → 5)

★ 2026-07-16 PR #25: 修 bug
  之前 (PR #14 c29f68a 引入): line 满 = 至少有 1 个真实成员
    → user 加 张1/张2 (line 1+2 各 1 真实成员) → 渲染层升 eff=4 → 误激活 line 3+4
  实际 (PR #18 业务规则): line 满 = line 父下面 max_depth >= 9
    → line 1+2 必须各挂 9 层真实成员才升 eff
  helper 改为构造「9 层子」表示 line 满
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import main  # noqa: E402


def _build_9_layer_chain(depth_left=10, name_prefix="chain"):
    """递归构造一个 9 层深的单链 (line 父 + 9 层子孙)
    depth_left=10: 返 9 层 (line 父下面 9 层子孙, 业务规则 line 满)
    depth_left=0: 返 None (叶子)

    ★ 用单链 1 叉 (5 叉会让 _build_9_layer_subtree 生成 5^9=1.95M 节点, 测试超时)
    ★ _max_depth_in_subtree 不依赖 5 叉还是 1 叉, 业务规则只算"line 父下面有几层"
    """
    if depth_left == 0:
        return None
    child = _build_9_layer_chain(depth_left - 1, f"{name_prefix}.1")
    return {
        "name": name_prefix,
        "distId": f"N-{name_prefix[:3]}{depth_left:02d}",
        "parentLineId": 0,
        "available": False,
        "avail": False,
        "pv": 100,
        "depth": 10 - depth_left,
        "maxLines": 5,
        "children": [child] if child else [],
    }


def _real_node_filled_9_layers(parent_line_id):
    """构造一个 line 满的 9 层子 (max_depth_in_subtree=9, 业务规则 line 满)
    用单链 9 层 (line 父 + 9 个 chain 节点 = 9 层子孙, 满足 line 满条件)
    """
    sub = _build_9_layer_chain(depth_left=10)
    return {
        "name": f"line{parent_line_id}-full9",
        "distId": f"N-L{parent_line_id:07d}",
        "parentLineId": parent_line_id,
        "available": False,
        "avail": False,
        "pv": 100,
        "maxLines": 5,
        "children": sub["children"],  # 9 层单链子
    }


def _real_node_empty(parent_line_id):
    """构造一个真实但没子 (max_depth=0) 的成员"""
    return {
        "name": f"line{parent_line_id}-empty",
        "distId": f"N-L{parent_line_id:07d}-e",
        "parentLineId": parent_line_id,
        "available": False,
        "avail": False,
        "pv": 100,
        "maxLines": 5,
        "children": [],
    }


def _avail_node(parent_line_id):
    """构造一个 avail 占位节点"""
    return {
        "name": "",
        "distId": None,
        "parentLineId": parent_line_id,
        "available": True,
        "avail": True,
        "pv": 0,
    }


def _parent_with_lines(line_states, max_lines=5):
    """构造 parent dict, line_states 描述每条线 (1..5) 的状态
    line_states[i] (i=0..4) 描述 line_id=i+1:
        - "empty"      → 该 line 有 1 个真实空子 (line 满条件不满足)
        - "full9"      → 该 line 有 1 个 9 层子 (line 满)
        - "avail"      → 该 line 有 1 个 avail 占位
        - None         → 该 line 没子
    """
    parent = {"name": "parent", "distId": "N-1234567", "maxLines": max_lines, "children": []}
    for i, state in enumerate(line_states):
        if state is None:
            continue
        line_id = i + 1
        if state == "empty":
            parent["children"].append(_real_node_empty(line_id))
        elif state == "full9":
            parent["children"].append(_real_node_filled_9_layers(line_id))
        elif state == "avail":
            parent["children"].append(_avail_node(line_id))
        else:
            raise ValueError(f"unknown state: {state!r}")
    return parent


class TestComputeEffectiveFromJson(unittest.TestCase):
    """_compute_effective_active_from_json 业务规则 (PR #25 修复版)"""

    def test_empty_parent_eff_is_2(self):
        """parent 完全没子 → eff=2 (默认)"""
        parent = {"name": "root", "distId": "N-1", "maxLines": 5, "children": []}
        self.assertEqual(main._compute_effective_active_from_json(parent), 2)

    def test_only_line_1_empty_eff_stays_2(self):
        """parent line 1 有 1 真实空子 (没满 9 层) → eff=2"""
        parent = _parent_with_lines(["empty", None, None, None, None])
        self.assertEqual(main._compute_effective_active_from_json(parent), 2)

    def test_only_line_2_empty_eff_stays_2(self):
        """parent line 2 有 1 真实空子 (没满 9 层) → eff=2"""
        parent = _parent_with_lines([None, "empty", None, None, None])
        self.assertEqual(main._compute_effective_active_from_json(parent), 2)

    def test_line_1_and_2_avail_eff_stays_2(self):
        """parent line 1+2 都是 avail (不真实) → eff=2"""
        parent = _parent_with_lines(["avail", "avail", "avail", "avail", "avail"])
        self.assertEqual(main._compute_effective_active_from_json(parent), 2)

    def test_line_1_empty_line_2_empty_eff_stays_2(self):
        """★ 关键回归测试: line 1+2 各 1 真实空子 (没满 9 层) → eff=2 (不能升 4)
        user 反馈 (2026-07-16): "我增加成员后, 王常军的 3 区和 4 区自动激活了.
                                规则是要等 1 区和 2 区的 9 层都排满了, 再激活"
        """
        parent = _parent_with_lines(["empty", "empty", "avail", "avail", "avail"])
        self.assertEqual(main._compute_effective_active_from_json(parent), 2)

    def test_line_1_and_2_full9_promotes_to_4(self):
        """parent line 1+2 都满 9 层 → eff=4 (升档)"""
        parent = _parent_with_lines(["full9", "full9", "avail", "avail", "avail"])
        self.assertEqual(main._compute_effective_active_from_json(parent), 4)

    def test_line_1_full9_line_2_empty_eff_stays_2(self):
        """parent line 1 满 9 层, line 2 没满 → eff=2 (不升档)"""
        parent = _parent_with_lines(["full9", "empty", "empty", "empty", "empty"])
        self.assertEqual(main._compute_effective_active_from_json(parent), 2)

    def test_line_1_full9_line_2_full9_line_3_empty_eff_4(self):
        """parent line 1+2 满 9 层, line 3 没满 → eff=4 (没到 5)"""
        parent = _parent_with_lines(["full9", "full9", "empty", None, None])
        self.assertEqual(main._compute_effective_active_from_json(parent), 4)

    def test_line_1_2_3_4_all_full9_promotes_to_5(self):
        """parent line 1+2+3+4 都满 9 层 → eff=5 (升到顶)"""
        parent = _parent_with_lines(["full9", "full9", "full9", "full9", "avail"])
        self.assertEqual(main._compute_effective_active_from_json(parent), 5)

    def test_line_1_5_full_eff_stays_5(self):
        """parent 1-5 都满 (line 5 也是真实满) → eff=5 (已到顶)"""
        parent = _parent_with_lines(["full9"] * 5)
        self.assertEqual(main._compute_effective_active_from_json(parent), 5)

    def test_max_lines_3_caps_eff(self):
        """max_lines=3 + 1+2+3+4 都满 9 层 → eff=3 (max_lines cap)"""
        parent = _parent_with_lines(["full9", "full9", "full9", "full9", None], max_lines=3)
        self.assertEqual(main._compute_effective_active_from_json(parent, max_lines=3), 3)

    def test_line_1_2_full9_line_3_4_avail_promotes_to_4(self):
        """parent line 1+2 满 9 层, 3+4 avail → eff=4 (avail 不阻止升档)"""
        parent = _parent_with_lines(["full9", "full9", "avail", "avail", None])
        self.assertEqual(main._compute_effective_active_from_json(parent), 4)

    def test_real_and_avail_mixed_same_line_not_full(self):
        """★ 关键回归测试: 同 line 上有 1 真实空子 + avail → line 仍没满 (max_depth=0) → eff=2
        之前 (PR #14) 这测试期望 eff=4 (因为 real_count > 0)
        现在 (PR #25) 期望 eff=2 (line 必须有 9 层子才算满)
        """
        parent = {
            "name": "p", "distId": "N-1", "maxLines": 5,
            "children": [
                _real_node_empty(1), _avail_node(1), _avail_node(1), _avail_node(1), _avail_node(1),
                _real_node_empty(2), _avail_node(2), _avail_node(2), _avail_node(2), _avail_node(2),
            ],
        }
        self.assertEqual(main._compute_effective_active_from_json(parent), 2)

    def test_real_and_avail_mixed_same_line_full9(self):
        """同 line 上有 1 真实 9 层子 + avail → line 满 → eff=4"""
        parent = {
            "name": "p", "distId": "N-1", "maxLines": 5,
            "children": [
                _real_node_filled_9_layers(1), _avail_node(1), _avail_node(1), _avail_node(1), _avail_node(1),
                _real_node_filled_9_layers(2), _avail_node(2), _avail_node(2), _avail_node(2), _avail_node(2),
            ],
        }
        self.assertEqual(main._compute_effective_active_from_json(parent), 4)

    def test_parentLineId_invalid_ignored(self):
        """子节点 parentLineId 解析失败 (None/字符串非数字) → 忽略, 不算那 line"""
        parent = {
            "name": "p", "distId": "N-1", "maxLines": 5,
            "children": [
                {"name": "t", "distId": "N-2", "parentLineId": "garbage", "available": False, "pv": 100,
                 "maxLines": 5, "children": []},
                _real_node_filled_9_layers(2),  # 只有 line 2 满 9 层
            ],
        }
        self.assertEqual(main._compute_effective_active_from_json(parent), 2)

    def test_default_max_lines_5(self):
        """max_lines 默认 5"""
        parent = _parent_with_lines(["full9"] * 5)
        self.assertEqual(main._compute_effective_active_from_json(parent, max_lines=5), 5)


class TestRenderTreeXCoord(unittest.TestCase):
    """集成测试: 用 _build_tree_render_html 渲染, 验证 eff 升降档后 xcoord 行为

    不依赖 json/Tree_empty_5_3.json 的具体状态 (gitignored, 经常变),
    直接构造内存树测渲染。
    """

    def _build_parent_5ary_tree(self, fill_lines_1_2=False, lines_full9=False):
        """构造一个 5 叉树 fixture, root 下按业务填充

        fill_lines_1_2=True + lines_full9=True → line 1, 2 是 9 层子 (升 eff=4)
        fill_lines_1_2=True + lines_full9=False → line 1, 2 是真实但没子 (eff=2)
        fill_lines_1_2=False → line 1-5 全是 avail
        """
        if fill_lines_1_2:
            if lines_full9:
                children = [
                    {**_real_node_filled_9_layers(1), "name": "张三", "distId": "N-5637591",
                     "depth": 0, "maxLines": 5},
                    {**_real_node_filled_9_layers(2), "name": "张四", "distId": "N-5637592",
                     "depth": 0, "maxLines": 5},
                ]
            else:
                children = [
                    {**_real_node_empty(1), "name": "张三", "distId": "N-5637591",
                     "depth": 0, "maxLines": 5,
                     "children": [_avail_node(i) for i in range(1, 6)]},
                    {**_real_node_empty(2), "name": "张四", "distId": "N-5637592",
                     "depth": 0, "maxLines": 5,
                     "children": [_avail_node(i) for i in range(1, 6)]},
                ]
        else:
            children = [_avail_node(i) for i in range(1, 6)]
        return {
            "name": "root", "distId": "N-1", "depth": 0, "maxLines": 5,
            "pv": 0, "available": False, "children": children,
        }

    def test_root_eff_2_no_l1_xcoord_for_line_3_4_5(self):
        """root 全 avail (eff=2) → L1 line 3, 4, 5 不显示 xcoord"""
        raw = self._build_parent_5ary_tree(fill_lines_1_2=False)
        main._reset_global_lv_k_n_inc()
        html = main._build_tree_render_html(raw, highlight_map={})
        self.assertIsInstance(html, str)
        self.assertIn("tv-slot", html)

    def test_root_eff_2_when_l1_l2_empty(self):
        """★ 关键回归: root line 1+2 各 1 真实空子 (eff=2) → 渲染应该 OK"""
        raw = self._build_parent_5ary_tree(fill_lines_1_2=True, lines_full9=False)
        main._reset_global_lv_k_n_inc()
        html = main._build_tree_render_html(raw, highlight_map={})
        self.assertIn("张三", html)
        self.assertIn("张四", html)

    def test_root_eff_4_when_l1_l2_full9(self):
        """root line 1+2 都满 9 层 (eff=4) → 渲染应该 OK"""
        raw = self._build_parent_5ary_tree(fill_lines_1_2=True, lines_full9=True)
        main._reset_global_lv_k_n_inc()
        html = main._build_tree_render_html(raw, highlight_map={})
        self.assertIn("张三", html)
        self.assertIn("张四", html)
        self.assertGreater(html.count("tv-slot"), 0)


if __name__ == "__main__":
    unittest.main()
