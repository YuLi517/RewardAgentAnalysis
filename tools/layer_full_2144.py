"""
L0-L9 全满 + L10 部分填充 = 2144.
阶段 1 (添加): L7 224->256 (+32), L8 240->512 (+272), L9 432->1024 (+592). 共 +896
阶段 2 (删除): L11-L14 全删 (158+68+12+4=242), L10 752->99 (删 653). 共 -895
净: +1, 总 2143 -> 2144.
"""
import sqlite3

DB = r'D:\Projects\Reward\RewardAgentAnalysis\data\rewarddb.db'
c = sqlite3.connect(DB)
cur = c.cursor()

def get_max_n():
    cur.execute("SELECT MAX(CAST(SUBSTR(member_dist_id, 10) AS INTEGER)) FROM members WHERE member_dist_id LIKE 'N5637590.%'")
    return cur.fetchone()[0]
def get_max_a():
    cur.execute("SELECT MAX(CAST(SUBSTR(member_name, 2) AS INTEGER)) FROM members WHERE member_name GLOB 'A[0-9]*'")
    return cur.fetchone()[0] or 0
def layer_size(depth):
    cur.execute('''
        WITH RECURSIVE tree AS (
            SELECT member_dist_id, 0 AS depth FROM members WHERE parent_dist_id IS NULL
            UNION ALL
            SELECT m.member_dist_id, t.depth + 1 FROM members m JOIN tree t ON m.parent_dist_id = t.member_dist_id
        )
        SELECT COUNT(*) FROM tree WHERE depth = ?
    ''', (depth,))
    return cur.fetchone()[0]
def parents_at(depth):
    """节点 whose children are at depth `depth`, 即节点本身在 depth-1"""
    cur.execute('''
        WITH RECURSIVE tree AS (
            SELECT member_dist_id, 0 AS depth FROM members WHERE parent_dist_id IS NULL
            UNION ALL
            SELECT m.member_dist_id, t.depth + 1 FROM members m JOIN tree t ON m.parent_dist_id = t.member_dist_id
        )
        SELECT member_dist_id FROM tree WHERE depth = ? ORDER BY member_dist_id
    ''', (depth - 1,))
    return [r[0] for r in cur.fetchall()]

next_n = get_max_n() + 1
next_a = get_max_a() + 1

# 重建 parent_kids
cur.execute('SELECT member_dist_id, parent_dist_id, slot_line_id FROM members WHERE parent_dist_id IS NOT NULL')
parent_kids = {}
for did, pid, sl in cur.fetchall():
    parent_kids.setdefault(pid, []).append((sl, did))

print('== 阶段 1: 填 L7, L8, L9 到 2^k 全满 ==')
for target_depth, target_size in [(7, 256), (8, 512), (9, 1024)]:
    cur_size = layer_size(target_depth)
    need = target_size - cur_size
    print(f'\nL{target_depth}: {cur_size} -> {target_size} (需加 {need})')
    if need <= 0:
        print(f'  跳过 (已满)')
        continue
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
    print(f'  加了 {added}')

print()
print('== 阶段 2: 删 L11-L14 全删 + L10 减到 99 ==')
# 2a: 删 L11+ (cascading)
cur.execute('''
    WITH RECURSIVE tree AS (
        SELECT member_dist_id, 0 AS depth FROM members WHERE parent_dist_id IS NULL
        UNION ALL
        SELECT m.member_dist_id, t.depth + 1 FROM members m JOIN tree t ON m.parent_dist_id = t.member_dist_id
    )
    SELECT member_dist_id, depth FROM tree WHERE depth >= 11
    ORDER BY depth DESC
''')
l11_plus = cur.fetchall()
print(f'\n  L11+: {len(l11_plus)} 个')
for did, d in l11_plus:
    cur.execute("DELETE FROM pv_ledger WHERE member_dist_id = ?", (did,))
    cur.execute("DELETE FROM members WHERE member_dist_id = ?", (did,))
c.commit()
print(f'  删了 {len(l11_plus)} 个')

# 2b: L10 减到 99
cur.execute('''
    WITH RECURSIVE tree AS (
        SELECT member_dist_id, parent_dist_id, slot_line_id, 0 AS depth FROM members WHERE parent_dist_id IS NULL
        UNION ALL
        SELECT m.member_dist_id, m.parent_dist_id, m.slot_line_id, t.depth + 1 FROM members m JOIN tree t ON m.parent_dist_id = t.member_dist_id
    )
    SELECT member_dist_id FROM tree WHERE depth = 10 ORDER BY parent_dist_id, slot_line_id
''')
l10_all = [r[0] for r in cur.fetchall()]
print(f'\n  L10: {len(l10_all)} 个 (需保留 99)')
to_delete_l10 = l10_all[99:]
print(f'  删 {len(to_delete_l10)} 个 L10')
for did in to_delete_l10:
    cur.execute("DELETE FROM pv_ledger WHERE member_dist_id = ?", (did,))
    cur.execute("DELETE FROM members WHERE member_dist_id = ?", (did,))
c.commit()

print()
print('== 验证 ==')
cur.execute('SELECT COUNT(*) FROM members')
print(f'  members 总数: {cur.fetchone()[0]} (期望 2144)')
cur.execute('SELECT COUNT(*) FROM pv_ledger')
print(f'  pv_ledger 总数: {cur.fetchone()[0]}')

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

# 严格 2 叉验证
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
for v in viols[:5]:
    print(f'    {v[0]} L{v[1]} 子数 {v[2]}')
