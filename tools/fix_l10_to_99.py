"""补 L10: 加 97 个新节点 (从 L9 父里找空 slot)"""
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

cur.execute('''
    WITH RECURSIVE tree AS (
        SELECT member_dist_id, parent_dist_id, slot_line_id, 0 AS depth FROM members WHERE parent_dist_id IS NULL
        UNION ALL
        SELECT m.member_dist_id, m.parent_dist_id, m.slot_line_id, t.depth + 1 FROM members m JOIN tree t ON m.parent_dist_id = t.member_dist_id
    )
    SELECT member_dist_id, parent_dist_id, slot_line_id FROM members WHERE parent_dist_id IS NOT NULL
''')
parent_kids = {}
for did, pid, sl in cur.fetchall():
    parent_kids.setdefault(pid, []).append((sl, did))

next_n = get_max_n() + 1
next_a = get_max_a() + 1

# 找 L9 父 (depth=8, children are at depth 9=L9 ... wait, depth 是 0-indexed)
# depth=9 是 L9 父 (即 L9 节点本身), 它们的子 = depth 10 (L10)
cur.execute('''
    WITH RECURSIVE tree AS (
        SELECT member_dist_id, 0 AS depth FROM members WHERE parent_dist_id IS NULL
        UNION ALL
        SELECT m.member_dist_id, t.depth + 1 FROM members m JOIN tree t ON m.parent_dist_id = t.member_dist_id
    )
    SELECT member_dist_id FROM tree WHERE depth = 9 ORDER BY member_dist_id
''')
l9_parents = [r[0] for r in cur.fetchall()]
print(f'L9 父: {len(l9_parents)} 个')

# 找 L9 父的 < 2 子, 加 L10
cur.execute('''
    WITH RECURSIVE tree AS (
        SELECT member_dist_id, 0 AS depth FROM members WHERE parent_dist_id IS NULL
        UNION ALL
        SELECT m.member_dist_id, t.depth + 1 FROM members m JOIN tree t ON m.parent_dist_id = t.member_dist_id
    )
    SELECT COUNT(*) FROM tree WHERE depth = 10
''')
cur_l10 = cur.fetchone()[0]
print(f'当前 L10: {cur_l10}')

# 加 L10 = 99 - cur_l10
need = 99 - cur_l10
print(f'L10 需加: {need}')

added = 0
for p in l9_parents:
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
print(f'加了 {added} 个')

# 验证
cur.execute('SELECT COUNT(*) FROM members')
print(f'\nmembers 总数: {cur.fetchone()[0]} (期望 2144)')

cur.execute('''
    WITH RECURSIVE tree AS (
        SELECT member_dist_id, 0 AS depth FROM members WHERE parent_dist_id IS NULL
        UNION ALL
        SELECT m.member_dist_id, t.depth + 1 FROM members m JOIN tree t ON m.parent_dist_id = t.member_dist_id
    )
    SELECT depth, COUNT(*) FROM tree GROUP BY depth ORDER BY depth
''')
print('按层:')
total = 0
for d, n in cur.fetchall():
    total += n
    full = ' [全满 2^k]' if n in [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024] else ' [部分]'
    print(f'  L{d}: {n}{full}')
print(f'  合计: {total}')

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
print(f'\nL2+ 父 子数 > 2 违规: {len(viols)} (期望 0)')
