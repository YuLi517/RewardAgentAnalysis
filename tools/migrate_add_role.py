# -*- coding: utf-8 -*-
"""
migrate_add_role.py — PR #41/42 加 member.role 列的幂等 migration
====================================================================

业务:
    - 7 种角色 (消费股东/预备合伙人/合伙人员工/初级管理/中级管理/高级管理/Inactive)
    - 加入时人工选 (/add 命令), 后续 /role 改
    - DB 列 NOT NULL default '消费股东' (业务默认最普通角色)
    - PR #42: DB 存全名 label (中文), 不用 enum key

幂等性:
    - 检查 members 表有没有 role 列, 没有就 ADD COLUMN
    - PR #41 enum key 映射: consumer → 消费股东, mid → 中级管理合伙人, etc.
      (PR #42: 新建库直接是中文 label, 不需要 mapping)
    - 给所有现有 member 兜底设 role='消费股东'
    - 重复运行安全 (什么都不做)

用法:
    cd D:\\Projects\\Reward\\RewardAgentAnalysis
    python tools/migrate_add_role.py
"""
import os
import sys

# ★ 2026-07-16 fix: PowerShell 控制台 GBK 编码, Python print 含中文/unicode 报错
#   强制 stdout 用 utf-8, 让 ✓/✗ 等 unicode 字符能正常输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import create_engine, text, inspect

# 让 main.py 跟 database.py 可被导入
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database import DB_URL  # noqa: E402


# ★ 2026-07-16 PR #42: enum key → 中文 label 映射 (PR #41 旧数据迁移用)
#   - 新建库: 不会有 enum key, 跳过这一步
#   - PR #41 旧库: 把 enum key 转成 label
ENUM_KEY_TO_LABEL = {
    "consumer": "消费股东",
    "reserve_partner": "预备合伙人",
    "employee": "合伙人员工",
    "junior": "初级管理合伙人",
    "mid": "中级管理合伙人",
    "senior": "高级管理合伙人",
    "inactive": "Inactive",
}


def migrate() -> None:
    """幂等 migration: 加 members.role 列 + enum key → label 映射 + 现有数据填默认值"""
    engine = create_engine(DB_URL, future=True)
    insp = inspect(engine)
    table_names = insp.get_table_names()
    if "members" not in table_names:
        print("[migrate_add_role] members 表不存在, 跳过 (应该不会发生)")
        return

    cols = {c["name"]: c for c in insp.get_columns("members")}
    if "role" in cols:
        print("[migrate_add_role] members.role 列已存在, 跑 enum key → label 映射 (PR #42)")

        # PR #42: enum key → label 映射 (PR #41 旧数据)
        with engine.begin() as conn:
            total_migrated = 0
            for enum_key, label in ENUM_KEY_TO_LABEL.items():
                result = conn.execute(text(
                    "UPDATE members SET role = :label WHERE role = :enum_key"
                ).bindparams(label=label, enum_key=enum_key))
                if result.rowcount > 0:
                    print(f"  {enum_key} → {label}: {result.rowcount} 行")
                    total_migrated += result.rowcount
            if total_migrated == 0:
                print("  (无 enum key 需迁移, DB 已是中文 label)")

            # 兜底: NULL/空 role 设为默认
            result = conn.execute(text(
                "UPDATE members SET role = '消费股东' WHERE role IS NULL OR role = ''"
            ))
            print(f"[migrate_add_role] NULL/空 role 兜底更新: {result.rowcount} 行")
        return

    # 加列 (SQLite 限制: NOT NULL 必须有 DEFAULT)
    print("[migrate_add_role] 添加 members.role 列...")
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE members ADD COLUMN role VARCHAR(64) NOT NULL DEFAULT '消费股东'"
        ))
        # 加索引 (跟 model 里 index=True 对应)
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_members_role ON members(role)"
        ))
        print("[migrate_add_role] ✓ role 列 + 索引 已加")

        # 现有 member 全部默认 消费股东 (DEFAULT 已经处理, 显式跑一次确保)
        result = conn.execute(text(
            "UPDATE members SET role = '消费股东' WHERE role IS NULL OR role = ''"
        ))
        print(f"[migrate_add_role] 现有 member 默认 role: {result.rowcount} 行")

    print("[migrate_add_role] ✓ 迁移完成")


if __name__ == "__main__":
    migrate()
