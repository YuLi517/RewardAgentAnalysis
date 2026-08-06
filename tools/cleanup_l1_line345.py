"""
补刀: 清 L1 父的 line 3-5 子 + 子孙.
业务规则: L1 = 4 大区 (line 1-4), 但 batch2000 v2 用 max_lines=5 加, 残留 line 3-5.
规则: root 4 大区 line 1-4 OK, L1 父的 line 3+ 子全部删除.
"""
import sqlite3
from collections import Counter

DB = r'D:\Projects\Reward\RewardAgentAnalysis\data\rewarddb.db'
c = sqlite3.connect(DB)
cur = c.cursor()

# 1. 找所有 L1 父 (root 的直接子, 4 个)
cur.execute("""
    SELECT m.member_dist_id, m.member_name, m.max_lines
    FROM members m
    WHERE m.parent_dist_id = (SELECT member_dist_id FROM members WHERE parent_dist_id IS NULL)
    ORDER BY m.slot_line_id
""")
l1_parents = cur.fetchall()
print(f'== L1 父: {len(l1_parents)} 个 ==')
for p in l1_parents:
    print(f'  {p[0]} {p[1]} max_lines={p[2]}')
print()

# 2. 找 line 3+ 子 + 子孙
to_delete = set()
for p_dist, p_name, p_ml in l1_parents:
    if p_ml > 4:
        # 找 line 3+ 子
        cur.execute("""
            WITH RECURSIVE line3_subtree AS (
                SELECT member_dist_id, parent_dist_id, slot_line_id
                FROM members WHERE parent_dist_id = ? AND slot_line_id >= 3
                UNION ALL
                SELECT m.member_dist_id, m.parent_dist_id, m.slot_line_id
                FROM members m JOIN line3_subtree d ON m.parent_dist_id = d.member_dist_id
            )
            SELECT member_dist_id FROM line3_subtree
        """, (p_dist,))
        for r in cur.fetchall():
            to_delete.add(r[0])

print(f'== L1 line 3+ 子 + 子孙待删除: {len(to_delete)} 个 ==')

# 3. 统计
cur.execute(f"""
    WITH RECURSIVE tree AS (
        SELECT member_dist_id, 0 AS depth FROM members WHERE parent_dist_id IS NULL
        UNION ALL
        SELECT m.member_dist_id, t.depth + 1 FROM members m JOIN tree t ON m.parent_dist_id = t.member_dist_id
    )
    SELECT depth, COUNT(*) FROM tree
    WHERE member_dist_id IN ({','.join('?' for _ in to_delete)})
    GROUP BY depth
    ORDER BY depth
""", list(to_delete))
print('按层分布:')
for d, n in cur.fetchall():
    print(f'  L{d}: {n}')
print()

# 4. 改 L1 max_lines=4
for p_dist, p_name, p_ml in l1_parents:
    if p_ml != 4:
        cur.execute("UPDATE members SET max_lines = 4 WHERE member_dist_id = ?", (p_dist,))
        print(f'  改 {p_dist} max_lines {p_ml} -> 4')

# 5. 删 ledger
ledger_count = 0
for d in to_delete:
    cur.execute("DELETE FROM pv_ledger WHERE member_dist_id = ?", (d,))
    ledger_count += cur.rowcount
print(f'删 ledger: {ledger_count} 条')

# 6. 删 members (深到浅)
cur.execute(f"""
    WITH RECURSIVE tree AS (
        SELECT member_dist_id, 0 AS depth FROM members WHERE parent_dist_id IS NULL
        UNION ALL
        SELECT m.member_dist_id, t.depth + 1 FROM members m JOIN tree t ON m.parent_dist_id = t.member_dist_id
    )
    SELECT member_dist_id, depth FROM tree
    WHERE member_dist_id IN ({','.join('?' for _ in to_delete)})
    ORDER BY depth DESC
""", list(to_delete))
del_members = cur.fetchall()
for d, _ in del_members:
    cur.execute("DELETE FROM members WHERE member_dist_id = ?", (d,))
print(f'删 members: {len(del_members)} 个')

c.commit()
print()

# 7. 验证
print('== 验证 ==')
cur.execute("SELECT COUNT(*) FROM members")
print(f'  members 总数: {cur.fetchone()[0]}')
cur.execute("SELECT COUNT(*) FROM pv_ledger")
print(f'  pv_ledger 总数: {cur.fetchone()[0]}')
# L1 父 max_lines 应都是 4
cur.execute("""
    SELECT m.member_dist_id, m.max_lines
    FROM members m
    WHERE m.parent_dist_id = (SELECT member_dist_id FROM members WHERE parent_dist_id IS NULL)
""")
for r in cur.fetchall():
    print(f'  L1 父 {r[0]} max_lines={r[1]} (期望 4)')
# 看 L2+ max_lines
cur.execute("""
    WITH RECURSIVE tree AS (
        SELECT member_dist_id, 0 AS depth FROM members WHERE parent_dist_id IS NULL
        UNION ALL
        SELECT m.member_dist_id, t.depth + 1 FROM members m JOIN tree t ON m.parent_dist_id = t.member_dist_id
    )
    SELECT COUNT(*) FROM tree t
    JOIN members m ON m.member_dist_id = t.member_dist_id
    WHERE t.depth >= 2 AND m.max_lines > 2
""")
print(f'  L2+ max_lines>2 残留: {cur.fetchone()[0]} (期望 0)')
# 看 line 3+ 非根子
cur.execute("""
    SELECT COUNT(*) FROM members WHERE parent_dist_id IS NOT NULL AND slot_line_id >= 3
""")
print(f'  line 3+ 非根子: {cur.fetchone()[0]} (期望 0)')

# 看一下 root 的 4 大区
cur.execute("""
    SELECT member_dist_id, member_name, slot_line_id
    FROM members
    WHERE parent_dist_id = (SELECT member_dist_id FROM members WHERE parent_dist_id IS NULL)
    ORDER BY slot_line_id
""")
print()
print('Root 4 大区:')
for r in cur.fetchall():
    print(f'  line {r[2]}: {r[0]} {r[1]}')
print()
print('Done.')
