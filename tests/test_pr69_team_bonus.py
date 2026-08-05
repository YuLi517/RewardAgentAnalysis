"""PR #69: 团队培育奖金 = 1区新PV × 30% + 2区新PV × 30%

业务规则 (用户 2026-07-27 反馈):
  "看他的1区和2区是否是新增的成员, 假设1区（左支）新增成员with 1500PV,
   2区（右支）新增成员with 1000PV, 团队培育奖金=1500*30% + 1000*30% = 750"

Tooltip 文案变更:
  - 本期可拿（模拟） → 本期可拿 (去掉"模拟")
  - own basic → 基本佣金
  - 7层对等pair → 对等奖金
  - 删除"基于本期 periodPv 模拟, 跟 settle_period 规则一致" 句
  - 增加 团队培育奖金

业务场景 (6 member 树):
  root → A (L1) + B (L2)
  A → C (L1) + E (L2)
  B → D (L1)

  Period PV: A=1500, B=1500, C=1000, D=1500, E=1200

  期望:
  - root: 1区(A subtree)=3700, 2区(B subtree)=3000
    teamBonus = 3700×0.3 + 3000×0.3 = 1110 + 900 = 2010
    ownBasic = 5 子区 P/L = 3000×0.15 = 450
    pairBonus = 22.5 (A 150×0.15)
    commissionPreview = 450 + 22.5 + 2010 = 2482.5
  - A: 1区(C subtree)=1000, 2区(E subtree)=1200
    teamBonus = 1000×0.3 + 1200×0.3 = 300 + 360 = 660
    ownBasic = 5 子区 P/L = min(1200, 1000)×0.15 = 1000×0.15 = 150
    pairBonus = 0
    commissionPreview = 150 + 0 + 660 = 810
  - B: 1区(D subtree)=1500, 2区(empty)=0
    teamBonus = 1500×0.3 + 0 = 450
    ownBasic = 5 子区 P/L = min(1500,0)×0.15 = 0
    pairBonus = 0
    commissionPreview = 0 + 0 + 450 = 450
  - C, D, E: 叶子, 1区+2区 都空, teamBonus=0
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
    """清 DB + 重建 root + 加 5 个成员"""
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
        for did, name, parent, slot, pv in [
            ("N5637590.2", "A", "N5637590.1", 1, 1500),
            ("N5637590.3", "B", "N5637590.1", 2, 1500),
            ("N5637590.4", "C", "N5637590.2", 1, 1000),
            ("N5637590.5", "D", "N5637590.3", 1, 1500),
            ("N5637590.6", "E", "N5637590.2", 2, 1200),
        ]:
            db.add(Member(
                member_dist_id=did, member_name=name, slot_line_id=slot,
                max_lines=5, parent_dist_id=parent, created_period_id=period_id,
                current_pv_balance=0, total_commission=0.0, role="consumer",
                created_at=ts, updated_at=ts,
            ))
        db.flush()
        for did, pv in [("N5637590.2", 1500), ("N5637590.3", 1500),
                        ("N5637590.4", 1000), ("N5637590.5", 1500), ("N5637590.6", 1200)]:
            m = db.query(Member).filter(Member.member_dist_id == did).first()
            db.add(PVLedger(member_id=m.id, member_dist_id=did, period_id=period_id,
                            pv_amount=pv, status="pending", contribution_pv=0,
                            commission_amount=0.0, created_at=ts))
        db.commit()
    finally:
        db.close()


def setup_function(function):
    _reset_db()


def _find_node(tree, dist_id):
    if tree.get("distId") == dist_id:
        return tree
    for child in tree.get("children", []):
        if not child.get("available"):
            r = _find_node(child, dist_id)
            if r is not None:
                return r
    return None


def test_root_team_bonus_left_and_right():
    """root 1区=3700 (A subtree), 2区=3000 (B subtree)
    teamBonus = 3700×0.3 + 3000×0.3 = 1110 + 900 = 2010
    """
    db = SessionLocal()
    try:
        tree = _build_tree_from_db(db)
        root = _find_node(tree, "N5637590.1")
        assert root is not None
        assert int(root["leftBranchPv"]) == 3700, f"root leftBranchPv should be 3700, got {root['leftBranchPv']}"
        assert int(root["rightBranchPv"]) == 3000, f"root rightBranchPv should be 3000, got {root['rightBranchPv']}"
        assert abs(root["teamBonus"] - 2010.0) < 0.01, f"root teamBonus should be 2010, got {root['teamBonus']}"
    finally:
        db.close()


def test_A_team_bonus_left_C_right_E():
    """A 1区=1000 (C), 2区=1200 (E)
    teamBonus = 1000×0.3 + 1200×0.3 = 300 + 360 = 660
    """
    db = SessionLocal()
    try:
        tree = _build_tree_from_db(db)
        a = _find_node(tree, "N5637590.2")
        assert a is not None
        assert int(a["leftBranchPv"]) == 1000, f"A leftBranchPv should be 1000 (C), got {a['leftBranchPv']}"
        assert int(a["rightBranchPv"]) == 1200, f"A rightBranchPv should be 1200 (E), got {a['rightBranchPv']}"
        assert abs(a["teamBonus"] - 660.0) < 0.01, f"A teamBonus should be 660, got {a['teamBonus']}"
    finally:
        db.close()


def test_B_team_bonus_left_D_right_empty():
    """B 1区=1500 (D), 2区=空=0
    teamBonus = 1500×0.3 + 0 = 450
    """
    db = SessionLocal()
    try:
        tree = _build_tree_from_db(db)
        b = _find_node(tree, "N5637590.3")
        assert b is not None
        assert int(b["leftBranchPv"]) == 1500, f"B leftBranchPv should be 1500 (D), got {b['leftBranchPv']}"
        assert int(b["rightBranchPv"]) == 0, f"B rightBranchPv should be 0, got {b['rightBranchPv']}"
        assert abs(b["teamBonus"] - 450.0) < 0.01, f"B teamBonus should be 450, got {b['teamBonus']}"
    finally:
        db.close()


def test_leaf_team_bonus_zero():
    """C/D/E 叶子, 1区+2区 都空, teamBonus=0"""
    db = SessionLocal()
    try:
        tree = _build_tree_from_db(db)
        for did in ("N5637590.4", "N5637590.5", "N5637590.6"):
            node = _find_node(tree, did)
            assert node is not None
            assert int(node["leftBranchPv"]) == 0
            assert int(node["rightBranchPv"]) == 0
            assert abs(node["teamBonus"] - 0.0) < 0.01, f"{did} teamBonus should be 0, got {node['teamBonus']}"
    finally:
        db.close()


def test_root_commission_preview_includes_team_bonus():
    """root commissionPreview = ownBasic 450 + pairBonus 22.5 + teamBonus 2010 = 2482.5"""
    db = SessionLocal()
    try:
        tree = _build_tree_from_db(db)
        root = _find_node(tree, "N5637590.1")
        assert root is not None
        assert abs(root["ownBasic"] - 450.0) < 0.01, f"ownBasic should be 450, got {root['ownBasic']}"
        assert abs(root["teamBonus"] - 2010.0) < 0.01, f"teamBonus should be 2010, got {root['teamBonus']}"
        # commissionPreview = 450 + 22.5 + 2010 = 2482.5
        assert abs(root["commissionPreview"] - 2482.5) < 0.01, (
            f"root commissionPreview should be 2482.5 (ownBasic 450 + pairBonus 22.5 + teamBonus 2010), "
            f"got {root['commissionPreview']}"
        )
    finally:
        db.close()


def test_A_commission_preview_includes_team_bonus():
    """A commissionPreview = ownBasic 150 + pairBonus 0 + teamBonus 660 = 810"""
    db = SessionLocal()
    try:
        tree = _build_tree_from_db(db)
        a = _find_node(tree, "N5637590.2")
        assert a is not None
        assert abs(a["ownBasic"] - 150.0) < 0.01, f"A ownBasic should be 150, got {a['ownBasic']}"
        assert abs(a["teamBonus"] - 660.0) < 0.01, f"A teamBonus should be 660, got {a['teamBonus']}"
        assert abs(a["commissionPreview"] - 810.0) < 0.01, (
            f"A commissionPreview should be 810 (ownBasic 150 + pairBonus 0 + teamBonus 660), "
            f"got {a['commissionPreview']}"
        )
    finally:
        db.close()


def test_team_bonus_does_not_propagate_to_ancestors():
    """PR #69: teamBonus 只加给节点自己, 不分给祖先 (跟 pairBonus 不同)"""
    db = SessionLocal()
    try:
        tree = _build_tree_from_db(db)
        # A 的 teamBonus = 660, 不应加到 root 上
        root = _find_node(tree, "N5637590.1")
        a = _find_node(tree, "N5637590.2")
        assert root["teamBonus"] == 2010  # root 自己的 1区+2区
        assert a["teamBonus"] == 660  # A 自己的 1区+2区
        # root 的 teamBonus (2010) 跟 A 的 teamBonus (660) 独立, 没有叠加
        # commissionPreview = own + pair + team
        # root: 450 + 22.5 + 2010 = 2482.5
        # A: 150 + 0 + 660 = 810
        # 验证 root commissionPreview != 450 + 22.5 + 2010 + 660 (没叠加)
        assert root["commissionPreview"] == 2482.5
    finally:
        db.close()


def test_simple_2_member_left_right():
    """简单 2 member 树: root → M1(L1) PV=1500, M2(L2) PV=1000
    业务 (用户截图例子): teamBonus = 1500×0.3 + 1000×0.3 = 750
    """
    # 重新建 2 member 树
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
        for did, name, slot, pv in [
            ("N5637590.2", "M1", 1, 1500),
            ("N5637590.3", "M2", 2, 1000),
        ]:
            db.add(Member(
                member_dist_id=did, member_name=name, slot_line_id=slot,
                max_lines=5, parent_dist_id="N5637590.1", created_period_id=period_id,
                current_pv_balance=0, total_commission=0.0, role="consumer",
                created_at=ts, updated_at=ts,
            ))
        db.flush()
        for did, pv in [("N5637590.2", 1500), ("N5637590.3", 1000)]:
            m = db.query(Member).filter(Member.member_dist_id == did).first()
            db.add(PVLedger(member_id=m.id, member_dist_id=did, period_id=period_id,
                            pv_amount=pv, status="pending", contribution_pv=0,
                            commission_amount=0.0, created_at=ts))
        db.commit()
    finally:
        db.close()

    db = SessionLocal()
    try:
        tree = _build_tree_from_db(db)
        root = _find_node(tree, "N5637590.1")
        assert root is not None
        # 1区 (M1) = 1500, 2区 (M2) = 1000
        # teamBonus = 1500×0.3 + 1000×0.3 = 450 + 300 = 750
        assert int(root["leftBranchPv"]) == 1500
        assert int(root["rightBranchPv"]) == 1000
        assert abs(root["teamBonus"] - 750.0) < 0.01, f"teamBonus should be 750, got {root['teamBonus']}"
    finally:
        db.close()
