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

    # ============== T3: 5 个成员 5 叉 MAX vs SUM ==============

    def test_t3_five_member_5ary_max_sum(self):
        """5 叉树, 5 个子区 PV = [100, 50, 50, 50, 50]
        MAX=100, SUM_rest=200
        pair = min(100, 200) = 100
        commission = 100 × 0.15 = 15
        carry_max = max(100-200, 0) = 0
        carry_rest_total = max(200-100, 0) = 100 → 按 4 个子区比例分 (各 50/200 = 25)
        """
        members = [self._make_member(f"N-T3-{i}", slot=i) for i in range(1, 6)]
        pvs = [100, 50, 50, 50, 50]
        for m, pv in zip(members, pvs):
            self._add_ledger(m, pv)

        result = settle_period(self.period_id, self.db, settled_by="test")

        # commission = 15
        self.assertAlmostEqual(result.total_commission, 15.0, places=2)
        # 总消耗 = 100
        self.assertEqual(result.total_pv_consumed, 100)
        # 验证 carry 分布: MAX 子区 (100) carry=0, 其余 4 子区 (50 each) carry 100/4=25 each
        carries = [result.carry_out_by_dist.get(f"N-T3-{i}", 0) for i in range(1, 6)]
        # MAX 子区 (N-T3-1, pv=100) → carry = 0
        # 其余 (pv=50) → carry = 25 each
        # sort: [0, 25, 25, 25, 25]
        self.assertEqual(sorted(carries), [0, 25, 25, 25, 25])
        # balances updated
        balances = []
        for i in range(1, 6):
            m = self.member_repo.get_by_dist_id(f"N-T3-{i}")
            balances.append(m.current_pv_balance)
        self.assertEqual(sorted(balances), [0, 25, 25, 25, 25])

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
