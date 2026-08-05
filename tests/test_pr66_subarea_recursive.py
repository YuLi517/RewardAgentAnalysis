"""PR #66: 修复 _settle_node 子区 PV 不递归累加 bug — 算法层

业务场景 (用户截图反馈, 2026-07-23):
- tree: root → A (line 1) + B (line 2)
-       A → C (line 2) + avail
-       B → D (line 2) + avail
- PV: A=1500, B=1000, C=1500, D=1000
- 用户业务规则:
  - root 1 区 = A 子区 = A own (1500) + C own (1500) = 3000
  - root 2 区 = B 子区 = B own (1000) + D own (1000) = 2000
  - 配对 MIN(3000, 2000) = 2000, root own = 2000 * 0.15 = 300 PV
  - 1 区 carry = 3000 - 2000 = 1000
  - 2 区 carry = 2000 - 2000 = 0

PR #58 旧实现: _settle_node line 386 return max_pv (只 1 层)
- A c_pv_total = 1500 (max of C only, 没加 A own)
- root 1 区 = 1500 (错)
- root own = MIN(1500, 1000) = 1000 * 0.15 = 150 (错)
- 实际算: 150 (用户截图确认)

PR #66 修复: 5 子区递归累加 (own + sum(子节点 c_pv_total))
- A c_pv_total = 1500 (A own) + 1500 (C sub) = 3000 ✓
- root 1 区 = 3000
- root own = MIN(3000, 2000) = 2000 * 0.15 = 300 ✓
- 1 区 carry = 1000, 2 区 carry = 0

PR #68 翻案 PR #66 own-P 配对: 节点 own 不参与 commission 配对
- 节点 own 100% carry
- commission = 5 子区 P/L 配对 (own 不算)

PR #68 算法下 ABCD 树 carry:
- A carry = 1500 (own) + 1000 (根 P 剩) = 2500
- B carry = 1000 (own) + 0 (根 L 剩) = 1000
- C carry = 1500 (own) + 1500 (A P 剩) = 3000
- D carry = 1000 (own) + 1000 (B P 剩) = 2000
"""
import sys
import time
from pathlib import Path

# 跟 PR #58 test 一致, 用 __file__ 相对路径
WT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WT))

from database import init_db, SessionLocal
from models import Member, PVLedger, CommissionPeriod
from skills.pair_commission import settle_period, get_or_create_period


def _reset_db():
    """清 DB + 重建 root (供 setup_function 调)"""
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
        db.add(Member(
            member_dist_id="N5637590.1", member_name="王常军", slot_line_id=0,
            max_lines=5, parent_dist_id=None, created_period_id="2026-07-19_W30",
            current_pv_balance=0, total_commission=0.0, role="consumer",
            created_at=ts, updated_at=ts,
        ))
        db.commit()
    finally:
        db.close()


def setup_function(function):
    """每个测试前清 DB"""
    _reset_db()


def _current_period():
    """用动态 period (跟 _build_tree_from_db.get_current_period_id 一致)"""
    from skills.period import get_current_period_id
    return get_current_period_id()


def _build_ABCD_tree(db, period_id):
    """建用户截图的树: root → A(1) + B(2), A → C(2), B → D(2)"""
    ts = time.time()
    # A (line 1) under root
    db.add(Member(member_dist_id="N5637590.2", member_name="A", slot_line_id=1,
                  max_lines=5, parent_dist_id="N5637590.1", created_period_id=period_id,
                  current_pv_balance=0, total_commission=0.0, role="consumer",
                  created_at=ts, updated_at=ts))
    db.flush()
    # B (line 2) under root
    db.add(Member(member_dist_id="N5637590.3", member_name="B", slot_line_id=2,
                  max_lines=5, parent_dist_id="N5637590.1", created_period_id=period_id,
                  current_pv_balance=0, total_commission=0.0, role="consumer",
                  created_at=ts, updated_at=ts))
    db.flush()
    # C (line 1) under A
    db.add(Member(member_dist_id="N5637590.4", member_name="C", slot_line_id=1,
                  max_lines=5, parent_dist_id="N5637590.2", created_period_id=period_id,
                  current_pv_balance=0, total_commission=0.0, role="consumer",
                  created_at=ts, updated_at=ts))
    db.flush()
    # D (line 1) under B
    db.add(Member(member_dist_id="N5637590.5", member_name="D", slot_line_id=1,
                  max_lines=5, parent_dist_id="N5637590.3", created_period_id=period_id,
                  current_pv_balance=0, total_commission=0.0, role="consumer",
                  created_at=ts, updated_at=ts))
    db.flush()
    # PV: A=1500, B=1000, C=1500, D=1000
    for did, pv in [("N5637590.2", 1500), ("N5637590.3", 1000),
                    ("N5637590.4", 1500), ("N5637590.5", 1000)]:
        m = db.query(Member).filter(Member.member_dist_id == did).first()
        db.add(PVLedger(member_id=m.id, member_dist_id=did, period_id=period_id,
                        pv_amount=pv, status="pending", contribution_pv=0,
                        commission_amount=0.0, created_at=ts))
    db.commit()


# ============ 算法 fix 验证 ============

def test_settle_ABCD_tree_root_own_commission():
    """用户截图场景: root own = 300 PV (= 2000 配对 × 15%)

    业务规则:
      root 1 区 = A 子区 = A(1500) + C(1500) = 3000
      root 2 区 = B 子区 = B(1000) + D(1000) = 2000
      pair = MIN(3000, 2000) = 2000
      root own = 2000 × 0.15 = 300

    PR #66 修复后 (5 子区递归累加): root own = 300 ✓
    PR #68 修复后 (own 不参与): root own = 300 ✓ (root own=0, 5 子区 P/L 配对不变)
    """
    db = SessionLocal()
    try:
        period_id = _current_period()
        get_or_create_period(period_id, db)
        db.commit()
        _build_ABCD_tree(db, period_id)

        result = settle_period(period_id, db, settled_by="manual")
        root_own = result.commission_by_dist.get("N5637590.1", 0.0)
        assert root_own == 300.0, (
            f"root own should be 300.0 (1区=3000, 2区=2000, 配对 2000 × 15%), "
            f"got {root_own}"
        )
    finally:
        db.close()


def test_settle_ABCD_tree_subarea_pv_accumulated():
    """A 子区 (recursive) = A own + C own = 3000
    B 子区 (recursive) = B own + D own = 2000
    """
    db = SessionLocal()
    try:
        period_id = _current_period()
        get_or_create_period(period_id, db)
        db.commit()
        _build_ABCD_tree(db, period_id)

        result = settle_period(period_id, db, settled_by="manual")
        # 配对日志: root 配对消耗 2000 (1区=3000 配对 2区=2000)
        root_log = next((p for p in result.pairs_log if p["node_dist_id"] == "N5637590.1"), None)
        assert root_log, "root pair log not found"
        assert root_log["max_pv"] == 3000, (
            f"root max_pv should be 3000 (A 子区 = A own + C own), "
            f"got {root_log['max_pv']}"
        )
        assert root_log["sum_rest"] == 2000, (
            f"root sum_rest should be 2000 (B 子区 = B own + D own), "
            f"got {root_log['sum_rest']}"
        )
        assert root_log["pair_pv"] == 2000, (
            f"pair = MIN(3000, 2000) = 2000, got {root_log['pair_pv']}"
        )
    finally:
        db.close()


def test_settle_ABCD_tree_carry_out():
    """PR #68 新算法下 (own 100% carry + 5 子区 P/L 配对 carry):
    - A carry = 1500 (own) + 1000 (根 P 子区剩 写给 A) = 2500
    - B carry = 1000 (own) + 0 (根 L 子区剩 写给 B) = 1000
    - 1 区 carry 写给 A = 1000 (根 P 子区剩)
    - 2 区 carry 写给 B = 0 (根 L 子区剩)

    业务: 用户的"剩余的PV=1000" 是 commission 池配对剩 (P 子区剩 1000),
    加上 A own 100% carry 1500, A 总 carry = 2500.
    """
    db = SessionLocal()
    try:
        period_id = _current_period()
        get_or_create_period(period_id, db)
        db.commit()
        _build_ABCD_tree(db, period_id)

        result = settle_period(period_id, db, settled_by="manual")
        # A carry = 2500 (own 1500 + 来自根 1000)
        a_carry = result.carry_out_by_dist.get("N5637590.2", 0)
        assert a_carry == 2500, f"A carry should be 2500 (own 1500 + 根 P 剩 1000), got {a_carry}"
        # B carry = 1000 (own 1000 + 来自根 0)
        b_carry = result.carry_out_by_dist.get("N5637590.3", 0)
        assert b_carry == 1000, f"B carry should be 1000 (own 1000 + 根 L 剩 0), got {b_carry}"
    finally:
        db.close()


def test_settle_ABCD_tree_leaf_carry():
    """PR #68 新算法下 (own 100% carry + 非叶子 own carry + 叶子 own 不写):
    - A carry = 1500 (own, 非叶子) + 1000 (根 P 剩) = 2500
    - B carry = 1000 (own, 非叶子) + 0 (根 L 剩) = 1000
    - C carry = 1500 (从 A P 剩, 叶子 own 不写, 避免双计) = 1500
    - D carry = 1000 (从 B P 剩, 叶子 own 不写) = 1000

    PR #66 老算法 C carry=0 (own 配对消耗 1500 全 P, C 1 子区空, sub_pair=0)
    PR #68 新算法:
      - 非叶子 own carry 100% (own 不参与配对)
      - 叶子 own 不写 (父 p_remain 覆盖, 避免跟 own 双计)
      - 父 p_remain 永远 ADD 到子节点已有 carry 上

    业务 (用户 2026-07-27 反馈): "A 本期应该拿不到佣金, 因为 2 区没新成员"
    A (own=1500, 5 子区 C=1500) P=1500, L=0, pair=0, commission=0 ✓
    """
    db = SessionLocal()
    try:
        period_id = _current_period()
        get_or_create_period(period_id, db)
        db.commit()
        _build_ABCD_tree(db, period_id)

        result = settle_period(period_id, db, settled_by="manual")
        # C carry = 1500 (从 A P 剩, 叶子 own 不写避免双计)
        c_carry = result.carry_out_by_dist.get("N5637590.4", 0)
        assert c_carry == 1500, f"C carry should be 1500 (叶子 own 不写, 来自 A P 剩 1500), got {c_carry}"
        # D carry = 1000 (从 B P 剩)
        d_carry = result.carry_out_by_dist.get("N5637590.5", 0)
        assert d_carry == 1000, f"D carry should be 1000 (叶子 own 不写, 来自 B P 剩 1000), got {d_carry}"
    finally:
        db.close()


def test_settle_simple_flat_tree_still_works():
    """简单扁平树 (没嵌套) 算法不变, 回归测试

    root → A(L1)=100 + B(L2)=100
    root 1 区 = 100, root 2 区 = 100
    pair = MIN(100, 100) = 100, own = 100 * 0.15 = 15
    """
    db = SessionLocal()
    try:
        period_id = _current_period()
        get_or_create_period(period_id, db)
        ts = time.time()
        db.add(Member(member_dist_id="N5637590.2", member_name="A", slot_line_id=1,
                      max_lines=5, parent_dist_id="N5637590.1", created_period_id=period_id,
                      current_pv_balance=0, total_commission=0.0, role="consumer",
                      created_at=ts, updated_at=ts))
        db.flush()
        m_a = db.query(Member).filter(Member.member_dist_id == "N5637590.2").first()
        db.add(Member(member_dist_id="N5637590.3", member_name="B", slot_line_id=2,
                      max_lines=5, parent_dist_id="N5637590.1", created_period_id=period_id,
                      current_pv_balance=0, total_commission=0.0, role="consumer",
                      created_at=ts, updated_at=ts))
        db.flush()
        m_b = db.query(Member).filter(Member.member_dist_id == "N5637590.3").first()
        for m_id, did, pv in [(m_a.id, "N5637590.2", 100), (m_b.id, "N5637590.3", 100)]:
            db.add(PVLedger(member_id=m_id, member_dist_id=did, period_id=period_id,
                            pv_amount=pv, status="pending", contribution_pv=0,
                            commission_amount=0.0, created_at=ts))
        db.commit()

        result = settle_period(period_id, db, settled_by="manual")
        # root own = 15 (root own=0, 5 子区 P/L 配对 100×0.15)
        assert result.commission_by_dist.get("N5637590.1", 0.0) == 15.0
    finally:
        db.close()


def test_settle_3_level_deep_tree():
    """3 层树 (root → A → C → G), 验证递归累加到底

    root → A(L1) + B(L2)
    A → C(L1) + avail
    C → G(L1) + avail
    PV: A=100, B=100, C=100, G=100
    A 子区 = C 子区 = C own (100) + G own (100) = 200
    root 1 区 = 200, root 2 区 = 100
    pair = MIN(200, 100) = 100, root own = 100 * 0.15 = 15
    """
    db = SessionLocal()
    try:
        period_id = _current_period()
        get_or_create_period(period_id, db)
        ts = time.time()
        # A (1) under root
        db.add(Member(member_dist_id="N5637590.2", member_name="A", slot_line_id=1,
                      max_lines=5, parent_dist_id="N5637590.1", created_period_id=period_id,
                      current_pv_balance=0, total_commission=0.0, role="consumer",
                      created_at=ts, updated_at=ts))
        db.flush()
        m_a = db.query(Member).filter(Member.member_dist_id == "N5637590.2").first()
        # B (2) under root
        db.add(Member(member_dist_id="N5637590.3", member_name="B", slot_line_id=2,
                      max_lines=5, parent_dist_id="N5637590.1", created_period_id=period_id,
                      current_pv_balance=0, total_commission=0.0, role="consumer",
                      created_at=ts, updated_at=ts))
        db.flush()
        m_b = db.query(Member).filter(Member.member_dist_id == "N5637590.3").first()
        # C (1) under A
        db.add(Member(member_dist_id="N5637590.4", member_name="C", slot_line_id=1,
                      max_lines=5, parent_dist_id="N5637590.2", created_period_id=period_id,
                      current_pv_balance=0, total_commission=0.0, role="consumer",
                      created_at=ts, updated_at=ts))
        db.flush()
        m_c = db.query(Member).filter(Member.member_dist_id == "N5637590.4").first()
        # G (1) under C
        db.add(Member(member_dist_id="N5637590.5", member_name="G", slot_line_id=1,
                      max_lines=5, parent_dist_id="N5637590.4", created_period_id=period_id,
                      current_pv_balance=0, total_commission=0.0, role="consumer",
                      created_at=ts, updated_at=ts))
        db.flush()
        m_g = db.query(Member).filter(Member.member_dist_id == "N5637590.5").first()
        for m_id, did, pv in [(m_a.id, "N5637590.2", 100), (m_b.id, "N5637590.3", 100),
                              (m_c.id, "N5637590.4", 100), (m_g.id, "N5637590.5", 100)]:
            db.add(PVLedger(member_id=m_id, member_dist_id=did, period_id=period_id,
                            pv_amount=pv, status="pending", contribution_pv=0,
                            commission_amount=0.0, created_at=ts))
        db.commit()

        result = settle_period(period_id, db, settled_by="manual")
        # root own = 15
        assert result.commission_by_dist.get("N5637590.1", 0.0) == 15.0, (
            f"3 层树: root own should be 15 (A 子区=200, B=100, pair=100), "
            f"got {result.commission_by_dist.get('N5637590.1', 0.0)}"
        )
    finally:
        db.close()
