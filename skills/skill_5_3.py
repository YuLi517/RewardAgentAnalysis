# -*- coding: utf-8 -*-
r"""
Skill 5_3 · 按「按位反转 (base-5 digit reversal)」顺序添加新成员 + 5 叉网体实时佣金计算
========================================================================================

[业务背景]
- skill_5_1 (列优先 BFS) 在 2026-07-11 v4 改成了「只挂奇数线 (L1/L3/L5)」,业务 commission 永远为 0
- skill_5_2 (配对优先 BFS) 改成「优先凑 L1+L2 配对」,commission 实际触发
- skill_5_3 (本 skill) 改路线: **完全沿用 visio 树型图的「按位反转」落位规律** —
  从 TreeGenerate 目录 verify_l6.py 反推出来的 L6 前 8 节点
  `64, 96, 80, 112, 72, 104, 88, 120` 正好等于 `bit_reverse(0..7, 6) + 64`。
  对 5 叉树 = base-5 digit reversal: 已知新成员在 L+1 阶段的序号 i (0..5^L-1),
  反转 i 的 base-5 表示 (L 位),得到该新成员在 "L 层父节点 × 5 列" 共 5^L 个槽位里的
  实际槽位编号 = (父 BFS 索引 × 5 + col)。

[与 skill_5_1 / skill_5_2 的关键区别]

| 维度 | skill_5_1 (列优先 BFS) | skill_5_2 (配对优先 BFS) | skill_5_3 (按位反转, 本) |
|------|----------------------|--------------------------|------------------------------|
| 落位算法 | 列优先:col0→col1→…→col4 | 凑 L1+L2 配对优先 | **base-5 digit reversal** |
| 5 列都挂? | ❌ v4 起只挂奇数线 (L1/L3/L5) | ❌ 只挂 L1+L2 凑配对 | ✅ **全员 5 列都挂** |
| 业务触发 commission? | ❌ 永远 0 (缺右叉) | ✅ L1+L2 都挂时触发 | ✅ 满 5 列时整体参与 |
| 树型图位置 | 列优先(从左到右) | L1+L2 优先 | **按位反转** (FFT/iDFT 风格) |
| 来源沉淀 | user_add_order_rule.md 2 叉版 | skill_5_1 配套补全 | TreeGenerate visio 树型图反推 |

[核心算法: 按位反转 (base-5 digit reversal) 找下一个 slot]

    L+1 阶段新增 5^L 个新成员, 在 L 层父节点 (5^(L-1) 个, 按 BFS 序) × 5 列 = 5^L 个槽位
    按 i=0..5^L-1 顺序, 第 i 个新成员填到第 bit_reverse_base5(i, L) 个槽位

    bit_reverse_base5(n, L) 算法:
        把 n 写成 L 位的 base-5 表示 (n = d0 + d1*5 + d2*25 + ... + d_{L-1}*5^(L-1))
        把 d0, d1, ..., d_{L-1} 倒序:
            r = d_{L-1} + d_{L-2}*5 + d_{L-3}*25 + ... + d_0*5^(L-1)
        = (n 各个 base-5 digit 倒序排列后转回 10 进制)

    实际使用:
        slot_idx = bit_reverse_base5(i, L)
        parent_bfs_idx = slot_idx // 5
        col = slot_idx % 5
        parent = BFS 序里的第 parent_bfs_idx 个 L 层父节点
        新成员 = parent 的第 col 个孩子 (line_id = col+1)

    直观举例 (5 叉树):
        L=1 阶段 (5^1=5 个新成员, root 下 5 列):
            i=0 (0)  → rev 0  → slot 0   → root col 0  → 新成员挂 root L1
            i=1 (1)  → rev 1  → slot 1   → root col 1  → 新成员挂 root L2
            i=2 (2)  → rev 2  → slot 2   → root col 2  → 新成员挂 root L3
            i=3 (3)  → rev 3  → slot 3   → root col 3  → 新成员挂 root L4
            i=4 (4)  → rev 4  → slot 4   → root col 4  → 新成员挂 root L5
            顺序 = L1, L2, L3, L4, L5 (1 位反转 = 自身, 跟「列优先 BFS」一致)

        L=2 阶段 (5^2=25 个新成员, 5 个 L1 父 × 5 列 = 25 槽):
            i=0 (00) → rev 00 → slot 0   → 父[0] col 0
            i=1 (01) → rev 10 → slot 5   → 父[1] col 0
            i=2 (02) → rev 20 → slot 10  → 父[2] col 0
            i=3 (03) → rev 30 → slot 15  → 父[3] col 0
            i=4 (04) → rev 40 → slot 20  → 父[4] col 0
            i=5 (10) → rev 01 → slot 1   → 父[0] col 1
            i=6 (11) → rev 11 → slot 6   → 父[1] col 1
            i=7 (12) → rev 21 → slot 11  → 父[2] col 1
            ...
            i=24 (44) → rev 44 → slot 24 → 父[4] col 4
            顺序: 先全部 col 0 (5 个父), 再 col 1 (5 个父), ... 再 col 4
                  (L=2, 2 位反转 = 自身, 也跟「列优先 BFS」一致)

        L=3 阶段 (5^3=125 个新成员, 25 个 L2 父 × 5 列 = 125 槽):
            i=0 (000) → rev 000 → slot 0   → 父[0] col 0
            i=1 (001) → rev 100 → slot 25  → 父[5] col 0
            i=2 (002) → rev 200 → slot 50  → 父[10] col 0
            i=3 (003) → rev 300 → slot 75  → 父[15] col 0
            i=4 (004) → rev 400 → slot 100 → 父[20] col 0
            i=5 (010) → rev 010 → slot 5   → 父[1] col 0
            i=6 (011) → rev 110 → slot 30  → 父[6] col 0
            ...
            顺序: 不是简单「列优先 BFS」! 而是 base-5 位倒序遍历
            跟 TreeGenerate visio 树型图反推的位反转规律一致

[与 2 叉版 (verify_l6.py) 的对照验证]

    2 叉 L3 阶段 (2^2=4 新成员, 2 个 L1 父 × 2 列):
        i=0 (00) → rev 00 → slot 0 → 父[0] col 0 = 节点 4 ✓ (tree-structure.md 验证)
        i=1 (01) → rev 10 → slot 2 → 父[1] col 0 = 节点 5 ✓
        i=2 (10) → rev 01 → slot 1 → 父[0] col 1 = 节点 6 ✓
        i=3 (11) → rev 11 → slot 3 → 父[1] col 1 = 节点 7 ✓
    完美命中 tree-structure.md 的 4, 5, 6, 7!

[API 速览]
    find_next_slot_bitrev(tree, step) -> Optional[Tuple[Node5, int]]
        按 base-5 digit reversal 找下一个挂载点的 (父节点, line_id);
        树满 / 找不到 active 槽位则返回 None。
    add_user_bitrev(tree, pv, name='', code='') -> Optional[Node5]
        在 tree 上挂一个 PV=pv 的新成员; 成功返回新节点, 失败返回 None。
    simulate_addition_bitrev(tree, pv_list, names=None, codes=None,
                             include_pairing=True) -> List[dict]
        模拟多次挂入, 每一步记录 uid / parent_uid / 父节点挂前后 basic /
        整树 basic&pairing 增量 / 总利润 / lift_pct, 返回历史列表。
    run_demo_bitrev(n_members, pv_per_member, seed_pv)
        CLI 演示入口。

[依赖]
- skill_5_lib.py(同目录内): Node5 + 业务计算函数, 直接 `from skill_5_lib import ...`
- skill_5_1.py(同目录内): _bfs_all / _snapshot_profit / AdditionStep / _ancestor_chain
  / load_from_jstree_* / history_to_json 等原语直接复用, 不重写
- Python 3.7+ (dataclass)
- 无第三方依赖
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 复用 skill_5_lib + skill_5_helpers 的所有节点/计算原语(零重复实现)
# ---------------------------------------------------------------------------
# 2026-07-13: skill_5_1 / skill_5_2 已下线,原来从 skill_5_1 复用的 helper
# (_bfs_all / _snapshot_profit / AdditionStep / _ancestor_chain /
#  load_from_jstree_dict / load_tree_from_jstree_file / history_to_json)
# 抽到 skill_5_helpers.py 里。这里直接 import 新模块。
from skill_5_lib import (  # noqa: E402
    DEFAULT_MAX_CHILDREN,
    PAIRING_RATIOS,
    COMMISSION_RATE,
    ZONE_CAP,
    Node5,
    basic_commission,
    cap,
    clone,
    max_subtree_uid,
    pairing_bonus,
    subtree_pv,
    total_basic,
    total_profit,
)

from skill_5_helpers import (  # noqa: E402
    AdditionStep,
    _bfs_all,
    _snapshot_profit,
    _ancestor_chain,
    load_from_jstree_dict,
    load_tree_from_jstree_file,
    history_to_json,
)


# ===========================================================================
# 1. 核心: base-5 digit reversal 工具
# ===========================================================================

def _bit_reverse_base_b(n: int, bits: int, base: int = 5) -> int:
    """对 n 做 base-进制的 digit reversal, 共 bits 位

    把 n 写成 bits 位的 base 进制表示 (n = d0 + d1*base + d2*base^2 + ... + d_{bits-1}*base^(bits-1))
    把 digits 倒序: r = d_{bits-1} + d_{bits-2}*base + ... + d_0*base^(bits-1)

    Parameters
    ----------
    n    : int, 待反转的非负整数
    bits : int, 位数 (n 必须 < base^bits)
    base : int, 进制 (5 叉树用 5; 2 叉树用 2 复现 verify_l6 行为)

    Returns
    -------
    int, 反转后的非负整数 (范围 0..base^bits-1)

    Examples
    --------
    >>> _bit_reverse_base_b(0, 3, base=5)   # 000 → 000
    0
    >>> _bit_reverse_base_b(1, 3, base=5)   # 001 → 100 = 25
    25
    >>> _bit_reverse_base_b(5, 3, base=5)   # 010 → 010 = 5
    5
    >>> _bit_reverse_base_b(24, 3, base=5)  # 044 → 440 = 4 + 4*5 + 4*25 = 120
    120
    >>> _bit_reverse_base_b(0, 2, base=2)   # 00 → 00
    0
    >>> _bit_reverse_base_b(1, 2, base=2)   # 01 → 10 = 2
    2
    >>> _bit_reverse_base_b(2, 2, base=2)   # 10 → 01 = 1
    1
    >>> _bit_reverse_base_b(3, 2, base=2)   # 11 → 11 = 3
    3
    """
    if n < 0:
        raise ValueError(f"n 必须非负, 得到 {n}")
    if n >= base ** bits:
        raise ValueError(
            f"n={n} 超出 {base}^{bits}={base**bits} 范围 (需要 bits 更多)"
        )

    # 抽取 base 进制 digits
    digits: List[int] = []
    x = n
    for _ in range(bits):
        digits.append(x % base)
        x //= base
    # 此时 digits = [d0, d1, d2, ..., d_{bits-1}] (低位在前)
    # 倒序: d_{bits-1} 变最低位, d_{bits-1} 乘 base^0, d_{bits-2} 乘 base^1, ...
    r = 0
    for i, d in enumerate(reversed(digits)):
        r += d * (base ** i)
    return r


# ===========================================================================
# 2. 按位反转 — 找下一个挂载点 / 实际挂载
# ===========================================================================

# step 从 0 开始累计 (0 = 还没挂任何新成员; 第 1 个新成员 = step 0)
# 每次新成员挂入后 step += 1
# step 决定:
#   - 在哪个 level
#   - 在该 level 内的 index i
#   - bit_reverse_base5(i, level) → 槽位

def _level_of_step(step: int, base: int = 5) -> int:
    """第 step 个新成员 (从 0 开始) 处于哪个 level

    累积 5^1 + 5^2 + ... + 5^L = (5^(L+1) - 5) / 4
    step 0..4                  → level 1 (root 下 5 子)
    step 5..29                 → level 2 (5 个 L1 父各 5 子 = 25 子)
    step 30..154               → level 3 (25 个 L2 父各 5 子 = 125 子)
    ...
    """
    if step < 0:
        raise ValueError(f"step 必须非负, 得到 {step}")
    # 累积 base^L 从 L=1 开始
    cum = 0
    level = 1
    while cum + base ** level <= step:
        cum += base ** level
        level += 1
    return level


def _index_in_level(step: int, base: int = 5) -> int:
    """第 step 个新成员在所在 level 内的 index (0..5^level-1)"""
    if step < 0:
        raise ValueError(f"step 必须非负, 得到 {step}")
    cum = 0
    level = 1
    while cum + base ** level <= step:
        cum += base ** level
        level += 1
    return step - cum


# ===========================================================================
# PR #71: 算法翻案 — 5 叉按位反转 -> 4 大区横向 A->C->B->D + 纵向 L1->L2 优先
# ===========================================================================
# 业务规则 (用户 2026-08-03 拍板, 翻案 PR #18 5 叉按位反转):
#   - 横向 4 大区顺序: A(line 1) -> C(line 3) -> B(line 2) -> D(line 4)
#   - 纵向: L1 (line 1) 优先 -> L2 (line 2) -> L3, L4 (5 叉 eff=4 兜底)
#   - 5 叉 eff=4 时 line 5 锁
#   - 5 叉树 9 层深 (PR #18 9 层满规则保留)
#   - 旧算法 (5 叉按位反转) 替换为新算法 (4 大区横向 + 纵向 L1->L2 优先)
HORIZONTAL_ORDER = [1, 3, 2, 4]  # 4 大区横向: A(line 1) -> C(line 3) -> B(line 2) -> D(line 4)
MAX_DEPTH_PR71 = 9  # 5 叉 9 层满


def _find_next_slot_pr71_v2(
    node: "Node5",
    depth: int = 0,
) -> "Optional[Tuple[Node5, int]]":
    """PR #71 v2 (深度优先递归, 已被 v3 翻案): 4 大区横向 A->C->B->D + 纵向 L1->L2 优先.

    业务规则 (PR #71, 2026-08-03 用户拍板, **2026-08-04 翻案**):
      - 横向 4 大区: A(line 1) -> C(line 3) -> B(line 2) -> D(line 4)
      - 纵向: L1 (line 1) 优先, 然后 L2 (line 2), 然后 L3, L4 兜底 (eff=4)
      - 5 叉 eff=4 时 line 5 锁
      - 5 叉树 9 层深 (PR #18 9 层满规则保留)

    算法 (递归):
      - 在 node 内, 横向 4 大区按 HORIZONTAL_ORDER 找
      - 每个 4 大区, 先看是否空 (is_avail), 是 -> return
      - 否则递归到该 4 大区的子树 (depth+1), 同样规则

    **翻案原因 (2026-08-04)**: v2 是深度优先, 实际行为是 A 9 层 -> C 9 层 -> B 9 层 -> D 9 层
    (单链), 不符合用户原话 12 个点位 (4 大区 L1 平行 -> L2 平行 -> L3 平行)
    """
    if depth >= MAX_DEPTH_PR71:
        return None
    eff = node.effective_max_active_lines()
    if eff < 2:
        return None

    for line in HORIZONTAL_ORDER:
        if line > eff:
            continue
        child_idx = line - 1
        if child_idx < len(node.children):
            child = node.children[child_idx]
            if not child.is_avail:
                # 已挂 real, 递归到该 child
                sub = _find_next_slot_pr71_v2(child, depth + 1)
                if sub is not None:
                    return sub
                continue
        # 空 (没 children 或 avail placeholder), 挂这里
        return (node, line)
    return None


def _decode_bfs_path(bfs_idx: int) -> list:
    """PR #11 v4: BFS 索引 → 路径. 业务: 4 大区 L1 父 子树 BFS 枚举.

    业务规则 (用户 2026-08-04 拍板):
      - BFS 1 = root (空 path [])
      - BFS 2 = root.children[0] (path [1])  (left child, line 1)
      - BFS 3 = root.children[1] (path [2])  (right child, line 2)
      - BFS 4 = BFS 2.children[0] (path [1, 1])
      - BFS 5 = BFS 2.children[1] (path [1, 2])
      - BFS 6 = BFS 3.children[0] (path [2, 1])
      - BFS 7 = BFS 3.children[1] (path [2, 2])
      - BFS 8 = BFS 4.children[0] (path [1, 1, 1])
      - ...

    算法: 递归解码
      - bfs_idx <= 1 → []
      - bfs_idx >= 2 → parent_idx = bfs_idx // 2, is_right = bfs_idx % 2
        - line = 2 if is_right else 1
        - return decode(parent_idx) + [line]
    """
    if bfs_idx <= 1:
        return []
    parent_idx = bfs_idx // 2
    is_right = bfs_idx % 2
    line = 2 if is_right else 1
    return _decode_bfs_path(parent_idx) + [line]


def _compute_slot_pr71_v3(
    tree: "Node5",
    step: int,
) -> "Optional[Tuple[Node5, int]]":
    """PR #71 v5 (line-first BFS, user 2026-08-04 反馈) — 2026-08-04.

    业务规则 (PR #71, 2026-08-04 用户拍板, line-first BFS 跟 L2 一致):
      - 4 大区横向: A(line 1) -> C(line 3) -> B(line 2) -> D(line 4)  (HORIZONTAL_ORDER)
      - 4 大区 L1 平行 -> L2 平行 (column-first BFS, 跟 L1 一致)
      - L2+ line 优先 4 大区后: 先 line 1 全部 4 大区 (m5/m6/m7/m8) → line 2 全部 4 大区 (m9/m10/m11/m12)
      - L_k 父 (k >= 2) 也 line 优先: 先 L_(k-1) 父的 line 1 全部, 再 line 2 全部 (line-first BFS)
      - 5 叉 eff=4 时 line 5 锁
      - 5 叉树 9 层深 (PR #18 9 层满规则保留)

    PR #71 v5 修复 (2026-08-04 用户反馈, k5 应该挂 m9 左支 + L3 标号 重复):
      - 旧 (PR #11 v4) 业务 depth-first BFS: step 12-15 业务 L2 父 line 1, step 16-19 业务 L2 父 line 2 (m5.line 2)
        - k5 业务 (m5, 2) 业务! 业务上 k5 应该挂 m9 左支 (m9.line 1)
        - 业务 L3 标号公式 `(line-1)*4 + region_idx` 业务 (m7.line 1=L3-15) 跟 (m9.line 1=L3-15) 重复
      - 新 (PR #71 v5) 业务 line-first BFS: step 12-19 业务 全部 L3 父 line 1 (m5/m6/m7/m8/m9/m10/m11/m12 line 1)
        - step 12-15: m5/m6/m7/m8 line 1 (4 个 L2 父 line 1)
        - step 16-19: m9/m10/m11/m12 line 1 (4 个 L2 父 line 2)
        - step 20+: 全部 L3 父 line 2
      - 业务 L3 标号 业务 (l3_line, l2_line, region_idx) 算, 业务:
        - m5.line 1=L3·13, m5.line 2=L3·21
        - m9.line 1=L3·17, m9.line 2=L3·25
        - 全部 16 个 L3 槽位 业务 唯一标号 13-28

    12 个 L2 标 (PR #10, 业务 PR #71 v5 不变):
      - step 0-3: 4 L1 父 (A=L1·1, C=L1·2, B=L1·3, D=L1·4)
      - step 4-7: 4 L2 父 line 1 (A.line 1=L2·5, C.line 1=L2·6, B.line 1=L2·7, D.line 1=L2·8)
      - step 8-11: 4 L2 父 line 2 (A.line 2=L2·9, C.line 2=L2·10, B.line 2=L2·11, D.line 2=L2·12)

    L3 父 (k1-k5 批量添加, 5 个新成员):
      - step 12 (k1, reg 0, m5.line 1): parent_bfs_path=[1,1], line=1 → (m5, 1) ✓
      - step 13 (k2, reg 1, m6.line 1): (m6, 1) ✓
      - step 14 (k3, reg 2, m7.line 1): (m7, 1) ✓
      - step 15 (k4, reg 3, m8.line 1): (m8, 1) ✓
      - step 16 (k5, reg 0, m9.line 1): parent_bfs_path=[1,2], line=1 → (m9, 1) ✓
      - step 17-19: m10/m11/m12 line 1 (avail)
      - step 20+: 8 个 L3 父 line 2 (avail)

    算法 (line-first BFS):
      - step 0-3: L1 父 (4 L1 父 业务 region 业务)
      - step 4+: L_k 父 (k >= 2)
        - 业务 depth d: line-first BFS, 业务 4 大区 L_(d-1) 父 业务 line 1 → 业务 line 2
        - 业务 (line, L_(d-1) 父 idx) 业务 → 业务 (parent_node, line) 业务
    """
    if step < 0:
        return None

    if step < 4:
        # 业务: 业务 4 L1 父 业务 region 业务 (业务 PR #5)
        region_idx = step
        root_line = HORIZONTAL_ORDER[region_idx]
        if root_line > tree.effective_max_active_lines():
            return None
        return (tree, root_line)

    # 业务: 业务 L_k 父 (k >= 2) 业务 line-first BFS
    # 业务 step 业务: 业务 2^(d+1) - 4 <= s < 2^(d+2) - 4
    # 业务 d=2: 业务 4-11 (8 步)
    # 业务 d=3: 业务 12-27 (16 步)
    # 业务 d=4: 业务 28-59 (32 步)
    s = step
    d = 1
    while s >= 2 ** (d + 2) - 4:
        d += 1
    # 业务 depth_offset 业务 s - (2^(d+1) - 4)
    depth_offset = s - (2 ** (d + 1) - 4)

    # 业务: 业务 depth d 业务 业务: 业务 line (1, 2) 业务 业务 L_(d-1) 父 业务 order
    # 业务 n_l_prev = 业务 L_(d-1) 父 业务 = 2^d 业务 d >= 2
    n_l_prev = 2 ** d
    line_offset = depth_offset // n_l_prev
    prev_idx = depth_offset % n_l_prev
    line = line_offset + 1

    # 业务: 业务 L_(d-1) 父 业务 业务 prev_idx 业务 (业务 line-first BFS order)
    prev_parent = _get_parent_at_depth_v5(tree, d - 1, prev_idx)
    if prev_parent is None:
        return None
    if line > prev_parent.effective_max_active_lines():
        return None
    return (prev_parent, line)


def _get_parent_at_depth_v5(
    tree: "Node5",
    target_depth: int,
    idx: int,
) -> "Optional[Node5]":
    """PR #71 v5: 业务 L_(target_depth) 父 业务 业务 idx 业务 (line-first BFS order).

    业务:
      - target_depth=1: idx 0-3 业务 4 L1 父 业务 region 业务
      - target_depth=2: idx 0-7 业务 8 L2 父 业务 (line, region) order
      - target_depth=3: idx 0-15 业务 16 L3 父 业务 (line, l2_idx) order
      - 业务 业务 业务 (target_depth >= 2): 业务 line-first BFS 业务
    """
    if target_depth == 1:
        # L1 父 业务 region 业务
        if idx < 0 or idx >= 4:
            return None
        root_line = HORIZONTAL_ORDER[idx]
        if root_line > tree.effective_max_active_lines():
            return None
        if tree.children is None or len(tree.children) < root_line:
            return None
        return tree.children[root_line - 1]

    # target_depth >= 2: 业务 line-first BFS 业务
    # 业务: 业务 L_(d-1) 父 业务 n_l_prev = 2^d 业务
    # 业务: 业务 (line_offset, prev_idx) → 业务 (line, L_(d-2) 父 idx) 业务
    n_l_prev = 2 ** target_depth
    if idx < 0 or idx >= n_l_prev * 2:
        return None
    line_offset = idx // n_l_prev
    prev_idx = idx % n_l_prev
    line = line_offset + 1

    # 业务: 业务 L_(d-1) 父 业务 prev_idx 业务
    prev_parent = _get_parent_at_depth_v5(tree, target_depth - 1, prev_idx)
    if prev_parent is None:
        return None
    if prev_parent.children is None or len(prev_parent.children) < line:
        return None
    child = prev_parent.children[line - 1]
    if child.is_avail:
        return None
    return child


def _is_slot_avail(parent: "Node5", line: int) -> bool:
    """检查 (parent, line) 槽位是否 avail (未挂 real).

    业务: parent.children[line-1] 不存在 OR is_avail=True → 可填
    实际 caller (simulate_addition) replace avail, 所以 avail 占位是合法状态
    """
    if parent.children is None or len(parent.children) < line:
        return True  # 没 children, 整个父节点空, 当然可填
    child = parent.children[line - 1]
    return child.is_avail


def _find_next_slot_pr71_v3(
    tree: "Node5",
    step: int = 0,
    max_step: int = 1000,
) -> "Optional[Tuple[Node5, int]]":
    """PR #71 v3 (列优先 BFS, stage-based, 用户 2026-08-04 拍板): 4 大区 L1 平行 -> L2 平行 -> ...

    业务规则 (PR #71, 2026-08-04 用户拍板, 严格匹配 12 个点位):
      - 4 大区横向顺序: A(line 1) -> C(line 3) -> B(line 2) -> D(line 4)
      - 4 大区 L1 平行 (4 region 各自 L1 子节点, 先全部 4 个都 fill)
      - 4 大区 L1 全满才 L2 (4 region 各自 L2 子节点)
      - 5 叉 eff=4 时 line 5 锁
      - 5 叉树 9 层深 (PR #18 9 层满规则保留)

    12 个点位 (用户原话, 严格匹配):
      step  1: A-L1 (root.line 1)    = root.line 1   = A
      step  2: C-L1 (root.line 3)    = root.line 3   = C
      step  3: B-L1 (root.line 2)    = root.line 2   = B
      step  4: D-L1 (root.line 4)    = root.line 4   = D
      step  5: A-L2                  = A.line 1      = E1
      step  6: C-L2                  = C.line 1      = E2
      step  7: B-L2                  = B.line 1      = E3
      step  8: D-L2                  = D.line 1      = E4
      step  9: A-L3                  = A.line 2      = F1
      step 10: C-L3                  = C.line 2      = F2
      step 11: B-L3                  = B.line 2      = F3
      step 12: D-L3                  = D.line 2      = F4

    算法 (stage-based + 看 tree 状态跳过已占):
      - step 决定 (parent, line) — stateless 计算
      - 检查 (parent, line) 槽位是否已占, 已占 → step+1 重试
      - max_step 限制避免无限循环 (业务树大小 < 1000 step)
    """
    s = step
    while s < step + max_step:
        slot = _compute_slot_pr71_v3(tree, s)
        if slot is None:
            return None
        parent, line = slot
        if not _is_slot_avail(parent, line):
            s += 1  # 槽位已占, 跳下一个 step
            continue
        return (parent, line)
    return None


def find_next_slot_bitrev(
    tree: "Node5",
    step: int = 0,
    base: int = 5,
) -> "Optional[Tuple[Node5, int]]":
    """PR #71: 4 大区横向 A->C->B->D + 纵向 L1->L2 优先, 5 叉 9 层深 (PR #18 翻案).

    业务规则 (用户 2026-08-03 拍板, **2026-08-04 v3 翻案**):
      - 横向 4 大区顺序: A(line 1) -> C(line 3) -> B(line 2) -> D(line 4)
      - 4 大区 L1 平行 -> L2 平行 -> L3 平行 (列优先 BFS, 严格匹配 12 个点位)
      - 纵向: L1 (line 1) 优先, L2 (line 2), L3, L4, L5 (eff=5 满)
      - 5 叉 eff=4 时 line 5 锁 (默认; root.eff=4 PR #1 拍板)
      - 5 叉树 9 层深 (PR #18 9 层满规则保留)
      - 函数名 find_next_slot_bitrev 保留 (向后兼容), 行为已改为 v3 (列优先 BFS)
    """
    return _find_next_slot_pr71_v3(tree, step=step)


def _find_next_slot_bitrev_legacy(
    tree: Node5,
    step: int,
    base: int = 5,
) -> Optional[Tuple[Node5, int]]:
    """按「base 进制 digit reversal」找下一个挂载点的 (父节点, line_id)。

    ★ 2026-07-14 v6: 返回 (parent, line_id) pair, caller 不再算 line_id
    ★ 2026-07-14 v6: 业务规则「双轨制」渐进解锁 (用户拍板)
      - 每个父节点默认 max_active_lines=2 (只 L1+L2 激活)
      - L1+L2 都被真实成员占满 → 提升到 4 (L3+L4 同时激活)
      - L1-L4 都满 → 提升到 5 (L5 单独激活)

    ★ 2026-07-15 PR #18: 动态 base = root.effective_max_active_lines()
      - 业务规则「挂满 9 层」全局触发, 算法 base 跟 root.eff 走
      - root.eff=2 (默认): 算法 base=2 → 只挂 line 1+line 2 (跳 line 3+4+5)
      - root.eff=4 (line 1+2 满 9 层): 算法 base=4 → 解锁 line 3+4
      - root.eff=5 (line 1-4 满 9 层): 算法 base=5 → 解锁 line 5
      - 跟 TreeGenerate/full_tree.html 严格 base-N digit reversal 一致

    算法
    ----
        global_base = tree.effective_max_active_lines()   # PR #18 动态 base
        level = _level_of_step(step, base=global_base)
        i     = _index_in_level(step, base=global_base)
        slot  = _bit_reverse_base_b(i, level, global_base)
        parent_bfs_idx = slot // global_base
        col = slot % global_base
        target_depth = level - 1

        BFS 找 target_depth 层的父, 但只收集 line_id <= global_base 的父
        (line 3+4+5 locked 时, BFS 跳过 line 3+4+5 父, 算法 base 自动变 2)

        父 = BFS 序里第 parent_bfs_idx 个父
        line_id = real_count(parent.children) + 1
        检查 line_id <= global_base AND line_id <= parent.eff
        (父可能 eff 较小, 比如父的 line 1+2 还没满 9 层)

    Returns
    -------
    Optional[Tuple[Node5, int]]
        (父节点, line_id) pair; 树满 / 计算异常则返回 None。
    """
    # ★ 2026-07-15 PR #18: 动态 base = root 的 eff (业务规则全局触发)
    #   - 算法不再用全局 base=5, 跟 root.eff 走
    #   - root.eff=2 (默认): 算法 base=2 → 只挂 line 1+line 2 (跳 line 3+4+5)
    #   - root.eff=4 (line 1+2 满 9 层): 算法 base=4 → 解锁 line 3+4
    #   - root.eff=5 (line 1-4 满 9 层): 算法 base=5 → 解锁 line 5
    #   - 跟 TreeGenerate/full_tree.html 严格 base-N digit reversal 一致
    global_base = tree.effective_max_active_lines()
    if global_base < 2:
        return None  # 业务上没激活线, 算法无槽位可挂

    # ★ 2026-07-16 PR #22 fix: 算法改成「遍历所有 (level, i) slot, 找第一个实际可挂入的」
    #   之前 (PR #20 v3) 用 step 算 (level, i), 父满跳 parent_bfs++ / level 跳 i
    #   问题: preview stateless batch(1) 永远 step=0, 但累积 tree 下 i 已经不是 0
    #   例: root 满 + L1 父满 + L2 父空, 算法应该挂 L2 父.line 1 (节点 5) 不是 L1 父.line 2
    #   修复: 遍历所有 (level, i) 按 base-N 严格按位反转顺序, 跳过已挂的 (parent 满 / col 已被占)
    #   算法 stateless + 累积 tree 自然兼容, 不需要跨 batch 维护 step counter
    #
    # 遍历顺序示例 (base=2):
    #   L=1: i=0..1  (节点 1, 2) — root.line 1, root.line 2
    #   L=2: i=0..3  (节点 3..6 bit_rev=0,2,1,3)
    #         4=L1父.line1, 5=L2父.line1, 6=L1父.line2, 7=L2父.line2
    #   L=3: i=0..7  (节点 7..14)
    max_level = 10  # 防止死循环
    for level in range(1, max_level + 1):
        n_slots = global_base ** level
        for i in range(n_slots):
            slot = _bit_reverse_base_b(i, level, base=global_base)
            parent_bfs_idx = slot // global_base
            col = slot % global_base  # 0-based, 业务 line_id = col+1
            line_id = col + 1

            if line_id > global_base:
                continue  # 算法 base 内, line_id 最大 = base, 不会超过

            # BFS 找 target_depth 层第 parent_bfs_idx 个父 (line_id <= base)
            target_depth = level - 1
            parent = _bfs_find_nth_parent(tree, target_depth, parent_bfs_idx, global_base)
            if parent is None:
                continue  # 这个 level 父不够 (parent_bfs_idx >= len)

            # ★ 检查父的 eff: line_id 必须 <= parent.eff
            if line_id > parent.effective_max_active_lines():
                continue  # 父的 eff 较小, 这个 col 还没激活

            # ★ 检查 col 位置是否已被占 (real 节点存在)
            if col < len(parent.children) and not parent.children[col].is_avail:
                continue  # 已被占, 跳下个 i

            return (parent, line_id)

        # 整个 level 所有 slot 都不可挂入, 跳下个 level
    return None  # 整个树满了


def _bfs_find_nth_parent(
    tree: Node5,
    target_depth: int,
    nth: int,
    global_base: int,
) -> Optional[Node5]:
    """BFS 找 target_depth 层第 nth 个父节点 (line_id <= global_base)
    找不到 (nth >= 匹配数) 返回 None
    """
    count = 0
    queue: List[Tuple[Node5, int, int]] = [(tree, 0, 0)]
    while queue:
        cur, depth, lid = queue.pop(0)
        if depth == target_depth:
            if lid <= global_base:
                if count == nth:
                    return cur
                count += 1
        for idx, c in enumerate(cur.children):
            c_lid = c.line_id if c.line_id > 0 else (idx + 1)
            queue.append((c, depth + 1, c_lid))
    return None



def _calc_col_from_step(step: int, base: int = 5) -> int:
    """计算 step 对应的新成员的 col (0-based) — 供 add_user / simulate_addition 用"""
    level = _level_of_step(step, base=base)
    i = _index_in_level(step, base=base)
    slot = _bit_reverse_base_b(i, level, base=base)
    return slot % base  # 0-based col


def add_user_bitrev(
    tree: Node5,
    pv: int,
    name: str = "",
    code: str = "",
    base: int = 5,
    _state: Optional[Dict[str, int]] = None,
) -> Optional[Node5]:
    """按「base 进制 digit reversal」添加一个新成员。

    Parameters
    ----------
    tree : Node5
        当前网体根节点(直接 in-place 修改, 不深拷贝)
    pv   : int
        新成员 PV(必须 > 0)
    name : str
        可选, 新成员姓名
    code : str
        可选, 新成员 code
    base : int
        进制 (5 叉树 = 5)
    _state : Optional[Dict[str, int]]
        内部状态字典 {"step": int}, 由 simulate_addition_bitrev 维护,
        保证跨多次调用 step 累计正确。外部调用可传 None, 内部用函数属性。

    Returns
    -------
    Node5 | None
        成功挂入返回新节点; 树无空位返回 None。
    """
    if pv <= 0:
        raise ValueError(f"pv 必须是正整数, 得到 {pv}")

    # 维护 step 状态 (函数属性, 避免全局变量污染)
    if _state is None:
        # 外部单次调用, 用函数属性暂存 (Python 函数对象可挂属性)
        if not hasattr(add_user_bitrev, "_step_state"):
            add_user_bitrev._step_state = {"step": 0}
        _state = add_user_bitrev._step_state

    current_step = _state["step"]
    # ★ 2026-07-14 v6: find_next_slot_bitrev 返回 (parent, line_id) pair
    #   - 内部已做 active 槽位过滤 (业务规则「双轨制」渐进解锁)
    #   - caller 不再算 line_id
    slot_info = find_next_slot_bitrev(tree, current_step, base=base)
    if slot_info is None:
        return None
    parent, new_line_id = slot_info

    new_uid = -(_state["step"] + 1)  # -1, -2, -3, ... (跟 skill_5_1 一致)
    new_node = Node5(
        uid=new_uid,
        pv=pv,
        depth=parent.depth + 1,
        name=name,
        code=code,
        max_children=parent.max_children,
        line_id=new_line_id,
    )
    parent.children.append(new_node)
    _state["step"] += 1
    return new_node


# ===========================================================================
# 3. 逐步模拟 — 计算每一步的实时利润
# ===========================================================================

def simulate_addition_bitrev(
    tree: Node5,
    pv_list: List[int],
    names: Optional[List[str]] = None,
    codes: Optional[List[str]] = None,
    include_pairing: bool = True,
    parent_dist_id_map: Optional[Dict[int, str]] = None,
    start_rank: int = 0,
    base: int = 5,
) -> List[Dict[str, Any]]:
    """按「base 进制 digit reversal」依次挂入多个新成员, 每一步记录实时利润与父节点增量。

    与 skill_5_1.simulate_addition 结构一致, 但挂载算法不同:
        - skill_5_1: 列优先 BFS (改后 v4 只挂奇数线, commission 永远 0)
        - skill_5_2: 配对优先 BFS (凑 L1+L2 配对, 触发 commission)
        - skill_5_3: 按位反转 (全员 5 列都挂, base-5 digit reversal)

    Parameters
    ----------
    tree                 : 当前网体根节点(in-place 修改)
    pv_list              : 新成员 PV 列表, 按顺序加入
    names, codes         : 可选, 新成员姓名 / code 列表
    include_pairing      : 是否计算对等奖金
    parent_dist_id_map   : 可选, uid → officev2 distId 反向索引
    start_rank           : 跨 batch 全局基数 (与 skill_5_1 一致, 保证新 uid 全局递增)
    base                 : 进制 (5 叉树 = 5)

    Returns
    -------
    List[dict]
        每一步一个 dict(见 AdditionStep.to_dict())。
    """
    cur = _snapshot_profit(tree, include_pairing)

    history: List[Dict[str, Any]] = []

    # step 状态 (跨 batch 由 main.py 通过 start_rank 控制全局 uid 递增)
    _state: Dict[str, int] = {"step": 0}

    # 新成员临时 distId 映射 (每个新成员分配 PREVIEW-{rank})
    _preview_dist_id_map: Dict[int, str] = {}

    # 综合 dist_id 反查表
    _combined_dist_id_map: Dict[int, str] = dict(parent_dist_id_map or {})

    def _alloc_neg_uid() -> int:
        """跟 skill_5_1 一样的 uid 分配: -(global_rank)"""
        global_rank = _state["step"] + start_rank + 1
        new_uid = -global_rank
        new_dist_id = f"PREVIEW-{global_rank}"
        _preview_dist_id_map[new_uid] = new_dist_id
        _combined_dist_id_map[new_uid] = new_dist_id
        return new_uid

    for step_idx, pv in enumerate(pv_list, start=1):
        # ★ 2026-07-14 v6: 返回 (parent, line_id) pair, 不再算 line_id
        slot_info = find_next_slot_bitrev(tree, _state["step"], base=base)
        if slot_info is None:
            # 树已满, 终止模拟
            break
        parent, new_line_id = slot_info

        # 父节点挂入前的 basic
        parent_basic_before = basic_commission(parent)

        # 挂入
        new_uid = _alloc_neg_uid()
        n = names[step_idx - 1] if (names and step_idx - 1 < len(names)) else ""
        c = codes[step_idx - 1] if (codes and step_idx - 1 < len(codes)) else ""

        new_node = Node5(
            uid=new_uid,
            pv=pv,
            depth=parent.depth + 1,
            name=n,
            code=c,
            max_children=parent.max_children,
            line_id=new_line_id,
        )
        # ★ 2026-07-15 PR #17: 替换 avail 节点(而不是 append)
        #   - load_from_jstree_dict 保留 avail 在 children 数组(line_id 1..5)
        #   - 之前 append 模式: 5 个 avail + 5 个 real = children=10, real_count=5,算法错位
        #   - 替换模式: 在 parent.children[line_id-1] 找到 avail 节点(按 line_id 匹配),用 real 替换
        #   - children 总数保持 base 个 (5), 算法能正确算 real_count
        replaced = False
        for i, c in enumerate(parent.children):
            if c.is_avail and c.line_id == new_line_id:
                parent.children[i] = new_node
                replaced = True
                break
        if not replaced:
            # 没找到匹配的 avail 槽位 — append 模式 (fallback, 兼容老数据)
            parent.children.append(new_node)
        _state["step"] += 1

        # 重算利润
        new = _snapshot_profit(tree, include_pairing)
        parent_basic_after = basic_commission(parent)

        lift_b = new["basic"] - cur["basic"]
        lift_p = new["pairing"] - cur["pairing"]
        lift_t = new["total"] - cur["total"]
        lift_pct = (lift_t / cur["total"] * 100.0) if cur["total"] > 0 else None

        step_data = AdditionStep(
            step=step_idx,
            uid=new_uid,
            pv=pv,
            name=n if n else "",
            parent_uid=parent.uid,
            parent_dist_id=_combined_dist_id_map.get(parent.uid, ""),
            member_dist_id=_preview_dist_id_map.get(new_uid, ""),
            ancestor_chain=_ancestor_chain(tree, new_node, dist_id_map=_combined_dist_id_map),
            parent_basic_before=round(parent_basic_before, 4),
            parent_basic_after=round(parent_basic_after, 4),
            basic_before=round(cur["basic"], 4),
            basic_after=round(new["basic"], 4),
            pairing_before=round(cur["pairing"], 4),
            pairing_after=round(new["pairing"], 4),
            total_before=round(cur["total"], 4),
            total_after=round(new["total"], 4),
            lift_basic=round(lift_b, 4),
            lift_pairing=round(lift_p, 4),
            lift_total=round(lift_t, 4),
            lift_pct=round(lift_pct, 2) if lift_pct is not None else None,
        )
        history.append(step_data.to_dict())

        cur = new

    return history


# ===========================================================================
# 4. 演示入口
# ===========================================================================

def run_demo_bitrev(
    n_members: int = 30,
    pv_per_member: int = 200,
    seed_pv: int = 1000,
    max_children: int = 5,
    include_pairing: bool = True,
) -> List[Dict[str, Any]]:
    """CLI 演示入口: 从一个 root 开始, 按 base-5 digit reversal 加 n_members 个新成员。

    默认参数(n_members=30, pv=200, seed_pv=1000, max_children=5)覆盖:
        L1: 5 个新成员(root 下 5 子, col 0..4)
        L2: 25 个新成员(5 个 L1 父各 5 子)
        总节点数 = 1 + 5 + 25 = 31
        默认 n_members=30: 跑完 L1 全员(5) + L2 前 25 个
    """
    # 重置函数属性, 避免 CLI 多次跑时 step 状态污染
    if hasattr(add_user_bitrev, "_step_state"):
        delattr(add_user_bitrev, "_step_state")

    tree = Node5(
        uid=1, pv=seed_pv, depth=0,
        max_children=max_children,
    )

    print("=" * 92)
    print(f"Skill 5_3 演示 · 「按位反转 (base-5 digit reversal)」添加新成员 · 5 叉网体实时佣金")
    print("=" * 92)
    print(f"初始:     root (uid=1, pv={seed_pv}, max_children={max_children})")
    print(f"规则:     按位反转 (L+1 阶段 5^L 个新成员, 槽位 = bit_reverse_base5(i, L))")
    print(f"输入:     {n_members} 个新成员, 每人 PV={pv_per_member}")
    print(f"业务:     5 叉制 · basic=MIN(P, L_sum)·{COMMISSION_RATE:.0%} · "
          f"pairing 7 代 [15/10/5×5] · 封顶 {ZONE_CAP}")
    print("=" * 92)

    pv_list = [pv_per_member] * n_members
    history = simulate_addition_bitrev(
        tree, pv_list,
        include_pairing=include_pairing,
        base=max_children,  # 用 max_children 决定 base (5 叉 → base=5, 测试用 base=2/3 即可)
    )

    if not history:
        print("\n(没有挂入任何成员 — 请检查 n_members / seed_pv / max_children)")
        return history

    # ----------- 逐步表格 -------------
    pair_cols_hdr = (f"  {'PairΔ':>8}  {'Pair':>8}" if include_pairing else "")
    print(
        f"{'#':>3}  {'UID':>4}  {'PV':>5}  {'Par':>4}  "
        f"{'BcΔ':>8}  {'Basic':>8}"
        + pair_cols_hdr
        + f"  {'TotΔ':>8}  {'Total':>8}  {'Lift%':>8}  {'L':>2}"
    )
    for h in history:
        pct = "N/A" if h["lift_pct"] is None else f"{h['lift_pct']:+.2f}%"
        pair_cols = (
            f"  {_fmt(h['lift_pairing']):>8}  {_fmt(h['pairing_after']):>8}"
            if include_pairing
            else ""
        )
        # 从 ancestor_chain 末尾取 parent_line_id
        last_lid = h["ancestor_chain"][-1]["parent_line_id"] if h["ancestor_chain"] else "?"
        print(
            f"{h['step']:>3}  {h['uid']:>4}  {h['pv']:>5}  {h['parent_uid']:>4}  "
            f"{_fmt(h['lift_basic']):>8}  {_fmt(h['basic_after']):>8}"
            + pair_cols
            + f"  {_fmt(h['lift_total']):>8}  {_fmt(h['total_after']):>8}  {pct:>8}  L{last_lid}"
        )

    # ----------- 汇总 -------------
    final_tree_size = len(_bfs_all(tree))
    final_basic = total_basic(tree)
    final_pairing = pairing_bonus(tree) if include_pairing else 0.0
    final_total = final_basic + final_pairing

    print("=" * 92)
    print(f"最终状态")
    print(f"  整树节点数:       {final_tree_size}  (含 root)")
    print(f"  最终 basic:       ${final_basic:.2f}")
    print(f"  最终 pairing:     ${final_pairing:.2f}")
    print(f"  最终 total:       ${final_total:.2f}")
    print(f"  整树 PV 总和:     {sum(n.pv for n in _bfs_all(tree))} 分")
    print("=" * 92)

    # ----------- 业务对比 -------------
    if include_pairing and history:
        last = history[-1]
        lift_per_200pv = last["total_after"] / (last["step"] * pv_per_member) if last["step"] else 0
        print(f"\n[业务对比] 同样 {n_members} 个新成员 × PV={pv_per_member}:")
        print(f"  skill_5_1 (列优先 BFS, 只挂 L1/L3/L5): 5 子区缺右叉, basic ≈ 0")
        print(f"  skill_5_2 (配对优先 BFS, 凑 L1+L2):     5 父各凑 L1+L2, basic 部分触发")
        print(f"  skill_5_3 (按位反转, 全员 5 列):         5 子区全填, 整树 basic=${final_basic:.2f}")

    return history


def _fmt(x: float) -> str:
    """数值格式化为 ±X.XX"""
    if x is None:
        return "—"
    if x == 0:
        return "0.00"
    return f"{x:.2f}" if x >= 0 else f"{x:.2f}"


# ===========================================================================
# 5. CLI
# ===========================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Skill 5_3 · 按位反转 (base-5 digit reversal) 添加新成员 + 5 叉网体实时佣金",
    )
    parser.add_argument(
        "-n", "--n-members", type=int, default=30,
        help="新成员数量 (默认 30 = L1 全员 5 + L2 前 25 个, 共 30 个)",
    )
    parser.add_argument(
        "--pv", type=int, default=200,
        help="每个新成员的 PV (默认 200)",
    )
    parser.add_argument(
        "--seed-pv", type=int, default=1000,
        help="root 的 PV (默认 1000)",
    )
    parser.add_argument(
        "--max-children", type=int, default=5,
        help="5 叉 = 5(可配, 测试用 2 叉可复现 verify_l6 行为, 3 叉可对照位反转 3 进制)",
    )
    parser.add_argument(
        "--no-pairing", action="store_true",
        help="不计算对等奖金(只看 basic)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="把历史以 JSON 输出到 stdout(便于 Agent 消费)",
    )

    args = parser.parse_args()

    if args.json:
        tree = Node5(
            uid=1, pv=args.seed_pv, depth=0, max_children=args.max_children,
        )
        hist = simulate_addition_bitrev(
            tree, [args.pv] * args.n_members,
            include_pairing=not args.no_pairing,
            base=args.max_children,
        )
        print(history_to_json(hist))
    else:
        run_demo_bitrev(
            n_members=args.n_members,
            pv_per_member=args.pv,
            seed_pv=args.seed_pv,
            max_children=args.max_children,
            include_pairing=not args.no_pairing,
        )
