"""scenarios 表 migration 工具 (PR3 Task 2)

Idempotent: 重复调用不报错, 不删除已有数据.

业务 (P1 PR3, 2026-08-07):
  - 大重构阶段 3: 运营系统 → 分析推理系统 (招商/路演实时计算器)
  - scenarios 表存客户路演场景 (4 组参数拍平 40 列)
  - PR3 Task 1 加 Scenario ORM (40 列), PR3 Task 2 加 migration 工具
  - PR3 Task 3 加 repository.py (save/load/list/delete)
  - PR3 Task 4 加 scenario_routes.py (3 个 FastAPI 路由)

设计要点:
  1. 用 SQLAlchemy 2.x ORM 风格 (跟 models.py:Scenario 保持一致)
  2. inspect 检测表存在, 重复调用跳过
  3. 数据库 URL 走 live database.py:engine (跟其他 migration 工具一致)
"""
import os
import sys

# 让 main.py 跟 database.py 可被导入 (跟其他 tools/migrate_*.py 一致)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import inspect


def upgrade(engine):
    """创 scenarios 表 (40 列, 跟 models.py:Scenario 一致)

    重复调用跳过 (idempotent), 不删除已有数据.

    Args:
        engine: SQLAlchemy Engine 实例
    """
    insp = inspect(engine)
    if "scenarios" in insp.get_table_names():
        print("[migrate] scenarios 表已存在, 跳过")
        return

    # 用 ORM 创表 (跟 models.py:Scenario 保持一致, 避免 raw SQL 跟 ORM 漂移)
    from models import Base, Scenario
    Scenario.__table__.create(bind=engine, checkfirst=True)
    print("[migrate] scenarios 表创建成功 (40 列)")


if __name__ == "__main__":
    # CLI 入口: 跟其他 migration 工具一致
    from database import engine
    upgrade(engine)
