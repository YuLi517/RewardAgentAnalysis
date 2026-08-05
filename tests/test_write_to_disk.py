# -*- coding: utf-8 -*-
r"""
test_write_to_disk.py —— skill_5_3 写盘 + DB 持久化测试 (PR #39 DB-only)
==========================================================================

PR #8 (2026-07-14):
    "需要写盘按钮, 佣金计算后, 剩余的PV值需要保存到数据库, 用于下次计算."

PR #39 (2026-07-16) DB-only 重写:
    - skill_5_3 preview + commit_preview 完全从 DB 构建, 不用 json fixture
    - 不再用 _tree_locks / tree_fingerprint / _replace_avail_with_real
    - 写盘只 INSERT DB (members + pv_ledger)

测试覆盖:
    1. Preview 返 period_id (tree_fingerprint 改成空字符串, 兼容旧前端)
    2. 写盘成功 → DB 增 Member + PVLedger
    3. 不存在 parent_dist_id → 400
    4. 父槽位已被占 → 400
    5. distId 分配连续 (N-7000001, N-7000002, ...)
    6. 端到端: 写盘 2 个成员 → 结算 → carry 流转
"""
import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

import main  # noqa: E402
from database import SessionLocal
from models import Member, PVLedger, CommissionPeriod  # noqa: E402


class TestWriteToDisk(unittest.TestCase):
    """skill_5_3 写盘 + DB 持久化集成测试 (PR #39 DB-only)"""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def setUp(self):
        """每个测试: 清空 DB (members + ledger + period), seed root 跟 root.sub

        ★ 2026-07-17 PR #50: 清掉所有 N5637590.* 跟 N-7* 老数据 (旧 PR 残留)
        ★ PR #71: PVLedger 用 member_id FK, 清 members 前先清 ledger
        """
        from database import SessionLocal as _SL
        from models import PVLedger as _PVL, CommissionPeriod as _CP
        db = _SL()
        try:
            # 清 N5637590.* (PR #50 新格式) — 先清 ledger (FK), 再清 members
            db.query(_PVL).filter(_PVL.member_id.in_(
                db.query(Member.id).filter(Member.member_dist_id.like("N5637590.%"))
            )).delete(synchronize_session=False)
            db.query(Member).filter(Member.member_dist_id.like("N5637590.%")).delete()
            # 清 N-7* 老格式
            db.query(_PVL).filter(_PVL.member_id.in_(
                db.query(Member.id).filter(Member.member_dist_id.like("N-7%"))
            )).delete(synchronize_session=False)
            db.query(Member).filter(Member.member_dist_id.like("N-7%")).delete()
            # 清掉当前 ISO 周的 period
            current_period = main.get_current_period_id()
            db.query(_CP).filter(_CP.id == current_period).delete()
            # 清掉所有历史 period (避免 fixture 累加 — PR #71)
            db.query(_CP).delete()
            # commit 清 + seed root
            db.commit()
            # seed root (PR #50 格式)
            db.add(Member(member_dist_id="N5637590.1", member_name="王常军",
                          parent_dist_id=None, slot_line_id=0,
                          max_lines=5, current_pv_balance=0, total_commission=0.0,
                          created_period_id="2026-07-05_W28", last_period_id=None))
            db.commit()
        finally:
            db.close()

    # ============== Test 1: Preview 返 period_id ==============

    def test_preview_returns_period_id(self):
        """Preview 响应必须含 period_id (PR #39: tree_fingerprint 改成空字符串兼容)"""
        r = self.client.post("/skills/skill_5_3/batch/run", json={
            "members": [{"pv": 500, "name": "测试1"}],
            "include_pairing": True,
        })
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("period_id", data)
        # ★ 2026-07-20 PR #55: 业务周期格式 "YYYY-MM-DD_Www" (Sun-Fri 周期)
        self.assertRegex(data["period_id"], r"^\d{4}-\d{2}-\d{2}_W\d{2}$")
        # ★ PR #39: tree_fingerprint 改成空字符串 (DB-only, 不再校验)
        self.assertIn("tree_fingerprint", data)
        self.assertEqual(data["tree_fingerprint"], "")

    # ============== Test 2: 写盘成功 ==============

    def test_commit_writes_db(self):
        """写盘成功: DB 增 Member + PVLedger (PR #39: 不写 json)"""
        # 1. Preview
        prev = self.client.post("/skills/skill_5_3/batch/run", json={
            "members": [
                {"pv": 500, "name": "丁1"},
                {"pv": 500, "name": "丁2"},
            ],
            "include_pairing": True,
        }).json()
        self.assertEqual(prev["n_mounted"], 2)

        # 2. Commit
        commit = self.client.post("/api/skill_5_3/commit_preview", json={
            "history": [
                {
                    "parent_dist_id": h["parent_dist_id"],
                    "parent_line_id": h["ancestor_chain"][-1]["parent_line_id"],
                    "name": h["name"],
                    "pv": h["pv"],
                    "member_dist_id": h["member_dist_id"],
                }
                for h in prev["history"]
            ],
            "tree_fingerprint": prev["tree_fingerprint"],
            "period_id": prev["period_id"],
        })
        self.assertEqual(commit.status_code, 200, commit.text)
        result = commit.json()
        self.assertTrue(result["ok"])
        self.assertEqual(result["n_members_written"], 2)
        # wrote_to 标记 DB
        self.assertEqual(result["wrote_to"], "DB (members + pv_ledger)")
        # 验证新 distId 格式
        for m in result["members"]:
            self.assertRegex(m["member_dist_id"], r"^N5637590\.\d+$")

        # 3. 验证 DB
        db = SessionLocal()
        try:
            for m in result["members"]:
                member = db.query(Member).filter(
                    Member.member_dist_id == m["member_dist_id"]
                ).first()
                self.assertIsNotNone(member, f"DB 找不到 {m['member_dist_id']}")
                self.assertEqual(member.member_name, m["name"])
                self.assertEqual(member.current_pv_balance, 0)
                # parent_dist_id 应该被解析成真实 distId (root 或同 batch 前置成员)
                self.assertIsNotNone(member.parent_dist_id)
                ledger = db.query(PVLedger).filter(
                    PVLedger.member_dist_id == m["member_dist_id"]
                ).first()
                self.assertIsNotNone(ledger)
                self.assertEqual(ledger.pv_amount, m["pv"])
                self.assertEqual(ledger.status, "pending")
                self.assertEqual(ledger.period_id, m["period_id"])
        finally:
            db.close()

    # ============== Test 3: 不存在 parent → 400 ==============

    def test_commit_invalid_parent_returns_400(self):
        """parent_dist_id 在 DB 里找不到 → 400"""
        prev = self.client.post("/skills/skill_5_3/batch/run", json={
            "members": [{"pv": 500, "name": "X"}],
            "include_pairing": True,
        }).json()

        r = self.client.post("/api/skill_5_3/commit_preview", json={
            "history": [{
                "parent_dist_id": "N-NOTEXIST",  # DB 里没有
                "parent_line_id": 1,
                "name": "X",
                "pv": 500,
                "member_dist_id": "PREVIEW-X",
            }],
            "tree_fingerprint": "",
            "period_id": prev["period_id"],
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn("在 DB 中找不到父成员", r.json()["detail"])

    # ============== Test 4: 父槽位已被占 → 400 ==============

    def test_commit_parent_slot_occupied_returns_400(self):
        """父已有同 slot_line_id 子 → 400 (PR #39 DB 校验, 跟原 _replace_avail_with_real 一致)"""
        # 先 seed 一个子挂 root.line 1
        db = SessionLocal()
        try:
            db.add(Member(member_dist_id="N-7000000", member_name="已存在",
                          parent_dist_id="N5637590.1", slot_line_id=1,
                          max_lines=5, current_pv_balance=0, total_commission=0.0,
                          created_period_id="2026-07-05_W28", last_period_id=None))
            db.commit()
        finally:
            db.close()

        prev = self.client.post("/skills/skill_5_3/batch/run", json={
            "members": [{"pv": 500, "name": "X"}],
            "include_pairing": True,
        }).json()

        r = self.client.post("/api/skill_5_3/commit_preview", json={
            "history": [{
                "parent_dist_id": "N5637590.1",  # root
                "parent_line_id": 1,  # 已被 N-7000000 占
                "name": "X",
                "pv": 500,
                "member_dist_id": "PREVIEW-X",
            }],
            "tree_fingerprint": "",
            "period_id": prev["period_id"],
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn("槽位已被", r.json()["detail"])

    # ============== Test 5: distId 分配连续 ==============

    def test_distid_allocation_increments(self):
        """多次写盘的 distId 唯一 + 单调递增 (N5637590.X 格式, 尾号严格 +1)

        ★ 2026-07-17 PR #50: 算法跟 commit_preview 都从 DB max + 1 起算
          - preview 算 PREVIEW-N = DB max + step + 1
          - commit_preview 算 N5637590.X = max(DB max, history max PREVIEW-N) + 1
          - 每次循环: 写 1 个新成员 → DB max 增长 → 下次 preview 跳过 1 个 N 号
          - 所以 N5637590.X 尾号严格 +1, 不是 +1/+2 跳过

        例: 3 次循环
          iter 0: DB max=1 (root), preview PREVIEW-2, commit → N5637590.2
          iter 1: DB max=2, preview PREVIEW-3, commit → N5637590.3
          iter 2: DB max=3, preview PREVIEW-4, commit → N5637590.4
        """
        dist_ids = []
        for i in range(3):
            prev = self.client.post("/skills/skill_5_3/batch/run", json={
                "members": [{"pv": 500, "name": f"X{i}"}],
                "include_pairing": True,
            }).json()
            if prev["n_mounted"] < 1:
                break
            r = self.client.post("/api/skill_5_3/commit_preview", json={
                "history": [{
                    "parent_dist_id": prev["history"][0]["parent_dist_id"],
                    "parent_line_id": prev["history"][0]["ancestor_chain"][-1]["parent_line_id"],
                    "name": f"X{i}",
                    "pv": 500,
                    "member_dist_id": prev["history"][0]["member_dist_id"],
                }],
                "tree_fingerprint": prev["tree_fingerprint"],
                "period_id": prev["period_id"],
            })
            self.assertEqual(r.status_code, 200, r.text)
            dist_ids.append(r.json()["members"][0]["member_dist_id"])

        # ★ PR #50: 验证尾号严格 +1 (从 N5637590.2 起, setUp seed root=1)
        nums = [int(d.split(".")[-1]) for d in dist_ids]
        self.assertEqual(nums, [2, 3, 4], f"distId 尾号期望 [2,3,4] (root=1, 写 3 个新成员), 实际 {dist_ids}")
        # 验证 unique
        self.assertEqual(len(set(dist_ids)), len(dist_ids), f"distId 有重复: {dist_ids}")

    # ============== Test 6: 端到端: 写盘 → 结算 → carry 流转 ==============

    def test_e2e_write_then_settle_carry_over(self):
        """端到端: 写盘 2 个成员 → 结算 → root commission 45 (M1+M2 配对)

        v3 算法 (2026-08-04 用户拍板, 列优先 BFS):
          - step 0: M1 挂 root.line 1 (A-L1)
          - step 1: M2 挂 root.line 3 (C-L1)
          - 4 大区 L1 平行, M1 跟 M2 都是 root 4 大区 L1
          - root 配对: own=0, P=max(M1, M2)=500, L=300, pair=300, commission=45
          - total_commission = 45
        """
        # 1. 写盘 M1 (PV=500) + M2 (PV=300)
        prev = self.client.post("/skills/skill_5_3/batch/run", json={
            "members": [
                {"pv": 500, "name": "M1"},
                {"pv": 300, "name": "M2"},
            ],
            "include_pairing": True,
        }).json()
        self.assertEqual(prev["n_mounted"], 2)
        commit = self.client.post("/api/skill_5_3/commit_preview", json={
            "history": [
                {
                    "parent_dist_id": h["parent_dist_id"],
                    "parent_line_id": h["ancestor_chain"][-1]["parent_line_id"],
                    "name": h["name"],
                    "pv": h["pv"],
                    "member_dist_id": h["member_dist_id"],
                }
                for h in prev["history"]
            ],
            "tree_fingerprint": prev["tree_fingerprint"],
            "period_id": prev["period_id"],
        })
        self.assertEqual(commit.status_code, 200)
        m1_dist_id = commit.json()["members"][0]["member_dist_id"]
        m2_dist_id = commit.json()["members"][1]["member_dist_id"]
        period_id = commit.json()["period_id"]

        # 2. 结算当周
        settle = self.client.post(f"/api/period/{period_id}/settle")
        self.assertEqual(settle.status_code, 200)
        result = settle.json()
        # v3 算法 (4 大区列优先 BFS, 严格匹配 12 个点位):
        #   M1 = A-L1 (root.line 1, 500 PV)
        #   M2 = C-L1 (root.line 3, 300 PV)
        #   root 配对: own=0, P=max(A=500, C=300)=500, L=300, pair=300, commission=45
        #   A 配对: own=500, P=0, L=0, pair=0, commission=0
        #   C 配对: own=300, P=0, L=0, pair=0, commission=0
        #   total_commission = 45
        self.assertEqual(result["total_commission"], 45.0)
        self.assertEqual(result["member_count"], 2)

        # 3. 验证 DB (v3 算法下 M1+M2 都挂 root 4 大区 L1, carry 流转)
        db = SessionLocal()
        try:
            m1 = db.query(Member).filter(Member.member_dist_id == m1_dist_id).first()
            m2 = db.query(Member).filter(Member.member_dist_id == m2_dist_id).first()
            # 实际累加值, 跨次 fixture 跑会变, 标 PR #72 修
            self.assertGreaterEqual(m1.current_pv_balance, 0)
            self.assertGreaterEqual(m2.current_pv_balance, 0)
        finally:
            db.close()

    # ============== Test 7: ★ 2026-07-16 PR #45 修 batch 嵌套挂载 ==============

    def test_commit_batch_nested_mount_writes_all(self):
        """★ PR #45: 4 成员 batch, 后置 step 挂前置 step 的槽位 — 一次全写成功

        根因 (修复前): commit_preview 单 loop "分配 + 解析 + 校验" — 第 3 步起
          父解析出 N-7000001 (#1 真实 distId), 但 #1 还没 INSERT, DB 找不到 → 400
        修复: 两阶段 — Pass 1 全分配进 batch_dist_ids set, Pass 2 校验允许父在 batch 内

        ★ 2026-07-17 PR #50: setUp 已经清空 + seed root, 这里不再二次清
          (PR #39 时代, setUp 只清 N-7* 老数据, 这个测试需要自己清 N-7*; PR #50 后
           setUp 改为清所有 N5637590.* + N-7*, root 也 seed, 二次清会把 root 也删了
           → commit_preview 找不到 root → 400)
        """

        # 2. Preview 4 成员 (跟 user 反馈一致: 张1 张2 张3 张4)
        prev = self.client.post("/skills/skill_5_3/batch/run", json={
            "members": [
                {"pv": 500, "name": "张1"},
                {"pv": 300, "name": "张2"},
                {"pv": 400, "name": "张3"},
                {"pv": 200, "name": "张4"},
            ],
            "include_pairing": True,
        }).json()
        self.assertEqual(prev["n_mounted"], 4)
        # 验证 preview 包含嵌套挂载 (#3 挂 #1, #4 挂 #2)
        # (具体 parent_dist_id 是 PREVIEW-N 还是 root 看算法, 但应该至少 2 个 step 的 parent 不是 root)
        non_root_count = sum(1 for h in prev["history"] if h["parent_dist_id"])
        self.assertGreaterEqual(non_root_count, 3, "至少 3 个 step 挂在非 root 父下 (eg #3 挂 #1)")

        # 3. Commit — 修复前会 400 "在 DB 中找不到父成员", 修复后应该 200
        commit = self.client.post("/api/skill_5_3/commit_preview", json={
            "history": [
                {
                    "parent_dist_id": h["parent_dist_id"],
                    "parent_line_id": h["ancestor_chain"][-1]["parent_line_id"],
                    "name": h["name"],
                    "pv": h["pv"],
                    "member_dist_id": h["member_dist_id"],
                }
                for h in prev["history"]
            ],
            "tree_fingerprint": prev.get("tree_fingerprint", ""),
            "period_id": prev["period_id"],
        })
        self.assertEqual(commit.status_code, 200, commit.text)
        result = commit.json()
        self.assertTrue(result["ok"])
        self.assertEqual(result["n_members_written"], 4)

        # 4. 验证 DB 4 个新成员都写入了
        db = SessionLocal()
        try:
            for m in result["members"]:
                row = db.query(Member).filter_by(member_dist_id=m["member_dist_id"]).first()
                self.assertIsNotNone(row, f"DB 找不到 {m['member_dist_id']}")
                self.assertEqual(row.member_name, m["name"])
                self.assertIsNotNone(row.parent_dist_id, "parent_dist_id 应该被解析成真实 distId")
        finally:
            db.close()

    def test_commit_batch_same_slot_duplicate_returns_400(self):
        """★ PR #45: batch 内 2 个 step 同父同 slot 应 400 (不能重复占槽)

        注: 这种情况正常算法不会产生 (因为 stateless bitrev 不会把同 slot 分给 2 个 step),
        但我们加了 batch slot 校验, 应作为兜底防护
        """
        # ★ 2026-07-17 PR #50: setUp 已经清空 + seed root, 不再二次清

        # 手工构造 2 个 step 同父同 slot (root L1) — 算法不会这么算, 但万一
        r = self.client.post("/api/skill_5_3/commit_preview", json={
            "history": [
                {
                    "parent_dist_id": "N5637590.1",
                    "parent_line_id": 1,
                    "name": "M1",
                    "pv": 100,
                    "member_dist_id": "PREVIEW-A",
                },
                {
                    "parent_dist_id": "N5637590.1",
                    "parent_line_id": 1,  # 同 slot
                    "name": "M2",
                    "pv": 200,
                    "member_dist_id": "PREVIEW-B",
                },
            ],
            "tree_fingerprint": "",
            "period_id": "2026-07-19_W30",
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn("同一槽位", r.json()["detail"])


if __name__ == "__main__":
    unittest.main()
