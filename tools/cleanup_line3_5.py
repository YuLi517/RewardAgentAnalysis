"""
清理 L2+ 节点的 line 3-5 子 + 它们的子孙.
业务规则: L1 = 4 大区 (line 1-4), L2+ = 严格 2 叉 (line 1-2 only).
244 个 L2+ 父 max_lines>2 违规, 删除它们的 line 3+ 子树, 改 max_lines=2.
"""
import sqlite3
from collections import Counter

DB = r'D:\Projects\Reward\RewardAgentAnalysis\data\rewarddb.db'
c = sqlite3.connect(DB)
cur = c.cursor()

# 1. 找所有 L2+ 父 max_lines > 2
cur.execute("""
    WITH RECURSIVE tree AS (
        SELECT member_dist_id, parent_dist_id, slot_line_id, max_lines, 0 AS depth
        FROM members WHERE parent_dist_id IS NULL
        UNION ALL
        SELECT m.member_dist_id, m.parent_dist_id, m.slot_line_id, m.max_lines, t.depth + 1
        FROM members m JOIN tree t ON m.parent_dist_id = t.member_dist_id
    )
    SELECT member_dist_id, max_lines, depth
    FROM tree
    WHERE depth >= 2 AND max_lines > 2
    ORDER BY depth, member_dist_id
""")
violations = cur.fetchall()
print(f'== L2+ max_lines>2 违规节点: {len(violations)} 个 ==')
cnt = Counter(v[1] for v in violations)
for ml, n in sorted(cnt.items()):
    print(f'  max_lines={ml}: {n}')
print()

# 2. 对每个违规, 递归找 line 3+ 子孙
to_delete = set()
line3_first_count = Counter()
for v_dist, v_ml, v_depth in violations:
    cur.execute("""
        WITH RECURSIVE line3_subtree AS (
            SELECT member_dist_id, parent_dist_id, slot_line_id
            FROM members WHERE parent_dist_id = ? AND slot_line_id >= 3
            UNION ALL
            SELECT m.member_dist_id, m.parent_dist_id, m.slot_line_id
            FROM members m JOIN line3_subtree d ON m.parent_dist_id = d.member_dist_id
        )
        SELECT member_dist_id, slot_line_id FROM line3_subtree
    """, (v_dist,))
    for d, s in cur.fetchall():
        to_delete.add(d)
        if d not in to_delete or s == 3:
            line3_first_count[s] += 1

print(f'== 待删除节点 (line 3+ 子树): {len(to_delete)} 个 ==')
print()

# 3. 看 L1 是不是有 line 4+ children (应该 root 4 大区 line 1-4 OK, 但 5 不能有)
# 因为 root max_lines=5, 实际有 4 子 (line 1-4), line 5 空的
cur.execute("""
    SELECT member_dist_id, member_name, slot_line_id
    FROM members
    WHERE parent_dist_id = (SELECT member_dist_id FROM members WHERE parent_dist_id IS NULL)
    ORDER BY slot_line_id
""")
root_kids = cur.fetchall()
print(f'== Root 直接子: {len(root_kids)} 个 ==')
for k in root_kids:
    print(f'  line {k[2]}: {k[0]} {k[1]}')
print()

# 4. 验证待删除节点不包含 root
root = cur.execute("SELECT member_dist_id FROM members WHERE parent_dist_id IS NULL").fetchone()[0]
assert root not in to_delete, "ERROR: 试图删除 root!"
print(f'确认: root {root} 不在待删除列表')
print()

# 5. 收集待删除节点的 ledger
cur.execute(f"""
    SELECT COUNT(*), member_dist_id FROM pv_ledger
    WHERE member_dist_id IN ({','.join('?' for _ in to_delete)})
    GROUP BY member_dist_id
""", list(to_delete))
ledger_counts = cur.fetchall()
total_ledger = sum(r[0] for r in ledger_counts)
print(f'== 待删除成员的 ledger 条数: {total_ledger} (覆盖 {len(ledger_counts)} 个成员) ==')
print()

# 6. 统计待删除节点的子孙分布
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
print('== 待删除节点按层分布 ==')
for d, n in cur.fetchall():
    print(f'  L{d}: {n}')
print()

# 7. 开干
print('== 开始删除 ==')
# 7a. 删 ledger
for d in to_delete:
    cur.execute("DELETE FROM pv_ledger WHERE member_dist_id = ?", (d,))
print(f'  删 ledger: {total_ledger} 条')
# 7b. 删 members (深到浅, 因为 FK)
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
print(f'  删 members: {len(del_members)} 个')
# 7c. 改 max_lines=2 (只对未删除的违规)
violations_survive = [v[0] for v in violations if v[0] not in to_delete]
for v in violations_survive:
    cur.execute("UPDATE members SET max_lines = 2 WHERE member_dist_id = ?", (v,))
print(f'  改 max_lines=2: {len(violations_survive)} 个 (删除中那些不用改)')

c.commit()
print()
print('== 验证 ==')
# 8. 验证
cur.execute("SELECT COUNT(*) FROM members")
print(f'  members 总数: {cur.fetchone()[0]} (原 {cur.fetchone()})')
cur.execute("SELECT COUNT(*) FROM pv_ledger")
print(f'  pv_ledger 总数: {cur.fetchone()[0]}')
# 看还有没有 L2+ max_lines>2
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
# 看还有没有 line 3+ 子 (除 root)
cur.execute("""
    SELECT COUNT(*) FROM members WHERE parent_dist_id IS NOT NULL AND slot_line_id >= 3
""")
print(f'  line 3+ 非根子: {cur.fetchone()[0]} (期望 0)')
print()
print('Done.')
