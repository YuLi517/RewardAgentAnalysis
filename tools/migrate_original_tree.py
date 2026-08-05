# -*- coding: utf-8 -*-
"""
migrate_original_tree.py —— 原版网体数据从 JSON 迁到 SQLite
================================================================

业务背景 (2026-08-05):
  - 原版网体 (303 节点 12 层深) 之前存 json/original_tree.json 文件
  - PR #15 升级: 树形数据进 DB 统一管理
  - /api/original_tree/data 端点从 DB 读, 删 JSON 依赖
  - PR #17 升级: interactive CLI, 默认询问清空范围, 让客户确认后再执行

表 schema (字段对齐 JSON 节点, snake_case, 25 列, 见 PR #15):
  - id, dist_id (UNIQUE), name, level, max_lines,
  - parent_id (FK 自身, 顶层 = NULL — 用户拍板 "最上面的 Root 节点算 L0"),
  - parent_line_id, business_level, gold, iix, rank, status, activity_status_id,
  - pv, org_pv, personal_customer_pv,
  - has_subscription, is_qualified, status_color, visibility, available,
  - rows, max_rows, created_at, updated_at

迁移步骤:
  1. 解析 CLI 参数 (--yes / --net / --db-path / --json-path)
  2. 确认 DB / JSON 路径
  3. interactive: 询问清空范围 (全清 5 张业务表 / 只清原版网体 / 取消)
  4. CREATE TABLE IF NOT EXISTS + 索引 (幂等)
  5. 清空选定表 (DELETE FROM, 幂等)
  6. 读 json/original_tree.json
  7. 递归 BFS 插入所有节点 (顶层 parent_id = NULL)
  8. 输出 stats (节点数, depth 分布, businessLevel 分布, FK 完整性验证)

用法 (详见 README.md §"数据迁移"):
  # interactive 模式 (默认), 询问清空范围
  python tools/migrate_original_tree.py

  # 自动模式 — 全清 5 张业务表 (推荐 UAT 客户)
  python tools/migrate_original_tree.py --yes

  # 自动模式 — 只清原版网体 (不动其他业务表)
  python tools/migrate_original_tree.py --net

  # 自定义路径
  python tools/migrate_original_tree.py --db-path /path/to/db.db --json-path /path/to/tree.json
"""
import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# 业务表清单 (PR #17 用户拍板: 全 DB 清)
BUSINESS_TABLES = [
    ("original_tree_nodes", "原版网体节点 (303 节点 12 层)"),
    ("members", "5 叉树 commission 成员"),
    ("pv_ledger", "业务 PV 流水"),
    ("commission_periods", "业务周期 (Sun-Fri + 补录窗口)"),
    ("order_items", "下单管理 (PR #70)"),
]

# JSON 字段 -> DB 字段 (snake_case) + 类型转换
def _bool_yesno(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    return str(v).upper() == 'YES'


def _bool_tf(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    return str(v).upper() == 'T'


def _int_or_none(v):
    if v is None or v == '':
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _str_or_none(v):
    if v is None:
        return None
    s = str(v)
    return s if s else None


def node_to_row(node, parent_id, now):
    return (
        _str_or_none(node.get('distId')),                 # dist_id
        _str_or_none(node.get('name')),                   # name
        _int_or_none(node.get('level')),                  # level
        _int_or_none(node.get('maxLines')),               # max_lines
        parent_id,                                        # parent_id
        _int_or_none(node.get('parentLineId')),           # parent_line_id
        _str_or_none(node.get('businessLevel')),          # business_level
        _bool_yesno(node.get('gold')),                    # gold
        _bool_yesno(node.get('iix')),                     # iix
        _str_or_none(node.get('rank')),                   # rank
        _str_or_none(node.get('status')),                 # status
        _str_or_none(node.get('activity_status_id')),     # activity_status_id
        _int_or_none(node.get('pv')),                     # pv
        _int_or_none(node.get('org_pv')),                 # org_pv
        _int_or_none(node.get('personal_customer_pv')),   # personal_customer_pv
        _bool_tf(node.get('has_subscription')),           # has_subscription
        _bool_tf(node.get('is_qualified')),               # is_qualified
        _str_or_none(node.get('status_color')),           # status_color
        _bool_yesno(node.get('visibility')),              # visibility
        _bool_yesno(node.get('available')),               # available
        _int_or_none(node.get('rows')),                   # rows
        _int_or_none(node.get('max_rows')),               # max_rows
        now,                                              # created_at
        now,                                              # updated_at
    )


INSERT_SQL = """
INSERT INTO original_tree_nodes (
    dist_id, name, level, max_lines, parent_id, parent_line_id,
    business_level, gold, iix, rank, status, activity_status_id,
    pv, org_pv, personal_customer_pv,
    has_subscription, is_qualified, status_color, visibility, available,
    rows, max_rows, created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS original_tree_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dist_id VARCHAR(64) UNIQUE NOT NULL,
            name VARCHAR(128),
            level INTEGER,
            max_lines INTEGER,
            parent_id VARCHAR(64),
            parent_line_id INTEGER,
            business_level VARCHAR(32),
            gold BOOLEAN,
            iix BOOLEAN,
            rank VARCHAR(64),
            status VARCHAR(16),
            activity_status_id VARCHAR(16),
            pv INTEGER,
            org_pv INTEGER,
            personal_customer_pv INTEGER,
            has_subscription BOOLEAN,
            is_qualified BOOLEAN,
            status_color VARCHAR(16),
            visibility BOOLEAN,
            available BOOLEAN,
            rows INTEGER,
            max_rows INTEGER,
            created_at FLOAT NOT NULL,
            updated_at FLOAT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_original_tree_parent
        ON original_tree_nodes(parent_id)
    """)
    conn.commit()


def get_table_counts(conn):
    """返回 {表名: 行数}, 表不存在返回 0"""
    out = {}
    for t, _ in BUSINESS_TABLES:
        try:
            cnt = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            out[t] = cnt
        except sqlite3.OperationalError:
            out[t] = 0
    return out


def ask_clear_scope(yes_flag, net_flag):
    """
    询问清空范围.
    返回: 'all' / 'net' / 'cancel'
    """
    if yes_flag:
        return 'all'
    if net_flag:
        return 'net'
    # interactive
    print()
    print("=" * 60)
    print("即将导入原版网体 JSON 到 DB. 请选择清空范围:")
    print("=" * 60)
    print()
    print("  [1] 全清 — 5 张业务表都清空 (推荐 UAT 客户)")
    print("      original_tree_nodes + members + pv_ledger")
    print("      + commission_periods + order_items")
    print()
    print("  [2] 只清原版网体 — 不动其他业务表")
    print("      (members / pv_ledger / commission_periods / order_items 保留)")
    print()
    print("  [3] 取消 — 退出不执行")
    print()
    while True:
        try:
            choice = input("请输入选项 [1/2/3]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 'cancel'
        if choice in ('1', '2', '3'):
            break
        print(f"  无效选项 '{choice}', 请重试")
    return {'1': 'all', '2': 'net', '3': 'cancel'}[choice]


def clear_tables(conn, scope):
    """scope: 'all' = 5 张业务表; 'net' = 只 original_tree_nodes"""
    tables = [t for t, _ in BUSINESS_TABLES] if scope == 'all' else ['original_tree_nodes']
    deleted = {}
    for t in tables:
        cur = conn.execute(f"DELETE FROM {t}")
        deleted[t] = cur.rowcount
    conn.commit()
    return deleted


def import_json(conn, json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        root = json.load(f)

    now = time.time()
    inserted = 0
    depth_count = {}

    def _walk(node, parent_id, depth):
        nonlocal inserted
        row = node_to_row(node, parent_id, now)
        conn.execute(INSERT_SQL, row)
        inserted += 1
        depth_count[depth] = depth_count.get(depth, 0) + 1
        new_parent_id = node.get('distId')
        for child in node.get('children', []):
            _walk(child, new_parent_id, depth + 1)

    _walk(root, None, 0)
    conn.commit()
    return inserted, depth_count


def main():
    ap = argparse.ArgumentParser(
        description="原版网体数据从 JSON 迁到 SQLite (interactive 模式, 询问清空范围)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例子:
  # interactive 模式 (默认, 询问清空范围)
  python tools/migrate_original_tree.py

  # 自动模式 — 全清 5 张业务表
  python tools/migrate_original_tree.py --yes

  # 自动模式 — 只清原版网体
  python tools/migrate_original_tree.py --net

  # 自定义路径
  python tools/migrate_original_tree.py --db-path D:/data/foo.db --json-path D:/data/tree.json
        """,
    )
    ap.add_argument("--yes", "-y", action="store_true",
                    help="自动 yes, 全清 5 张业务表 (跳过询问)")
    ap.add_argument("--net", action="store_true",
                    help="只清 original_tree_nodes (跳过询问, 其他业务表保留)")
    ap.add_argument("--db-path", default=None,
                    help="DB 路径, 默认 data/rewarddb.db")
    ap.add_argument("--json-path", default=None,
                    help="JSON 路径, 默认 json/original_tree.json")
    args = ap.parse_args()

    db_path = Path(args.db_path) if args.db_path else (PROJECT_ROOT / "data" / "rewarddb.db")
    json_path = Path(args.json_path) if args.json_path else (PROJECT_ROOT / "json" / "original_tree.json")

    print(f"DB:   {db_path}")
    print(f"JSON: {json_path}")
    if not db_path.exists():
        print(f"ERROR: DB 不存在: {db_path}")
        sys.exit(1)
    if not json_path.exists():
        print(f"ERROR: JSON 不存在: {json_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    try:
        # 1. 现状
        print("\n[1/5] 当前 DB 状态")
        counts = get_table_counts(conn)
        for t, desc in BUSINESS_TABLES:
            print(f"  {t:25s} {counts[t]:>6d} 行  -- {desc}")

        # 2. 询问清空范围
        scope = ask_clear_scope(args.yes, args.net)
        if scope == 'cancel':
            print("\n取消, 退出")
            return

        scope_label = "全清 (5 张业务表)" if scope == 'all' else "只清原版网体 (1 张表)"
        print(f"\n清空范围: {scope_label}")

        # 3. 建表
        print("\n[2/5] 建表 + 索引")
        ensure_table(conn)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(original_tree_nodes)").fetchall()]
        idx = [r[1] for r in conn.execute("PRAGMA index_list(original_tree_nodes)").fetchall()]
        print(f"  original_tree_nodes 字段数: {len(cols)}")
        print(f"  索引: {idx}")

        # 4. 清空
        print("\n[3/5] 清空表")
        deleted = clear_tables(conn, scope)
        for t, n in deleted.items():
            print(f"  DELETE FROM {t}: {n} 行")

        # 5. 导入
        print("\n[4/5] 导入 JSON")
        inserted, depth_count = import_json(conn, json_path)
        print(f"  插入: {inserted} 行")
        max_d = max(depth_count.keys()) if depth_count else 0
        print(f"  max depth: {max_d} (13 层 = 0..{max_d})")
        print(f"  depth 分布: {dict(sorted(depth_count.items()))}")

        biz_count = {}
        for r in conn.execute("SELECT business_level, COUNT(*) FROM original_tree_nodes GROUP BY business_level").fetchall():
            biz_count[r[0] or '(NULL)'] = r[1]
        print(f"  businessLevel 分布: {biz_count}")

        root_row = conn.execute("SELECT dist_id, name, level, business_level FROM original_tree_nodes WHERE parent_id IS NULL").fetchone()
        if root_row:
            print(f"  顶层 root: dist_id={root_row[0]}, name={root_row[1]}, level={root_row[2]}, business_level={root_row[3]}")

        # 6. 验证
        print("\n[5/5] 验证")
        cnt = conn.execute("SELECT COUNT(*) FROM original_tree_nodes").fetchone()[0]
        null_parents = conn.execute("SELECT COUNT(*) FROM original_tree_nodes WHERE parent_id IS NULL").fetchone()[0]
        child_count = conn.execute("SELECT COUNT(*) FROM original_tree_nodes WHERE parent_id IS NOT NULL").fetchone()[0]
        print(f"  总节点: {cnt}")
        print(f"  顶层 (parent_id IS NULL): {null_parents}")
        print(f"  有父: {child_count}")

        invalid = conn.execute("""
            SELECT COUNT(*) FROM original_tree_nodes child
            WHERE child.parent_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM original_tree_nodes p WHERE p.dist_id = child.parent_id)
        """).fetchone()[0]
        print(f"  FK 失效 (parent_id 不在表内): {invalid}")
        if invalid > 0:
            print(f"  WARNING: 有 {invalid} 个节点的 parent_id 在表内不存在")

        print("\nmigration 完成")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
