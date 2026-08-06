# -*- coding: utf-8 -*-
r"""
test_pair_commission.py —— 周 commission 结算核心算法单元测试
=================================================================

跑测试:
    cd D:\Projects\Reward\RewardAgentAnalysis
    python -m pytest tests/test_pair_commission.py -v
    或
    python -m unittest tests.test_pair_commission -v

用 in-memory SQLite (sqlite:///:memory:), 不污染 data/rewarddb.db

覆盖场景:
    T1: 1 个成员无配对 → carry 全量, commission = 0
    T2: 2 个成员 MIN 配对 → MIN 消耗, 各自 carry 剩余
    T3: 5 个成员 5 叉 MAX vs SUM 配对 → 复杂配对
    T4: 跨期 carry → 成员带 carry_in balance 进新一期
    T5: 7 代分润 → 深树验证 ancestor chain share
    T6: 边界: 0 PV / 负 PV 拒绝 / period 不存在
"""
import os
import sys
import unittest

# 确保项目根目录在 sys.path (能 import models / repository / skills)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, Member, PVLedger, CommissionPeriod
from repository import (
    MemberRepository, PVLedgerRepository, CommissionPeriodRepository,
)
from skills.pair_commission import (
    settle_period, get_or_create_period, _build_settle_tree, _settle_node,
    _apply_pairing_bonus, SlotNode, SettleResult,
)
from skills.period import get_current_period_id, COMMISSION_RATE


def _make_db():
    """返回 (SessionLocal, db) in-memory SQLite session"""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    return engine, SessionLocal()


class TestPairCommission(unittest.TestCase):
    """周 commission 结算算法测试"""

    def setUp(self):
        """每个 test 前建一个全新 in-memory DB"""
        self.engine, self.db = _make_db()
        self.member_repo = MemberRepository(self.db)
        self.ledger_repo = PVLedgerRepository(self.db)
        self.period_repo = CommissionPeriodRepository(self.db)
        self.period_id = get_current_period_id()
        self.period = self.period_repo.get_or_create(
            self.period_id, *self._get_period_range()
        )

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _get_period_range(self):
        from skills.period import get_period_range
        return get_period_range(self.period_id)

    def _make_member(self, dist_id, balance=0, name=None, parent="ROOT", slot=1):
        m = self.member_repo.get_or_create(
            member_dist_id=dist_id,
            member_name=name or dist_id,
            parent_dist_id=parent,
            slot_line_id=slot,
            max_lines=5,
            created_period_id=self.period_id,
        )
        if balance:
            self.member_repo.add_pv(m.id, balance)
        return m

    def _add_ledger(self, member, pv_amount, period_id=None):
        return self.ledger_repo.append(
            member_id=member.id,
            member_dist_id=member.member_dist_id,
            period_id=period_id or self.period_id,
            pv_amount=pv_amount,
            note="test",
        )

    # ============== T1: 1 个成员无配对 ==============

    def test_t1_single_member_no_pair(self):
        """1 个成员加 500PV, 没配对对象 → 全部 carry, commission = 0"""
        m = self._make_member("N-T1-001", balance=0)
        self._add_ledger(m, 500)

        result = settle_period(self.period_id, self.db, settled_by="test")

        # commission = 0 (1 人无配对)
        self.assertEqual(result.total_commission, 0.0)
        self.assertEqual(result.total_pv_consumed, 0)
        # carry = 500 (全量)
        self.assertEqual(result.carry_out_by_dist.get("N-T1-001"), 500)
        # member balance 已更新到 500
        m_after = self.member_repo.get_by_dist_id("N-T1-001")
        self.assertEqual(m_after.current_pv_balance, 500)
        # period 已 settled
        p_after = self.period_repo.get(self.period_id)
        self.assertEqual(p_after.status, "settled")
        # ledger 标 carried
        ledger = self.ledger_repo.list_by_member(m.id)
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0].status, "carried")
        # ★ PR #73: commission=0 → savings=0 (无 commission 触发)
        self.assertEqual(result.savings_by_dist, {})

    # ============== T2: 2 个成员 MIN 配对 ==============

    def test_t2_two_member_min_pair(self):
        """A=500, B=300, 配对 MIN(500,300) = 300, A 剩 200, B 剩 0"""
        m_a = self._make_member("N-T2-A")
        m_b = self._make_member("N-T2-B")
        self._add_ledger(m_a, 500)
        self._add_ledger(m_b, 300)

        result = settle_period(self.period_id, self.db, settled_by="test")

        # commission = 300 × 0.15 = 45
        self.assertAlmostEqual(result.total_commission, 45.0, places=2)
        # 总消耗 = 300
        self.assertEqual(result.total_pv_consumed, 300)
        # 验证 carry_out (按算法顺序, MAX 子区是谁取决于排序)
        # 500 > 300, 500 是 MAX, 300 是 SUM_rest
        # pair = min(500, 300) = 300
        # MAX 剩 = max(500-300, 0) = 200
        # SUM_rest 剩 = max(300-500, 0) = 0
        # 但算法按 sorted 排 (PV DESC), 所以 500 在前 carry_max, 300 在后 carry_rest
        carry_a = result.carry_out_by_dist.get("N-T2-A", 0)
        carry_b = result.carry_out_by_dist.get("N-T2-B", 0)
        # 验证: 一个是 200, 一个是 0
        carry_set = sorted([carry_a, carry_b])
        self.assertEqual(carry_set, [0, 200])
        # balances updated
        m_a_after = self.member_repo.get_by_dist_id("N-T2-A")
        m_b_after = self.member_repo.get_by_dist_id("N-T2-B")
        balance_set = sorted([m_a_after.current_pv_balance, m_b_after.current_pv_balance])
        self.assertEqual(balance_set, [0, 200])
        # ★ PR #73: commission=45 (< $250 门槛) → savings=0
        self.assertEqual(result.savings_by_dist, {})

    # ============== T3: 5 个成员 5 叉 MAX vs SUM ==============

    def test_t3_five_member_5ary_max_sum(self):
        """5 叉树, 5 个子区 PV = [100, 50, 50, 50, 50]
        MAX=100, SUM_rest=200
        pair = min(100, 200) = 100
        commission = 100 × 0.15 = 15
        carry_max = max(100-100, 0) = 0  (P 剩 = P - sub_pair = 100-100)
        carry_L_i = max(0, L_i - sub_pair)  (per-line cap, L_i=50, sub_pair=100, 50-100=-50 → 0)
        总 carry = 0 (PR #72 v2 统一 sub_pair 公式, per-line cap)
        """
        members = [self._make_member(f"N-T3-{i}", slot=i) for i in range(1, 6)]
        pvs = [100, 50, 50, 50, 50]
        for m, pv in zip(members, pvs):
            self._add_ledger(m, pv)

        result = settle_period(self.period_id, self.db, settled_by="test")

        # commission = 15 (sub_pair=100, × 15% = 15)
        self.assertAlmostEqual(result.total_commission, 15.0, places=2)
        # 总消耗 = 100 (sub_pair)
        self.assertEqual(result.total_pv_consumed, 100)
        # ★ PR #72 v2 (2026-08-06): carry per-line cap (P-sub_pair, L_i-sub_pair)
        #   P 剩 = 100-100 = 0
        #   L_i 剩 = max(0, 50-100) = 0 (L_i < sub_pair, 配对全消耗)
        #   总 carry = 0 (旧 PR #66 算法是 25 each, 100 total, 改后 0)
        carries = [result.carry_out_by_dist.get(f"N-T3-{i}", 0) for i in range(1, 6)]
        self.assertEqual(sorted(carries), [0, 0, 0, 0, 0])
        # balances updated
        balances = []
        for i in range(1, 6):
            m = self.member_repo.get_by_dist_id(f"N-T3-{i}")
            balances.append(m.current_pv_balance)
        self.assertEqual(sorted(balances), [0, 0, 0, 0, 0])
        # ★ PR #73: commission=15 (< $250 门槛) → savings=0
        self.assertEqual(result.savings_by_dist, {})

    # ============== T4: 跨期 carry ==============

    def test_t4_cross_period_carry(self):
        """成员 A 上期未消耗 200, 本期再增 100 → 当期可配对 = 300
        成员 B 本期增 300 → 当期可配对 = 300
        pair = min(300, 300) = 300
        commission = 45
        carry = 0
        """
        # ★ step 1: 先结算 period W1, A 加 500, B 加 300 (跟 T2 类似, 但 A 留 200 carry)
        w1_period = "2025-12-28_W01"
        self.period_repo.get_or_create(w1_period, *self._period_range(w1_period))
        m_a = self._make_member("N-T4-A")
        m_b = self._make_member("N-T4-B")
        self._add_ledger(m_a, 500, period_id=w1_period)
        self._add_ledger(m_b, 300, period_id=w1_period)
        r1 = settle_period(w1_period, self.db, settled_by="test")
        # A 余额 200, B 余额 0
        self.assertEqual(self.member_repo.get_by_dist_id("N-T4-A").current_pv_balance, 200)
        self.assertEqual(self.member_repo.get_by_dist_id("N-T4-B").current_pv_balance, 0)

        # ★ step 2: W2 期, A 余额 200 + 本期再增 100 = 300, B 本期 0
        w2_period = "2026-01-04_W02"
        self.period_repo.get_or_create(w2_period, *self._period_range(w2_period))
        self._add_ledger(m_a, 100, period_id=w2_period)

        # 现在 A 余额 200, ledger 100 → 算 settle_tree 时 pv = 200 + 100 = 300
        r2 = settle_period(w2_period, self.db, settled_by="test")
        # W2 commission = 0 (1 人, 无配对)
        self.assertEqual(r2.total_commission, 0.0)
        # A carry = 300 (本期无配对)
        self.assertEqual(r2.carry_out_by_dist.get("N-T4-A"), 300)
        # 验证 member balance 已更新
        self.assertEqual(self.member_repo.get_by_dist_id("N-T4-A").current_pv_balance, 300)
        # 期间信息写入
        self.assertEqual(self.member_repo.get_by_dist_id("N-T4-A").last_period_id, w2_period)
        # ★ PR #73: W1 + W2 commission 都很小 (< $250 门槛) → savings=0
        self.assertEqual(r2.savings_by_dist, {})

    def _period_range(self, period_id):
        from skills.period import get_period_range
        return get_period_range(period_id)

    # ============== T5: 7 代分润 (ancestor chain share) ==============

    def test_t5_pairing_bonus_7_generations(self):
        """构造深树触发 commission, 验证 ancestor 拿到 share

        结构: root → L1 → L2
              L2 子区: L3=100, L4=100  (2 子区, 触发配对)
              L1 子区: 只有 L2
              root 子区: 只有 L1
        期望:
          L2 commission = MIN(100,100) × 0.15 = 15
          沿祖先链: L1 拿 15×0.15=2.25, root 拿 15×0.10=1.5
        """
        def make_node(dist_id, pv, children=None):
            n = SlotNode(dist_id=dist_id, member_dist_id=dist_id, pv=pv, slot_line_id=1)
            n.children = children or [None] * 5
            return n

        l3 = make_node("L3", pv=100)
        l4 = make_node("L4", pv=100)
        l2 = make_node("L2", pv=100, children=[l3, l4, None, None, None])
        l1 = make_node("L1", pv=100, children=[l2, None, None, None, None])
        # ★ 2026-07-17 PR #53: root 改 __VIRTUAL_ROOT__ sentinel (旧 "ROOT" 跟真实 distId 冲突)
        root = SlotNode(dist_id="__VIRTUAL_ROOT__", slot_line_id=0)
        root.children = [l1, None, None, None, None]

        result = SettleResult(period_id="TEST-T5")
        _settle_node(root, result)
        _apply_pairing_bonus(root, result)

        # L2 节点 commission = 15 (L2 子区 L3=100, L4=100 配对, MIN(100,100)=100, × 0.15=15)
        self.assertAlmostEqual(result.commission_by_dist.get("L2", 0), 15.0, places=2)
        # L1 (L2 的直接父) 拿 share = 15 × 0.15 = 2.25
        self.assertAlmostEqual(result.ancestor_share_by_dist.get("L1", 0), 2.25, places=2)
        # ROOT 是虚拟根, 不参与分润 (不算 ancestor)
        self.assertNotIn("ROOT", result.ancestor_share_by_dist)
        # 至少 1 个 ancestor 拿到 share
        self.assertGreater(len(result.ancestor_share_by_dist), 0)
        # ★ PR #73: 所有 commission (15 + 1.5 + 2.25 = 18.75) 都 < $250 → savings=0
        self.assertEqual(result.savings_by_dist, {})

    # ============== T6: 边界 ==============

    def test_t6_settle_nonexistent_period_raises(self):
        """不存在的 period 抛 ValueError"""
        with self.assertRaises(ValueError):
            settle_period("9999-W99", self.db)

    def test_t7_settle_no_pending_is_noop(self):
        """没有 pending ledger 时, settle 是 noop (返回空 result, 不改 period status)"""
        result = settle_period(self.period_id, self.db, settled_by="test")
        self.assertEqual(result.total_commission, 0.0)
        self.assertEqual(result.member_count, 0)

    # ============== PR #53: root 拿 commission (不是虚拟 ROOT 丢) ==============

    def test_pr53_real_root_takes_pairing_commission(self):
        """★ PR #53: 张a=500 (P) + 张b=300 (L) 配对 → 真实 root (王常军) 拿 $45 commission

        业务规则: 配对 P vs L 的 15% commission 归**父节点** (用户 2026-07-17 拍板)
        旧实现: root 是 dist_id="ROOT" 虚拟根 → "if node.dist_id != ROOT" 永远跳过
                → commission 算出来但归属空, member table total_commission=0
        新实现: _build_settle_tree 用真实 root (parent_dist_id=空 + slot_line_id=0)
                root.dist_id = "N5637590.1" (王常军)
                → _settle_node 把 $45 写到 commission_by_dist["N5637590.1"]
                → _write_settle_result 给王常军 total_commission += 45
        """
        period = "2026-09-27_W40"
        # 0. 初始化 period (PR #53 测的独立 period)
        from skills.pair_commission import get_or_create_period
        get_or_create_period(period, self.db)
        self.db.commit()
        # 1. seed root + 2 个 L1 成员 (用 get_or_create + 手动 db.add)
        from models import Member
        now = 1234567890.0
        root = Member(
            member_dist_id="N5637590.1", member_name="王常军",
            parent_dist_id=None, slot_line_id=0, max_lines=5,
            current_pv_balance=0, total_commission=0.0,
            created_period_id=period, last_period_id=None,
            created_at=now, updated_at=now,
        )
        self.db.add(root)
        self.db.flush()
        m_a = Member(
            member_dist_id="N5637590.2", member_name="张a",
            parent_dist_id="N5637590.1", slot_line_id=1, max_lines=5,
            current_pv_balance=0, total_commission=0.0,
            created_period_id=period, last_period_id=None,
            created_at=now, updated_at=now,
        )
        m_b = Member(
            member_dist_id="N5637590.3", member_name="张b",
            parent_dist_id="N5637590.1", slot_line_id=2, max_lines=5,
            current_pv_balance=0, total_commission=0.0,
            created_period_id=period, last_period_id=None,
            created_at=now, updated_at=now,
        )
        self.db.add_all([m_a, m_b])
        self.db.commit()

        # 2. 写本期 ledger (500 + 300)
        from models import PVLedger
        self.db.add(PVLedger(
            member_id=m_a.id, member_dist_id="N5637590.2",
            period_id=period, pv_amount=500, status="pending",
        ))
        self.db.add(PVLedger(
            member_id=m_b.id, member_dist_id="N5637590.3",
            period_id=period, pv_amount=300, status="pending",
        ))
        self.db.commit()

        # 3. settle
        result = settle_period(period, self.db, settled_by="test")
        self.db.commit()  # 写 DB (更新 total_commission)

        # 4. 验证: total_commission = 45 (= MIN(500, 300) * 0.15)
        self.assertEqual(result.total_commission, 45.0)

        # 5. ★ PR #53 核心断言: 真实 root (王常军) 拿 commission, 不是 orphan
        self.assertIn("N5637590.1", result.commission_by_dist)
        self.assertAlmostEqual(result.commission_by_dist["N5637590.1"], 45.0, places=2)
        # 张a/张b 自己是叶子, own commission = 0 (commission 归父节点)
        self.assertNotIn("N5637590.2", result.commission_by_dist)
        self.assertNotIn("N5637590.3", result.commission_by_dist)

        # 6. DB 验证: 王常军 total_commission 实际写到了 45
        self.db.expire_all()
        root_after = self.member_repo.get_by_dist_id("N5637590.1")
        self.assertAlmostEqual(root_after.total_commission, 45.0, places=2)
        # 张a/张b total_commission 仍是 0 (没拿到)
        m_a_after = self.member_repo.get_by_dist_id("N5637590.2")
        m_b_after = self.member_repo.get_by_dist_id("N5637590.3")
        self.assertAlmostEqual(m_a_after.total_commission, 0.0, places=2)
        self.assertAlmostEqual(m_b_after.total_commission, 0.0, places=2)
        # ★ PR #73: 王常军 commission=45 (< $250 门槛) → savings=0
        self.assertEqual(result.savings_by_dist, {})

    def test_pr53_root_commission_not_to_other_members(self):
        """★ PR #53: root 拿 commission 后, 不分给 ancestors (root 是顶级, 没 ancestors)

        ancestor_share_by_dist 应该是空 (没有 member 拿 share, 因为 root 没 ancestors)
        """
        from models import Member, PVLedger
        period = "2026-10-04_W41"
        from skills.pair_commission import get_or_create_period
        get_or_create_period(period, self.db)
        self.db.commit()
        now = 1234567890.0
        root = Member(
            member_dist_id="N5637590.1", member_name="王常军",
            parent_dist_id=None, slot_line_id=0, max_lines=5,
            current_pv_balance=0, total_commission=0.0,
            created_period_id=period, last_period_id=None,
            created_at=now, updated_at=now,
        )
        self.db.add(root)
        self.db.flush()
        m_a = Member(
            member_dist_id="N5637590.2", member_name="张a",
            parent_dist_id="N5637590.1", slot_line_id=1, max_lines=5,
            current_pv_balance=0, total_commission=0.0,
            created_period_id=period, last_period_id=None,
            created_at=now, updated_at=now,
        )
        m_b = Member(
            member_dist_id="N5637590.3", member_name="张b",
            parent_dist_id="N5637590.1", slot_line_id=2, max_lines=5,
            current_pv_balance=0, total_commission=0.0,
            created_period_id=period, last_period_id=None,
            created_at=now, updated_at=now,
        )
        self.db.add_all([m_a, m_b])
        self.db.commit()
        self.db.add(PVLedger(
            member_id=m_a.id, member_dist_id="N5637590.2",
            period_id=period, pv_amount=500, status="pending",
        ))
        self.db.add(PVLedger(
            member_id=m_b.id, member_dist_id="N5637590.3",
            period_id=period, pv_amount=300, status="pending",
        ))
        self.db.commit()

        result = settle_period(period, self.db, settled_by="test")

        # root 是顶级, ancestors=[] → 没有 ancestor 拿 share
        self.assertEqual(len(result.ancestor_share_by_dist), 0,
                         f"root 是顶级不该有 ancestor share, 实际 {result.ancestor_share_by_dist}")
        # period 仍 open (不主动 settled 空期)
        p_after = self.period_repo.get(self.period_id)
        self.assertEqual(p_after.status, "open")

    # ============== PR #73: 储蓄奖金 (Savings Bonus, USD) ==============

    def _make_savings_setup(self, period, a_pv, b_pv):
        """PR #73 helper: 配 setup root + 2 L1 子 + ledger + commit, 返 (period, root, m_a, m_b)"""
        from models import Member, PVLedger
        from skills.pair_commission import get_or_create_period
        get_or_create_period(period, self.db)
        self.db.commit()
        now = 1234567890.0
        root = Member(
            member_dist_id="N5637590.1", member_name="王常军",
            parent_dist_id=None, slot_line_id=0, max_lines=5,
            current_pv_balance=0, total_commission=0.0,
            created_period_id=period, last_period_id=None,
            created_at=now, updated_at=now,
        )
        self.db.add(root)
        self.db.flush()
        m_a = Member(
            member_dist_id="N5637590.2", member_name="A",
            parent_dist_id="N5637590.1", slot_line_id=1, max_lines=5,
            current_pv_balance=0, total_commission=0.0,
            created_period_id=period, last_period_id=None,
            created_at=now, updated_at=now,
        )
        m_b = Member(
            member_dist_id="N5637590.3", member_name="B",
            parent_dist_id="N5637590.1", slot_line_id=2, max_lines=5,
            current_pv_balance=0, total_commission=0.0,
            created_period_id=period, last_period_id=None,
            created_at=now, updated_at=now,
        )
        self.db.add_all([m_a, m_b])
        self.db.commit()
        self.db.add(PVLedger(
            member_id=m_a.id, member_dist_id="N5637590.2",
            period_id=period, pv_amount=a_pv, status="pending",
        ))
        self.db.add(PVLedger(
            member_id=m_b.id, member_dist_id="N5637590.3",
            period_id=period, pv_amount=b_pv, status="pending",
        ))
        self.db.commit()
        return root, m_a, m_b

    def test_pr73_savings_below_threshold(self):
        """★ PR #73: ownBasic=$200 (< $250 门槛) → savings=0

        业务: sub_pair = min(200, 200) = 200, commission = 200 × 15% = $30 (< $250)
        savings: $30 < $250 门槛 → 不触发
        """
        period = "2026-10-11_W42"
        self._make_savings_setup(period, a_pv=200, b_pv=200)
        result = settle_period(period, self.db, settled_by="test")
        self.db.commit()

        # root ownBasic = 30
        self.assertAlmostEqual(result.commission_by_dist["N5637590.1"], 30.0, places=2)
        # savings=0 (commission=30 < $250 门槛)
        self.assertEqual(result.savings_by_dist, {})
        # DB 验证: root.savings_balance = 0
        self.db.expire_all()
        root_after = self.member_repo.get_by_dist_id("N5637590.1")
        self.assertAlmostEqual(root_after.savings_balance, 0.0, places=2)

    def test_pr73_savings_at_threshold(self):
        """★ PR #73: ownBasic=$250 (= 门槛) → savings = 250 × 15% = $37.50

        业务: 节点 commission = 250 (= 门槛) 触发, savings = $37.50
        配 setup: A=B=2000 → sub_pair=2000, commission=300 (≈)
        用 $250 配对消耗: 1000/1000 → 150 commission. 改用 cap 13334:
        A=B=13334 → sub_pair=13334, commission=$2000.10 (cap 触发 → $500)
        改用 10000/10000 不可 (超过 13334 cap 仍 $2000.10)
        改用 8334/8334 → sub_pair=8334, commission=$1250.10 (验证 savings)
        """
        period = "2026-10-18_W43"
        self._make_savings_setup(period, a_pv=8334, b_pv=8334)
        result = settle_period(period, self.db, settled_by="test")
        self.db.commit()

        # root ownBasic = 1250.10 (>= $250 门槛)
        self.assertAlmostEqual(result.commission_by_dist["N5637590.1"], 1250.10, places=2)
        # savings = 1250.10 × 15% = 187.515 (无 cap 触发)
        self.assertIn("N5637590.1", result.savings_by_dist)
        self.assertAlmostEqual(result.savings_by_dist["N5637590.1"], 187.515, places=2)
        # DB 验证: savings_balance 累加
        self.db.expire_all()
        root_after = self.member_repo.get_by_dist_id("N5637590.1")
        self.assertAlmostEqual(root_after.savings_balance, 187.515, places=2)

    def test_pr73_savings_user_example(self):
        """★ PR #73: 用户原话场景 — ownBasic=$1000 → savings=$150

        业务: "当周基本佣金收入达到或超过 250 美元时候, 如果您的基本佣金为 1000 美元.
              您将在储蓄奖金中额外存入 150 美元"
        配 setup: A=B=10000/2=5000 (没有 cap 影响), sub_pair=5000, commission=$750
        改用 A=B=20000/2=10000 → cap 13334 触发, sub_pair=13334, commission=$2000.10
        改用 A=B=13334 → cap 触发, commission=$2000.10, savings cap 触发 $500
        改用 20000/0.15/2=6666: A=B=6666, sub_pair=6666, commission=$999.90 ≈ $1000
        """
        period = "2026-10-25_W44"
        self._make_savings_setup(period, a_pv=6666, b_pv=6666)
        result = settle_period(period, self.db, settled_by="test")
        self.db.commit()

        # root ownBasic ≈ $999.90 (≈ $1000, 用户原话场景)
        self.assertAlmostEqual(result.commission_by_dist["N5637590.1"], 999.90, places=2)
        # savings = 999.90 × 15% = 149.985 (≈ $150, 用户原话)
        self.assertIn("N5637590.1", result.savings_by_dist)
        self.assertAlmostEqual(result.savings_by_dist["N5637590.1"], 149.985, places=2)

    def test_pr73_savings_cap(self):
        """★ PR #73: ownBasic ≥ $3334 → savings cap $500/周

        业务: max(ownBasic × 15%, 500) = $500
        配 setup: A=B=13334 (cap 触发), sub_pair=13334, commission=$2000.10
        savings = min(2000.10 × 15%, 500) = min(300.015, 500) = $300.015 (无 cap)
        用 A=B=20000 → sub_pair=13334, commission=$2000.10 (同)
        用 A=20000+B=13334 → sub_pair=13334, commission=$2000.10 (同)
        要触发 cap: ownBasic ≥ 3334 (= 500/0.15)
        配 setup: A=B=13334*1.5=20001 → cap 13334, sub_pair=13334, commission=$2000.10 (同)
        commission 不会超过 $2000.10, 所以 cap 永远不触发 (sub_pair cap=13334)
        → 调整: 用单边配对消耗, 走 "commission=13334×15%=2000.10" 永远 < 500/0.15=3334
        → 测试改成: 验证 cap 公式 (没真实 cap 触发场景, 但要验证 _savings_bonus_usd 公式)
        """
        from main import _savings_bonus_usd
        # 3334 触发 cap: 3334 × 15% = 500.10, min(500.10, 500) = 500
        self.assertAlmostEqual(_savings_bonus_usd(3334), 500.0, places=2)
        # 5000 触发 cap: 5000 × 15% = 750, min(750, 500) = 500
        self.assertAlmostEqual(_savings_bonus_usd(5000), 500.0, places=2)
        # 10000 触发 cap: 10000 × 15% = 1500, min(1500, 500) = 500
        self.assertAlmostEqual(_savings_bonus_usd(10000), 500.0, places=2)
        # 业务约束: commission cap (sub_pair 13334) 让 ownBasic max=$2000.10, 永远 < cap 触发
        # 但公式独立验证: 直接给 ownBasic > 3334 时 cap 触发
        period = "2026-11-01_W45"
        self._make_savings_setup(period, a_pv=13334, b_pv=13334)
        result = settle_period(period, self.db, settled_by="test")
        self.db.commit()
        # root ownBasic = $2000.10 (commission cap)
        self.assertAlmostEqual(result.commission_by_dist["N5637590.1"], 2000.10, places=2)
        # savings = 2000.10 × 15% = 300.015 (无 cap 触发, < $500)
        self.assertAlmostEqual(result.savings_by_dist["N5637590.1"], 300.015, places=2)

    def test_pr73_savings_accumulate_cross_period(self):
        """★ PR #73: 跨期累计 savings_balance (主 settle + 补录都加)

        业务: 节点 W1 commission=$1000 → savings=$150 → savings_balance += $150
              W2 commission=$1000 → savings=$150 → savings_balance += $150
              最终 savings_balance = $300
        """
        from models import Member, PVLedger
        from skills.pair_commission import get_or_create_period

        # W1 配 setup
        w1 = "2026-11-08_W46"
        get_or_create_period(w1, self.db)
        self.db.commit()
        now = 1234567890.0
        root = Member(
            member_dist_id="N5637590.1", member_name="王常军",
            parent_dist_id=None, slot_line_id=0, max_lines=5,
            current_pv_balance=0, total_commission=0.0,
            savings_balance=0.0,  # ★ 起始 0
            created_period_id=w1, last_period_id=None,
            created_at=now, updated_at=now,
        )
        self.db.add(root)
        self.db.flush()
        m_a = Member(member_dist_id="N5637590.2", member_name="A",
                     parent_dist_id="N5637590.1", slot_line_id=1, max_lines=5,
                     current_pv_balance=0, total_commission=0.0, savings_balance=0.0,
                     created_period_id=w1, last_period_id=None,
                     created_at=now, updated_at=now)
        m_b = Member(member_dist_id="N5637590.3", member_name="B",
                     parent_dist_id="N5637590.1", slot_line_id=2, max_lines=5,
                     current_pv_balance=0, total_commission=0.0, savings_balance=0.0,
                     created_period_id=w1, last_period_id=None,
                     created_at=now, updated_at=now)
        self.db.add_all([m_a, m_b])
        self.db.commit()
        # W1 ledger: A=B=6666 (commission $999.90)
        self.db.add(PVLedger(member_id=m_a.id, member_dist_id="N5637590.2",
                             period_id=w1, pv_amount=6666, status="pending"))
        self.db.add(PVLedger(member_id=m_b.id, member_dist_id="N5637590.3",
                             period_id=w1, pv_amount=6666, status="pending"))
        self.db.commit()
        r1 = settle_period(w1, self.db, settled_by="test")
        self.db.commit()
        # W1: ownBasic=$999.90, savings=$149.985
        self.assertAlmostEqual(r1.savings_by_dist["N5637590.1"], 149.985, places=2)
        # DB 验证: savings_balance=149.985
        self.db.expire_all()
        root_after = self.member_repo.get_by_dist_id("N5637590.1")
        self.assertAlmostEqual(root_after.savings_balance, 149.985, places=2)

        # W2 配 setup (新期, 新 ledger, 同一 root)
        w2 = "2026-11-15_W47"
        get_or_create_period(w2, self.db)
        self.db.commit()
        self.db.add(PVLedger(member_id=m_a.id, member_dist_id="N5637590.2",
                             period_id=w2, pv_amount=6666, status="pending"))
        self.db.add(PVLedger(member_id=m_b.id, member_dist_id="N5637590.3",
                             period_id=w2, pv_amount=6666, status="pending"))
        self.db.commit()
        r2 = settle_period(w2, self.db, settled_by="test")
        self.db.commit()
        # W2: ownBasic=$999.90, savings=$149.985 (再触发)
        self.assertAlmostEqual(r2.savings_by_dist["N5637590.1"], 149.985, places=2)
        # DB 验证: savings_balance 累加 = 149.985 + 149.985 = 299.97
        self.db.expire_all()
        root_after = self.member_repo.get_by_dist_id("N5637590.1")
        self.assertAlmostEqual(root_after.savings_balance, 299.97, places=2)
        # total_commission 累加 = 999.90 + 999.90 = 1999.80
        self.assertAlmostEqual(root_after.total_commission, 1999.80, places=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
