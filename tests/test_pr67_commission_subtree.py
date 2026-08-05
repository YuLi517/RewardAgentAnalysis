"""PR #67 修复 + PR #68 翻案: commission preview 渲染层对齐算法层

PR #67 修复 (2026-07-24): 渲染层 ownBasic 用递归子区 PV
- _build 加 subtreePv 字段 = own + sum(子节点 subtreePv) 递归累加
- real_child_pvs = [cd.subtreePv for cd in child_dicts]
- 跟算法层 PR #66 对齐

PR #68 翻案 (2026-07-27): own 不参与 commission 配对
- 旧 (PR #67): ownBasic = (own_pair + sub_pair) × 0.15 — own 参与配对
- 新 (PR #68): ownBasic = sub_pair × 0.15 — own 不参与, 只 5 子区 P/L 配对
- 业务截图: A (own=1500, 5 子区 C=1500) 旧算法算 ¥150 错, 新算法算 ¥0 ✓

业务场景 (用户截图, 2026-07-24 / 2026-07-27):
- ABCD 4 member 树: root -> A(L1) + B(L2), A -> C, B -> D
- PV: A=1500, B=1000, C=1500, D=1000

PR #68 业务期望:
- root: own=0, 5 子区 P=3000, L=2000, pair=2000, ownBasic=300 ✓
- A: own=1500, 5 子区 P=1500 (C 递归), L=0, pair=0, ownBasic=0 ✓
- B: own=1000, 5 子区 P=1000 (D 递归), L=0, pair=0, ownBasic=0 ✓
- C/D: 叶子, ownBasic=0

PR #67 老期望 (已翻案):
- A ownBasic = 225 (own_pair=1500) — 错
- B ownBasic = 150 (own_pair=1000) — 错
- root commissionPreview = 356.25 (ownBasic 300 + pair 56.25 from A/B 7-gen) — 错
"""
import sys
import time
from pathlib import Path

WT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WT))

from database import init_db, SessionLocal
from models import Member, PVLedger, CommissionPeriod
from main import _build_tree_from_db
from skills.period import get_current_period_id


def _reset_db():
    """清 DB + 重建 root"""
    init_db()
    db = SessionLocal()
    try:
        db.query(PVLedger).delete()
        db.query(CommissionPeriod).delete()
        db.query(Member).delete()
        db.commit()
    finally:
        db.close()
    db = SessionLocal()
    try:
        ts = time.time()
        period_id = get_current_period_id()
        db.add(Member(
            member_dist_id="N5637590.1", member_name="王常军", slot_line_id=0,
            max_lines=5, parent_dist_id=None, created_period_id=period_id,
            current_pv_balance=0, total_commission=0.0, role="consumer",
            created_at=ts, updated_at=ts,
        ))
        db.commit()
    finally:
        db.close()


def setup_function(function):
    _reset_db()


def _current_period():
    return get_current_period_id()


def _build_ABCD_tree(db, period_id):
    """建用户截图的树"""
    ts = time.time()
    db.add(Member(member_dist_id="N5637590.2", member_name="A", slot_line_id=1,
                  max_lines=5, parent_dist_id="N5637590.1", created_period_id=period_id,
                  current_pv_balance=0, total_commission=0.0, role="consumer",
                  created_at=ts, updated_at=ts))
    db.flush()
    db.add(Member(member_dist_id="N5637590.3", member_name="B", slot_line_id=2,
                  max_lines=5, parent_dist_id="N5637590.1", created_period_id=period_id,
                  current_pv_balance=0, total_commission=0.0, role="consumer",
                  created_at=ts, updated_at=ts))
    db.flush()
    db.add(Member(member_dist_id="N5637590.4", member_name="C", slot_line_id=1,
                  max_lines=5, parent_dist_id="N5637590.2", created_period_id=period_id,
                  current_pv_balance=0, total_commission=0.0, role="consumer",
                  created_at=ts, updated_at=ts))
    db.flush()
    db.add(Member(member_dist_id="N5637590.5", member_name="D", slot_line_id=1,
                  max_lines=5, parent_dist_id="N5637590.3", created_period_id=period_id,
                  current_pv_balance=0, total_commission=0.0, role="consumer",
                  created_at=ts, updated_at=ts))
    db.flush()
    for did, pv in [("N5637590.2", 1500), ("N5637590.3", 1000),
                    ("N5637590.4", 1500), ("N5637590.5", 1000)]:
        m = db.query(Member).filter(Member.member_dist_id == did).first()
        db.add(PVLedger(member_id=m.id, member_dist_id=did, period_id=period_id,
                        pv_amount=pv, status="pending", contribution_pv=0,
                        commission_amount=0.0, created_at=ts))
    db.commit()


def _find_node(tree, dist_id):
    if tree.get("distId") == dist_id:
        return tree
    for child in tree.get("children", []):
        if not child.get("available"):
            r = _find_node(child, dist_id)
            if r is not None:
                return r
    return None


# ============ PR #67 (subtreePv 递归) + PR #68 (own 不参与) 共同验证 ============

def test_render_root_own_basic_uses_subtree_pv():
    """root own basic = 300 (1区=3000, 2区=2000, 配对 2000 x 15%)
    PR #68: own 不参与, root own=0, 5 子区 P/L 配对不变 → 300
    """
    from skills.pair_commission import get_or_create_period
    db = SessionLocal()
    try:
        period_id = _current_period()
        get_or_create_period(period_id, db)
        db.commit()
        _build_ABCD_tree(db, period_id)

        tree = _build_tree_from_db(db)
        root = _find_node(tree, "N5637590.1")
        assert root is not None, "root not found"

        own_basic = float(root.get("ownBasic", 0.0) or 0.0)
        assert abs(own_basic - 300.0) < 0.01, (
            f"root own basic should be 300.0 (1区=3000, 2区=2000, 配对 2000 x 15%), "
            f"got {own_basic}"
        )
    finally:
        db.close()


def test_render_root_subtree_pv_includes_descendants():
    """A 子区 (递归) = 3000, B 子区 (递归) = 2000 (PR #67 修复, PR #68 保留)"""
    from skills.pair_commission import get_or_create_period
    db = SessionLocal()
    try:
        period_id = _current_period()
        get_or_create_period(period_id, db)
        db.commit()
        _build_ABCD_tree(db, period_id)

        tree = _build_tree_from_db(db)
        a = _find_node(tree, "N5637590.2")
        assert a is not None
        a_subtree = int(a.get("subtreePv", 0) or 0)
        assert a_subtree == 3000, f"A subtreePv should be 3000 (A 1500 + C 1500), got {a_subtree}"

        b = _find_node(tree, "N5637590.3")
        assert b is not None
        b_subtree = int(b.get("subtreePv", 0) or 0)
        assert b_subtree == 2000, f"B subtreePv should be 2000 (B 1000 + D 1000), got {b_subtree}"
    finally:
        db.close()


def test_render_leaf_subtree_pv_equals_own():
    """叶子 subtreePv = 自己的 periodPv (PR #67 修复)"""
    from skills.pair_commission import get_or_create_period
    db = SessionLocal()
    try:
        period_id = _current_period()
        get_or_create_period(period_id, db)
        db.commit()
        _build_ABCD_tree(db, period_id)

        tree = _build_tree_from_db(db)
        c = _find_node(tree, "N5637590.4")
        assert c is not None
        c_subtree = int(c.get("subtreePv", 0) or 0)
        assert c_subtree == 1500, f"C subtreePv should be 1500, got {c_subtree}"

        d = _find_node(tree, "N5637590.5")
        assert d is not None
        d_subtree = int(d.get("subtreePv", 0) or 0)
        assert d_subtree == 1000, f"D subtreePv should be 1000, got {d_subtree}"
    finally:
        db.close()


def test_render_A_own_basic_zero_no_own_pair():
    """PR #68: A own=1500, 5 子区 P=1500 (C), L=0, pair=0
    A own_basic = 0 (own 不参与, 5 子区 P/L 配对 = 0)
    旧 (PR #67): 225 — 错, 已被 PR #68 翻案
    """
    from skills.pair_commission import get_or_create_period
    db = SessionLocal()
    try:
        period_id = _current_period()
        get_or_create_period(period_id, db)
        db.commit()
        _build_ABCD_tree(db, period_id)

        tree = _build_tree_from_db(db)
        a = _find_node(tree, "N5637590.2")
        assert a is not None

        a_own_basic = float(a.get("ownBasic", 0.0) or 0.0)
        assert abs(a_own_basic - 0.0) < 0.01, (
            f"A own basic should be 0.0 (own 1500 不参与, 5 子区 P=1500 L=0 pair=0), "
            f"got {a_own_basic}. PR #68 翻案 PR #67 own_pair!"
        )
    finally:
        db.close()


def test_render_B_own_basic_zero_no_own_pair():
    """PR #68: B own=1000, 5 子区 P=1000 (D), L=0, pair=0
    B own_basic = 0
    旧 (PR #67): 150 — 错
    """
    from skills.pair_commission import get_or_create_period
    db = SessionLocal()
    try:
        period_id = _current_period()
        get_or_create_period(period_id, db)
        db.commit()
        _build_ABCD_tree(db, period_id)

        tree = _build_tree_from_db(db)
        b = _find_node(tree, "N5637590.3")
        assert b is not None

        b_own_basic = float(b.get("ownBasic", 0.0) or 0.0)
        assert abs(b_own_basic - 0.0) < 0.01, (
            f"B own basic should be 0.0 (own 1000 不参与, 5 子区 P=1000 L=0 pair=0), "
            f"got {b_own_basic}. PR #68 翻案 PR #67 own_pair!"
        )
    finally:
        db.close()


def test_render_commissionPreview_root_only_own_basic():
    """PR #68: root commissionPreview = 300 (ownBasic)
    PR #67 旧: 356.25 (ownBasic 300 + pair 56.25 from A/B 7-gen 0.15+0.15)
    PR #68: A/B ownBasic=0, 所以 root 拿不到 pair_bonus, total = 300
    ★ PR #69: 加 teamBonus 1区=3000 (A subtree) × 0.3 + 2区=2000 (B subtree) × 0.3 = 1500
    PR #69 total: 300 + 0 + 1500 = 1800
    """
    from skills.pair_commission import get_or_create_period
    db = SessionLocal()
    try:
        period_id = _current_period()
        get_or_create_period(period_id, db)
        db.commit()
        _build_ABCD_tree(db, period_id)

        tree = _build_tree_from_db(db)
        root = _find_node(tree, "N5637590.1")
        assert root is not None

        # ★ PR #69: 1区 = A subtree (A 1500 + C 1500) = 3000
        #   2区 = B subtree (B 1000 + D 1000) = 2000
        #   teamBonus = 3000 * 0.3 + 2000 * 0.3 = 900 + 600 = 1500
        team_bonus = float(root.get("teamBonus", 0.0) or 0.0)
        assert abs(team_bonus - 1500.0) < 0.01, (
            f"root teamBonus should be 1500 (1区=3000, 2区=2000, × 0.3), got {team_bonus}"
        )

        commission_preview = float(root.get("commissionPreview", 0.0) or 0.0)
        # ownBasic 300 + pair 0 + teamBonus 1500 = 1800
        assert abs(commission_preview - 1800.0) < 0.01, (
            f"root commissionPreview should be 1800.0 (ownBasic 300 + pair 0 + teamBonus 1500), "
            f"got {commission_preview}. PR #68 ownBasic 300, PR #69 加 teamBonus 1500!"
        )
    finally:
        db.close()
