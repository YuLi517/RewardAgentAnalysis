"""
3 步回到 2144 节点:
1. 修 L1=5 异常: 删 N5637590.8 (A7) + 子孙; 改 A8077082.1 / A8121400.1 max_lines=4
2. 继续 BFS 填 L2-L9 到 2^k 全满
3. 删 L10+ 多余只留 99
"""
import sqlite3

DB = r'D:\Projects\Reward\RewardAgentAnalysis\data\rewarddb.db'
c = sqlite3.connect(DB)
cur = c.cursor()

# 备份
import shutil
shutil.copy2(DB, DB + '.bak-2026-08-06-pre-restore-2144')
print('备份 done')

def get_layer_size(depth):
    cur.execute('''
        WITH RECURSIVE tree AS (
            SELECT member_dist_id, 0 AS depth FROM members WHERE parent_dist_id IS NULL
            UNION ALL
            SELECT m.member_dist_id, t.depth + 1 FROM members m JOIN tree t ON m.parent_dist_id = t.member_dist_id
        )
        SELECT COUNT(*) FROM tree WHERE depth = ?
    ''', (depth,))
    return cur.fetchone()[0]

print(f'当前: 总 1384, L1=5 (异常)')

# Step 1: 修 L1=5 异常
print('\n== Step 1: 修 L1=5 异常 ==')
# 1a. 删 N5637590.8 (A7) + 子孙
print('  1a. 删 L1 line 5 子树 (N5637590.8 A7 + 子孙)...')
cur.execute('''
    WITH RECURSIVE subtree AS (
        SELECT member_dist_id, 0 AS depth FROM members WHERE member_dist_id = 'N5637590.8'
        UNION ALL
        SELECT m.member_dist_id, s.depth + 1 FROM members m JOIN subtree s ON m.parent_dist_id = s.member_dist_id
    )
    SELECT member_dist_id, depth FROM subtree ORDER BY depth DESC
''')
l5_tree = cur.fetchall()
print(f'    N5637590.8 子树: {len(l5_tree)} 个节点')
for did, d in l5_tree:
    cur.execute("DELETE FROM pv_ledger WHERE member_dist_id = ?", (did,))
    cur.execute("DELETE FROM members WHERE member_dist_id = ?", (did,))
c.commit()
print(f'    删了 {len(l5_tree)} 个')

# 1b. 改 L1 父 max_lines=4 (跟 root 4 大区对齐)
print('  1b. 改 L1 父 max_lines=4...')
for did in ['A8077082.1', 'A8822227.1', 'A8121400.1', 'N5630292.1']:
    cur.execute('UPDATE members SET max_lines = 4 WHERE member_dist_id = ?', (did,))
c.commit()
print('    4 个 L1 父 max_lines=4 done')

# 验证
cur.execute('SELECT COUNT(*) FROM members')
print(f'  现在: {cur.fetchone()[0]} 节点')
cur.execute('''
    WITH RECURSIVE tree AS (
        SELECT member_dist_id, 0 AS depth FROM members WHERE parent_dist_id IS NULL
        UNION ALL
        SELECT m.member_dist_id, t.depth + 1 FROM members m JOIN tree t ON m.parent_dist_id = t.member_dist_id
    )
    SELECT depth, COUNT(*) FROM tree GROUP BY depth ORDER BY depth
''')
print('  按层:')
for d, n in cur.fetchall():
    print(f'    L{d}: {n}')

# Step 2: 填 L2-L9 到 2^k 全满
print('\n== Step 2: 填 L2-L9 到 2^k 全满 ==')
def get_max_n():
    cur.execute("SELECT MAX(CAST(SUBSTR(member_dist_id, 10) AS INTEGER)) FROM members WHERE member_dist_id LIKE 'N5637590.%'")
    return cur.fetchone()[0]
def get_max_a():
    cur.execute("SELECT MAX(CAST(SUBSTR(member_name, 2) AS INTEGER)) FROM members WHERE member_name GLOB 'A[0-9]*'")
    return cur.fetchone()[0] or 0
def parents_at(depth):
    cur.execute('''
        WITH RECURSIVE tree AS (
            SELECT member_dist_id, 0 AS depth FROM members WHERE parent_dist_id IS NULL
            UNION ALL
            SELECT m.member_dist_id, t.depth + 1 FROM members m JOIN tree t ON m.parent_dist_id = t.member_dist_id
        )
        SELECT member_dist_id FROM tree WHERE depth = ? ORDER BY member_dist_id
    ''', (depth - 1,))
    return [r[0] for r in cur.fetchall()]

# 重建 parent_kids
cur.execute('SELECT member_dist_id, parent_dist_id, slot_line_id FROM members WHERE parent_dist_id IS NOT NULL')
parent_kids = {}
for did, pid, sl in cur.fetchall():
    parent_kids.setdefault(pid, []).append((sl, did))

next_n = get_max_n() + 1
next_a = get_max_a() + 1

for target_depth, target_size in [(2, 8), (3, 16), (4, 32), (5, 64), (6, 128), (7, 256), (8, 512), (9, 1024)]:
    cur_size = get_layer_size(target_depth)
    need = target_size - cur_size
    if need <= 0:
        print(f'  L{target_depth}: {cur_size} (已满)')
        continue
    print(f'  L{target_depth}: {cur_size} -> {target_size} (需加 {need})')
    parents = parents_at(target_depth)
    added = 0
    for p in parents:
        if added >= need:
            break
        existing = parent_kids.get(p, [])
        used = set(sl for sl, _ in existing)
        for slot in [1, 2]:
            if slot in used:
                continue
            if added >= need:
                break
            new_dist = f'N5637590.{next_n}'
            new_name = f'A{next_a}'
            next_n += 1
            next_a += 1
            cur.execute('''
                INSERT INTO members (member_dist_id, member_name, parent_dist_id, slot_line_id, max_lines, current_pv_balance, total_commission, created_period_id, last_period_id, role, created_at, updated_at)
                VALUES (?, ?, ?, ?, 2, 0, 0, '2026-08-02_W32', NULL, '消费股东', datetime('now'), datetime('now'))
            ''', (new_dist, new_name, p, slot))
            added += 1
            parent_kids.setdefault(p, []).append((slot, new_dist))
    c.commit()
    print(f'    加了 {added}')

# Step 3: 删 L10+ 多余只留 99
print('\n== Step 3: 删 L10+ 多余只留 99 ==')
# 3a. 删 L11+ cascade
cur.execute('''
    WITH RECURSIVE tree AS (
        SELECT member_dist_id, parent_dist_id, slot_line_id, 0 AS depth FROM members WHERE parent_dist_id IS NULL
        UNION ALL
        SELECT m.member_dist_id, m.parent_dist_id, m.slot_line_id, t.depth + 1 FROM members m JOIN tree t ON m.parent_dist_id = t.member_dist_id
    )
    SELECT member_dist_id, depth FROM tree WHERE depth >= 11 ORDER BY depth DESC
''')
l11_plus = cur.fetchall()
print(f'  L11+: {len(l11_plus)} 个')
for did, d in l11_plus:
    cur.execute("DELETE FROM pv_ledger WHERE member_dist_id = ?", (did,))
    cur.execute("DELETE FROM members WHERE member_dist_id = ?", (did,))
c.commit()
print(f'    删了 {len(l11_plus)} 个')

# 3b. L10 减到 99
cur.execute('''
    WITH RECURSIVE tree AS (
        SELECT member_dist_id, parent_dist_id, slot_line_id, 0 AS depth FROM members WHERE parent_dist_id IS NULL
        UNION ALL
        SELECT m.member_dist_id, m.parent_dist_id, m.slot_line_id, t.depth + 1 FROM members m JOIN tree t ON m.parent_dist_id = t.member_dist_id
    )
    SELECT member_dist_id FROM tree WHERE depth = 10 ORDER BY parent_dist_id, slot_line_id
''')
l10_all = [r[0] for r in cur.fetchall()]
to_del_l10 = l10_all[99:]
print(f'  L10: {len(l10_all)} 个 (留 99, 删 {len(to_del_l10)})')
for did in to_del_l10:
    cur.execute("DELETE FROM pv_ledger WHERE member_dist_id = ?", (did,))
    cur.execute("DELETE FROM members WHERE member_dist_id = ?", (did,))
c.commit()

# 验证
print('\n== 验证 ==')
cur.execute('SELECT COUNT(*) FROM members')
print(f'  members: {cur.fetchone()[0]} (期望 2144)')
cur.execute('SELECT COUNT(*) FROM pv_ledger')
print(f'  pv_ledger: {cur.fetchone()[0]}')
cur.execute('''
    WITH RECURSIVE tree AS (
        SELECT member_dist_id, 0 AS depth FROM members WHERE parent_dist_id IS NULL
        UNION ALL
        SELECT m.member_dist_id, t.depth + 1 FROM members m JOIN tree t ON m.parent_dist_id = t.member_dist_id
    )
    SELECT depth, COUNT(*) FROM tree GROUP BY depth ORDER BY depth
''')
print('  按层:')
total = 0
for d, n in cur.fetchall():
    total += n
    full = ' [全满 2^k]' if n in [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024] else ' [部分]'
    print(f'    L{d:2d}: {n:5d}{full}')
print(f'    合计: {total}')

# 严格 2 叉
cur.execute('''
    WITH RECURSIVE tree AS (
        SELECT member_dist_id, 0 AS depth FROM members WHERE parent_dist_id IS NULL
        UNION ALL
        SELECT m.member_dist_id, t.depth + 1 FROM members m JOIN tree t ON m.parent_dist_id = t.member_dist_id
    )
    SELECT t.member_dist_id, t.depth, COUNT(m.member_dist_id) as n
    FROM tree t
    LEFT JOIN members m ON m.parent_dist_id = t.member_dist_id
    WHERE t.depth >= 2
    GROUP BY t.member_dist_id, t.depth
    HAVING n > 2
''')
viols = cur.fetchall()
print(f'\n  L2+ 父 子数 > 2 违规: {len(viols)} (期望 0)')
