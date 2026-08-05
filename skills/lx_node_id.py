# -*- coding: utf-8 -*-
"""PR #24: 按 tree_l1_4_l10.html 的位反转规则给节点分配全局唯一编号.

参照 TreeGenerate/gen_l1_4_l10.py (2026-08-05).

# 每层 first/last 公式 (跟 tree_l1_4_l10 "2. 逐层规模与位反转排列" 一致):
- L0: 1 (1 节点)
- L_k (k>=1): first = 2^(k+1) - 2, count = 2^(k+1), last = 2^(k+2) - 3
- 位反转 bits = k+1 (k>=1), L0 用 bits=0

# 每层内 BFS 顺序排, 位置 i (0-indexed), 编号 = first + bit_reverse(i, bits).

# BFS 父映射 (跟 tree_l1_4_l10 一致):
- 父 L_k[i] 的 2 个 L_{k+1} 子 = L_{k+1} 位置 2i (左) 和 2i+1 (右).
- i % 2 == 0 → 左子, i % 2 == 1 → 右子.

# 5 叉业务兼容 (PR #24 A1 模式, 用户拍板 2026-08-05):
- 5 叉 line 1-2 子 → 走 tree 公式 (BFS 位置 2i, 2i+1, 编号 6-13 for L2)
- 5 叉 line 3-5 子 → BFS 位置超界 (5 叉 4 父 5 子需要 20 L2 位置, tree 公式只给 8)
  → 标 available=True, 编号用 5 叉自编号 (L_{k+1} first + count + (line-3))
  业务上保留 parent_dist_id, 编号层面跟 tree 公式不严格一致
"""


def bit_reverse(n, bits):
    """Reverse the lowest `bits` bits of n. e.g. bit_reverse(0, 3) = 0, bit_reverse(1, 3) = 4."""
    r = 0
    for _ in range(bits):
        r = (r << 1) | (n & 1)
        n >>= 1
    return r


def level_first_last(level):
    """Return (first, last, count) for given level (跟 tree_l1_4_l10 一致).

    L0: (1, 1, 1)
    L_k (k>=1): (2^(k+1)-2, 2^(k+2)-3, 2^(k+1))
    """
    if level == 0:
        return (1, 1, 1)
    first = 2 ** (level + 1) - 2
    count = 2 ** (level + 1)
    return (first, first + count - 1, count)


def global_node_id_for_bfs_pos(level, bfs_pos):
    """Compute global_node_id for a (level, bfs_pos) pair, using tree_l1_4_l10 bit-reversal.

    Args:
        level: L_k 层级 (0-indexed, 0=根)
        bfs_pos: 节点在 L_k 层内的 BFS 位置 (0-indexed, 0..2^(k+1)-1)

    Returns:
        global_node_id (整数, 跟 tree_l1_4_l10 表 "首编号" 列一致)
    """
    first, last, count = level_first_last(level)
    if level == 0:
        return 1
    bits = level + 1
    if bfs_pos < 0 or bfs_pos >= count:
        raise ValueError(f"bfs_pos {bfs_pos} out of range [0, {count}) for L{level}")
    return first + bit_reverse(bfs_pos, bits)


def five_tree_child_bfs_pos(parent_bfs_pos, line_idx):
    """5 叉父 L_k 节点的 bfs_pos + line_idx → L_{k+1} 子 BFS 位置 (A1 模式).

    A1 模式: 5 叉 line 1-2 走 tree 公式 (BFS 2i, 2i+1), line 3-5 超界返 None.

    Args:
        parent_bfs_pos: 父节点在 L_k 层内的 BFS 位置 (0-indexed)
        line_idx: 5 叉业务 line 1-5

    Returns:
        L_{k+1} 子 BFS 位置 (0-indexed) for line 1-2, None for line 3-5 (超界)
    """
    if line_idx in (1, 2):
        return 2 * parent_bfs_pos + (line_idx - 1)  # line 1 → 2i, line 2 → 2i+1
    return None  # line 3-5: BFS 位置超界 (5 叉业务 4 父 5 子 = 20 位置 > tree 给的 8)


def five_tree_own_bfs_pos(parent_bfs_pos, line_idx):
    """5 叉业务 L_{k+1} 子节点的 own BFS 位置 (跟 tree 公式脱钩, 5 叉自洽).

    公式: 5 叉 own BFS = parent_bfs_pos * 5 + (line_idx - 1)
    - L1 父 4 个, 每父 5 子 → L2 5 叉 own BFS 0..19
    - L2 父 (5 叉 own BFS 0..19) × 5 子 → L3 5 叉 own BFS 0..99
    - L3 父 × 5 子 → L4 5 叉 own BFS 0..499

    Args:
        parent_bfs_pos: 父节点在 level 层的 BFS 位置 (0-indexed, 可以是 tree BFS 也可以是 5 叉 own BFS)
        line_idx: 5 叉业务 line 1-5

    Returns:
        5 叉 own BFS 位置 (0-indexed)
    """
    return parent_bfs_pos * 5 + (line_idx - 1)


def five_tree_global_id(level, line_idx, parent_bfs_pos):
    """5 叉 line 1-2 走 tree 公式, line 3-5 用 5 叉自编号 (BFS 位置超界, 10000 偏移避免冲突).

    设计 (PR #24 A1 模式, 用户拍板 2026-08-05):
    - 5 叉 line 1-2 子: 走 tree 公式, 编号跟 tree_l1_4_l10 一致
      L2 = 6-13, L3 = 14-29, L4 = 30-61, ...
    - 5 叉 line 3-5 子: tree 公式 BFS 位置超界 (5 叉 4 父 5 子 = 20 位置, tree 给 8),
      标 available=True, 编号用 5 叉 own 公式 (10000 偏移, 跟 tree 公式完全脱钩):
        5_own_id = 10000 + 5^child_level + five_own_bfs
        five_own_bfs = parent_bfs_pos * 5 + (line-1)
      L2 5_own 范围: 10000 + 25 + 0..19 = 10025..10044
      L3 5_own 范围: 10000 + 125 + 0..99 = 10125..10224
      跨层不冲突, 跟 tree 公式 1-4093 不重叠

    Args:
        level: 父节点所在层 (0-indexed, 0=根)
        line_idx: 5 叉业务 line 1-5
        parent_bfs_pos: 父节点在 level 层的 BFS 位置 (0-indexed)

    Returns:
        (global_node_id, is_available) 元组
        - line 1-2: (tree 公式编号, False)
        - line 3-5: (5 叉 own 编号 10000+, True)
    """
    if level == 0:
        # 根节点 L0, 编号 1
        return (1, False)
    child_level = level + 1
    if line_idx in (1, 2):
        # 走 tree 公式
        child_bfs_pos = five_tree_child_bfs_pos(parent_bfs_pos, line_idx)
        return (global_node_id_for_bfs_pos(child_level, child_bfs_pos), False)
    # line 3-5: BFS 位置超界, 用 5 叉 own 公式 (10000 偏移)
    five_own_bfs = five_tree_own_bfs_pos(parent_bfs_pos, line_idx)
    five_own_id = 10000 + 5 ** child_level + five_own_bfs
    return (five_own_id, True)


# 简单自测
if __name__ == "__main__":
    print("=== tree_l1_4_l10 位反转规则自测 ===\n")

    print(f"{'层':<4} {'首编号':<8} {'末编号':<8} {'节点数':<6} {'位反转 bits'}")
    for k in range(11):
        first, last, count = level_first_last(k)
        bits = 0 if k == 0 else k + 1
        print(f"L{k:<3} {first:<8} {last:<8} {count:<6} {bits}")

    print("\n=== L1 位反转 (4 节点) ===")
    for i in range(4):
        print(f"  BFS pos {i} → 编号 {global_node_id_for_bfs_pos(1, i)}")

    print("\n=== L2 位反转 (8 节点) ===")
    for i in range(8):
        print(f"  BFS pos {i} → 编号 {global_node_id_for_bfs_pos(2, i)}")

    print("\n=== L3 位反转前 8 (16 节点) ===")
    for i in range(8):
        print(f"  BFS pos {i} → 编号 {global_node_id_for_bfs_pos(3, i)}")

    print("\n=== 5 叉业务兼容 (A1 模式, L1[0] 父的 5 子) ===")
    parent_bfs = 0  # L1 父 i=0
    for line in range(1, 6):
        gid, avail = five_tree_global_id(1, line, parent_bfs)
        print(f"  L1[i=0] line {line} → 编号 {gid}, available={avail}")

    print("\n=== 5 叉 line 3-5 跨父验证 (L1 4 父 × line 3, own BFS 0..2) ===")
    for parent_bfs in range(4):
        gid, avail = five_tree_global_id(1, 3, parent_bfs)
        print(f"  L1[i={parent_bfs}] line 3 → 编号 {gid}, available={avail}")
