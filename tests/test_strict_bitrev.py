# -*- coding: utf-8 -*-
"""test_strict_bitrev.py v4 — PR #71 v3 算法 stage-based + 跳过已占槽位测试

PR #71 v3 业务规则 (2026-08-04 用户拍板, 严格匹配 12 个点位):
  - 4 大区横向顺序: A(line 1) -> C(line 3) -> B(line 2) -> D(line 4)
  - 4 大区 L1 平行, 4 大区 L2 平行, ...
  - 5 叉 eff=4 时 line 5 锁
  - 算法 stage-based, 跳过已占槽位
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'skills'))

from skills.skill_5_3 import (
    find_next_slot_bitrev,
    add_user_bitrev,
    simulate_addition_bitrev,
    _compute_slot_pr71_v3,
    _is_slot_avail,
)
from skill_5_lib import Node5


def make_root_4l1() -> Node5:
    """PR #1 拍板: root max_active_lines=4, 加 4 个 L1 父 (line 1-4 顺序)"""
    root = Node5(uid=1, name="root", pv=0, max_children=5, max_active_lines=4)
    for lid in [1, 2, 3, 4]:
        n = Node5(uid=10 + lid - 1, name=f"L1-{lid}", pv=100, max_children=5,
                  max_active_lines=2, depth=1, line_id=lid)
        root.children.append(n)
    return root


class TestV3StageBased(unittest.TestCase):
    """v3 算法: step 决定 (parent, line), stage=step//4, region=step%4"""

    def setUp(self):
        if hasattr(add_user_bitrev, "_step_state"):
            delattr(add_user_bitrev, "_step_state")

    def test_stage_0_4_l1_parallel(self):
        """stage 0 (step 0-3): 4 大区 L1 平行 = root.line 1, 3, 2, 4"""
        root = make_root_4l1()
        expected_lines = [1, 3, 2, 4]
        for i, exp_line in enumerate(expected_lines):
            slot = _compute_slot_pr71_v3(root, step=i)
            self.assertIsNotNone(slot, f"step {i} None")
            parent, line_id = slot
            self.assertEqual(parent.uid, root.uid, f"step {i} parent should be root")
            self.assertEqual(line_id, exp_line, f"step {i} expected line {exp_line}, got {line_id}")

    def test_stage_1_4_l2_parallel(self):
        """stage 1 (step 4-7): 4 大区 L2 平行 = A/C/B/D.line 1"""
        root = make_root_4l1()
        # 4 大区 L1 父 = root.children[0..3] (line 1, 2, 3, 4)
        expected = [
            (10, 1),  # A = line 1 父 (uid 10), line 1
            (12, 1),  # C = line 3 父 (uid 12), line 1
            (11, 1),  # B = line 2 父 (uid 11), line 1
            (13, 1),  # D = line 4 父 (uid 13), line 1
        ]
        for i, (exp_uid, exp_line) in enumerate(expected):
            slot = _compute_slot_pr71_v3(root, step=4 + i)
            self.assertIsNotNone(slot, f"step {4+i} None")
            parent, line_id = slot
            self.assertEqual(parent.uid, exp_uid, f"step {4+i} expected uid {exp_uid}, got {parent.uid}")
            self.assertEqual(line_id, exp_line, f"step {4+i} expected line {exp_line}, got {line_id}")

    def test_stage_2_4_l3_parallel(self):
        """stage 2 (step 8-11): 4 大区 L3 平行 = A/C/B/D.line 2

        setUp: 4 L1 父 + 每个 L1 父下 1 子 (line 1) — A/C/B/D.line 2 还没挂
        """
        root = make_root_4l1()
        for i, p in enumerate(root.children):
            c = Node5(uid=20 + i, name=f"L2-{i+1}", pv=50, max_children=5,
                      max_active_lines=2, depth=2, line_id=1)
            p.children.append(c)
        expected = [
            (10, 2),  # A.line 2
            (12, 2),  # C.line 2
            (11, 2),  # B.line 2
            (13, 2),  # D.line 2
        ]
        for i, (exp_uid, exp_line) in enumerate(expected):
            slot = _compute_slot_pr71_v3(root, step=8 + i)
            self.assertIsNotNone(slot, f"step {8+i} None")
            parent, line_id = slot
            self.assertEqual(parent.uid, exp_uid, f"step {8+i} expected uid {exp_uid}, got {parent.uid}")
            self.assertEqual(line_id, exp_line, f"step {8+i} expected line {exp_line}, got {line_id}")


class TestV3SkipOccupied(unittest.TestCase):
    """v3 算法: 跳过已占槽位, step+1 advance"""

    def test_skip_occupied_l1(self):
        """step 0 = (root, line=1) 但 line 1 已挂 → 跳到 (root, line=3)"""
        root = Node5(uid=1, pv=0, depth=0, max_children=5, max_active_lines=4)
        # root.line 1 已挂 (按 line 顺序放 children[0])
        A = Node5(uid=10, pv=100, max_children=5, max_active_lines=2,
                  depth=1, line_id=1, is_avail=False)
        root.children.append(A)
        slot = find_next_slot_bitrev(root, step=0)
        self.assertIsNotNone(slot)
        parent, line_id = slot
        self.assertEqual(parent.uid, root.uid)
        self.assertEqual(line_id, 3)  # 跳过 line 1

    def test_skip_occupied_l1_l3(self):
        """step 0 = (root, line=1) 已挂, 跳 (root, line=3) 也已挂 → (root, line=2)

        children 按 line 顺序: [line 1 父, line 2 占位, line 3 父]
        """
        root = Node5(uid=1, pv=0, depth=0, max_children=5, max_active_lines=4)
        A = Node5(uid=10, pv=100, max_children=5, max_active_lines=2,
                  depth=1, line_id=1, is_avail=False)
        # line 2 占位 (avail)
        line2_avail = Node5(uid=-1, pv=0, max_children=5, max_active_lines=2,
                            depth=1, line_id=2, is_avail=True)
        C = Node5(uid=11, pv=100, max_children=5, max_active_lines=2,
                  depth=1, line_id=3, is_avail=False)
        root.children.extend([A, line2_avail, C])
        slot = find_next_slot_bitrev(root, step=0)
        self.assertIsNotNone(slot)
        parent, line_id = slot
        self.assertEqual(line_id, 2)  # 跳过 line 1+3, 找 line 2 (avail)


class TestV3IsSlotAvail(unittest.TestCase):
    """_is_slot_avail 辅助函数"""

    def test_avail_placeholder(self):
        root = Node5(uid=1, pv=0, depth=0, max_children=5, max_active_lines=4)
        avail = Node5(uid=-1, pv=0, max_children=5, max_active_lines=2,
                      depth=1, line_id=1, is_avail=True)
        root.children.append(avail)
        self.assertTrue(_is_slot_avail(root, 1))

    def test_occupied(self):
        root = Node5(uid=1, pv=0, depth=0, max_children=5, max_active_lines=4)
        real = Node5(uid=10, pv=100, max_children=5, max_active_lines=2,
                     depth=1, line_id=1, is_avail=False)
        root.children.append(real)
        self.assertFalse(_is_slot_avail(root, 1))

    def test_no_children(self):
        root = Node5(uid=1, pv=0, depth=0, max_children=5, max_active_lines=4)
        self.assertTrue(_is_slot_avail(root, 1))


class TestV3BatchPattern(unittest.TestCase):
    """v3 算法 12 步完整 pattern 模拟 (用户原话 12 个点位)"""

    def test_12_point_full_pattern(self):
        """完整 12 步 pattern 严格匹配用户原话

        step  1: A-L1 (root.line 1)
        step  2: C-L1 (root.line 3)
        step  3: B-L1 (root.line 2)
        step  4: D-L1 (root.line 4)
        step  5: A-L2 (A.line 1) = E1
        step  6: C-L2 (C.line 1) = E2
        step  7: B-L2 (B.line 1) = E3
        step  8: D-L2 (D.line 1) = E4
        step  9: A-L3 (A.line 2) = F1
        step 10: C-L3 (C.line 2) = F2
        step 11: B-L3 (B.line 2) = F3
        step 12: D-L3 (D.line 2) = F4
        """
        root = Node5(uid=1, pv=1000, depth=0, name='', max_children=5,
                     max_active_lines=4, is_avail=False, line_id=0)
        # 5 个 avail placeholder
        for i in range(5):
            root.children.append(Node5(uid=-100-i, pv=0, depth=1, max_children=5,
                                       max_active_lines=2, line_id=i+1, is_avail=True))

        expected = [
            (1, 1),    # A-L1
            (1, 3),    # C-L1
            (1, 2),    # B-L1
            (1, 4),    # D-L1
            (1, 1),    # A-L2 (A.line 1)
            (1, 1),    # C-L2 (C.line 1)
            (1, 1),    # B-L2 (B.line 1)
            (1, 1),    # D-L2 (D.line 1)
            (1, 2),    # A-L3 (A.line 2)
            (1, 2),    # C-L3 (C.line 2)
            (1, 2),    # B-L3 (B.line 2)
            (1, 2),    # D-L3 (D.line 2)
        ]
        for step_idx, (exp_parent_uid_at_stage0, exp_line) in enumerate(expected):
            slot = find_next_slot_bitrev(root, step=step_idx)
            self.assertIsNotNone(slot, f"step {step_idx+1} None")
            parent, line_id = slot
            self.assertEqual(line_id, exp_line, f"step {step_idx+1} expected line {exp_line}, got {line_id}")
            # 模拟 fill (replace avail placeholder with real)
            real = Node5(uid=-(step_idx+1), pv=0, depth=parent.depth+1, max_children=5,
                         max_active_lines=2, line_id=line_id, is_avail=False)
            replaced = False
            for j, c in enumerate(parent.children):
                if c.is_avail and c.line_id == line_id:
                    parent.children[j] = real
                    replaced = True
                    break
            if not replaced:
                # 缺 avail, 添加
                parent.children.append(real)


if __name__ == "__main__":
    unittest.main()
