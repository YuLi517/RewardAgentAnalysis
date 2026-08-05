# -*- coding: utf-8 -*-
"""PR #24: 给 original_tree_nodes 表加 global_node_id 列, 按 tree_l1_4_l10 位反转规则填.

参照:
- skills/lx_node_id.py (算法, bit_reverse + level_first_last + 5 叉 own 编号 10000+)
- TreeGenerate/tree_l1_4_l10.html (位反转规则源头)
- TreeGenerate/gen_l1_4_l10.py (公式: first=2^(k+1)-2, bits=k+1)

# 业务规则 (PR #24 A1 模式, 用户拍板 2026-08-05):
- 5 叉 line 1-2 子: 走 tree 公式, 编号跟 tree_l1_4_l10 一致
  L0=1, L1=2-5, L2=6-13, L3=14-29, L4=30-61, L5=62-127, L6=126-255, ...
- 5 叉 line 3-5 子: 5 叉 own 编号 (10000+ 偏移, 跟 tree 公式完全脱钩)
  L2 line 3-5 范围 10025-10044, L3 10125-10224, L4 10625-11124, ...
- 业务 5 叉保留: parent_dist_id + slot_line_id 1-5 不动, 编号系统辅助标识

# 幂等:
- 加列前检查列是否存在, 存在跳过
- 重算 global_node_id (按 BFS 顺序), 覆盖已有值
- 不动其他列, 不删行
"""

import sqlite3
import sys
import os
from pathlib import Path

# 强制 UTF-8 stdout (避免 Windows GBK console mojibake)
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', encoding='utf-8')

# 路径: tools/migrate_global_node_id.py → skills/lx_node_id.py
SKILLS_DIR = Path(__file__).resolve().parent.parent / 'skills'
sys.path.insert(0, str(SKILLS_DIR))
from lx_node_id import (
    bit_reverse,
    level_first_last,
    global_node_id_for_bfs_pos,
    five_tree_global_id,
    five_tree_own_bfs_pos,
)


def assign_global_node_ids_for_db(rows):
    """给 DB 行算 global_node_id 和 is_available.

    Args:
        rows: list of dicts with keys: dist_id, level (1-based, 1=根), parent_id, parent_line_id
              parent_line_id 1-5 for 5 叉业务 (None/0 for root)

    Returns:
        dict of dist_id -> {global_node_id, is_available, bfs_pos, actual_level}
    """
    # 1. 按 level 分组
    by_level = {}
    for r in rows:
        by_level.setdefault(r['level'], []).append(r)

    result = {}
    bfs_by_level = {}  # actual_level -> {dist_id: bfs_pos}

    # 2. L0 根 (level=1, 1 个)
    for r in by_level.get(1, []):
        result[r['dist_id']] = {
            'global_node_id': 1,
            'is_available': False,
            'bfs_pos': 0,
            'actual_level': 0,
        }
        bfs_by_level.setdefault(0, {})[r['dist_id']] = 0

    # 3. L1 父 (level=2, 4 个): 按 officev2 line 排 (parent_line_id 1-4), bfs_pos 0-3
    #    业务 (2026-08-05 用户拍板): 顺应按位反转排列, line 1 → BFS 0, line 2 → BFS 1, ...
    #    旧版按 dist_id 字典序排, 但 officev2 line 才是"槽位"语义 (line 1-5), 应按 line 排
    #    例: 郜翠微 (line 2) BFS pos 1 → gnode 4, 李苗 (line 3) BFS pos 2 → gnode 3
    l1_rows = sorted(by_level.get(2, []), key=lambda r: (r['parent_line_id'] or 0, r['dist_id']))
    for i, r in enumerate(l1_rows):
        result[r['dist_id']] = {
            'global_node_id': global_node_id_for_bfs_pos(1, i),
            'is_available': False,
            'bfs_pos': i,
            'actual_level': 1,
        }
        bfs_by_level.setdefault(1, {})[r['dist_id']] = i

    # 4. L_k 节点 (level >= 3): 按 (parent_bfs, line) 排
    for level in range(3, 14):  # DB level 1-13, 实际 L0-L12
        actual_level = level - 1
        l_rows = by_level.get(level, [])
        if not l_rows:
            continue

        def sort_key(r):
            parent_bfs = bfs_by_level.get(actual_level - 1, {}).get(r['parent_id'], 0)
            line = r['parent_line_id'] or 0
            return (parent_bfs, line)

        l_sorted = sorted(l_rows, key=sort_key)
        for i, r in enumerate(l_sorted):
            parent_bfs = bfs_by_level.get(actual_level - 1, {}).get(r['parent_id'], 0)
            line = r['parent_line_id'] or 0
            if line and 1 <= line <= 5:
                gid, avail = five_tree_global_id(actual_level - 1, line, parent_bfs)
            else:
                # 无 line 信息 (defensive), 走 tree 公式
                gid = global_node_id_for_bfs_pos(actual_level, i)
                avail = False
            result[r['dist_id']] = {
                'global_node_id': gid,
                'is_available': avail,
                'bfs_pos': i,
                'actual_level': actual_level,
            }
            bfs_by_level.setdefault(actual_level, {})[r['dist_id']] = i

    return result


def migrate(db_path: str = None, dry_run: bool = False):
    """加 global_node_id 列, 按 BFS 顺序填值.

    Args:
        db_path: SQLite DB 路径, 默认 data/rewarddb.db
        dry_run: True 只 print, 不写盘
    """
    if db_path is None:
        db_path = str(Path(__file__).resolve().parent.parent / 'data' / 'rewarddb.db')

    if not os.path.exists(db_path):
        print(f'ERROR: DB not found: {db_path}')
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 1. 检查列是否存在
    cur.execute("PRAGMA table_info(original_tree_nodes)")
    columns = [r[1] for r in cur.fetchall()]
    has_gid = 'global_node_id' in columns

    if not has_gid:
        print(f'[1/3] 加 global_node_id 列...')
        if not dry_run:
            cur.execute("ALTER TABLE original_tree_nodes ADD COLUMN global_node_id INTEGER")
        else:
            print('  (dry-run, skip)')
    else:
        print(f'[1/3] global_node_id 列已存在, 跳过 ADD COLUMN')

    # 2. 读所有节点
    print(f'[2/3] 读节点, 按 BFS 顺序算 global_node_id...')
    cur.execute("""
        SELECT dist_id, name, level, parent_id, parent_line_id
        FROM original_tree_nodes
        ORDER BY level, parent_id, parent_line_id
    """)
    rows = []
    for r in cur.fetchall():
        rows.append({
            'dist_id': r[0],
            'name': r[1],
            'level': r[2],
            'parent_id': r[3],
            'parent_line_id': r[4],
        })

    assignments = assign_global_node_ids_for_db(rows)

    # 3. 写回 DB
    print(f'[3/3] 写回 {len(assignments)} 节点...')
    if not dry_run:
        for dist_id, info in assignments.items():
            cur.execute(
                "UPDATE original_tree_nodes SET global_node_id = ? WHERE dist_id = ?",
                (info['global_node_id'], dist_id)
            )
        conn.commit()
    else:
        print('  (dry-run, skip)')

    # Stats
    by_level_count = {}  # actual_level -> count
    avail_count = 0
    for r in rows:
        al = r['level'] - 1
        by_level_count[al] = by_level_count.get(al, 0) + 1
    for info in assignments.values():
        if info['is_available']:
            avail_count += 1

    print()
    print('=== Migration 完成 ===')
    print(f'  总节点: {len(rows)}')
    print(f'  5 叉 line 3-5 available 节点: {avail_count}')
    print(f'  按层:')
    for al in sorted(by_level_count.keys()):
        first, last, count = level_first_last(al)
        print(f'    L{al}: {by_level_count[al]} 节点 (tree 公式 first={first}, last={last}, count={count})')

    conn.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='PR #24: 加 global_node_id 列 + 按位反转填值')
    parser.add_argument('--db-path', help='SQLite DB 路径 (默认 data/rewarddb.db)')
    parser.add_argument('--dry-run', action='store_true', help='只 print, 不写盘')
    args = parser.parse_args()
    migrate(db_path=args.db_path, dry_run=args.dry_run)
