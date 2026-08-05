# -*- coding: utf-8 -*-
r"""
init_root_member.py —— 一键把根节点 (王常军) 加到 members 表
==================================================================

背景:
    - 树根 "N5637590.1" (王常军) 之前不在 members 表, 因为根节点是网体起点, 不是被挂入的成员
    - 但 user 想在「成员列表」modal 看到根节点 (跟其他成员一样展示姓名/线/PV 等)
    - 成员列表期望 10 行 (root + 9 个挂入的成员)

幂等:
    - 如果 N5637590.1 已经在 members → 跳过
    - 如果不存在 → INSERT 一行

字段设置:
    - member_dist_id   = 'N5637590.1'
    - member_name      = '王常军'
    - parent_dist_id   = NULL     (根, 无父)
    - slot_line_id     = 0        (根, 无挂线; 跟 1..5 区分)
    - max_lines        = 5        (跟其他成员默认一致, 业务上根的 eff 由子节点决定)
    - current_pv_balance = 0      (根不参与 PV 累积)
    - total_commission   = 0.0
    - created_period_id  = '2026-W28' (比最早成员 7000001 早一期, 表示"早就在")
    - last_period_id     = NULL

跑法:
    python tools/init_root_member.py
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import SessionLocal
from models import Member
from repository import MemberRepository


ROOT_DIST_ID = "N5637590.1"
ROOT_NAME = "王常军"
ROOT_CREATED_PERIOD = "2026-W28"  # 比 N-7000001 早 (它是 W29)


def main():
    db = SessionLocal()
    try:
        repo = MemberRepository(db)
        existing = repo.get_by_dist_id(ROOT_DIST_ID)
        if existing:
            print(f"✓ Root 已在 members (id={existing.id}, name='{existing.member_name}')")
            print(f"  - parent_dist_id    = {existing.parent_dist_id!r}")
            print(f"  - slot_line_id      = {existing.slot_line_id}")
            print(f"  - current_pv_balance= {existing.current_pv_balance}")
            print(f"  - created_period_id = {existing.created_period_id!r}")
            return 0

        root = Member(
            member_dist_id=ROOT_DIST_ID,
            member_name=ROOT_NAME,
            parent_dist_id=None,    # 根, 无父
            slot_line_id=0,         # 根, 无挂线 (1..5 是挂线编号)
            max_lines=5,
            current_pv_balance=0,
            total_commission=0.0,
            created_period_id=ROOT_CREATED_PERIOD,
            last_period_id=None,
        )
        db.add(root)
        db.commit()
        db.refresh(root)
        print(f"✓ 已插入根节点: id={root.id}, dist_id={root.member_dist_id!r}, name='{root.member_name}'")
        return 0
    except Exception as e:
        db.rollback()
        print(f"✗ 失败: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
