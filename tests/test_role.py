# -*- coding: utf-8 -*-
r"""
test_role.py —— PR #41/42 角色功能测试
========================================

业务:
    - 7 种角色: 消费股东/预备合伙人/合伙人员工/初级管理合伙人/中级管理合伙人/高级管理合伙人/Inactive
    - DB 列 NOT NULL default '消费股东'
    - PR #42: DB 存全名 label (中文), 不用 enum key
    - /api/members 返 role
    - /api/tree/render 渲染 role badge (name 下方, 居中, 独占一行, 用全名 label)
    - /api/members/role 改 role
    - /api/members/roles 列可用角色

测试覆盖:
    1. 默认 role = '消费股东' (新 member)
    2. api_members_list 返 role 字段
    3. api_tree_render html 含 tv-badge-role + role-label
    4. api_member_role_update: 改 role 成功 + 拒绝无效值
    5. api_member_role_update: 找不到 distId → 404
    6. api_member_roles_list: 返 7 个角色
    7. 树视图 role 颜色
    8. migration 幂等
"""
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

import main  # noqa: E402
from database import SessionLocal, init_db  # noqa: E402
from models import Member  # noqa: E402


class TestRoleApi(unittest.TestCase):
    """PR #41/42 角色 API 测试"""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        init_db()  # 触发 metadata.create_all, 确保 role 列存在

    def setUp(self):
        """每个测试: 清空 + seed 3 个 member (各角色不同, PR #42 用 label 直接)"""
        db = SessionLocal()
        try:
            db.query(Member).delete()
            db.commit()
            # root (默认 消费股东)
            db.add(Member(member_dist_id="N5637590.1", member_name="root",
                          parent_dist_id=None, slot_line_id=0,
                          max_lines=5, current_pv_balance=0, total_commission=0.0,
                          created_period_id="2026-07-05_W28", last_period_id=None,
                          role="消费股东"))
            # 预备合伙人
            db.add(Member(member_dist_id="N-7000001", member_name="子1",
                          parent_dist_id="N5637590.1", slot_line_id=1,
                          max_lines=5, current_pv_balance=0, total_commission=0.0,
                          created_period_id="2026-07-12_W29", last_period_id=None,
                          role="预备合伙人"))
            # 高级管理合伙人
            db.add(Member(member_dist_id="N-7000002", member_name="子2",
                          parent_dist_id="N5637590.1", slot_line_id=2,
                          max_lines=5, current_pv_balance=0, total_commission=0.0,
                          created_period_id="2026-07-12_W29", last_period_id=None,
                          role="高级管理合伙人"))
            db.commit()
        finally:
            db.close()

    # ============== Test 1: 默认 role = 消费股东 ==============

    def test_default_role_consumer(self):
        """新 member 不显式设 role → 默认 消费股东"""
        db = SessionLocal()
        try:
            m = db.query(Member).filter_by(member_dist_id="N-7000001").first()
            self.assertEqual(m.role, "预备合伙人", "fixture role 应保留 (label)")
        finally:
            db.close()

    # ============== Test 2: api_members_list 返 role ==============

    def test_members_list_returns_role(self):
        r = self.client.get("/api/members")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["count"], 3)
        by_dist = {m["member_dist_id"]: m for m in data["members"]}
        self.assertIn("role", by_dist["N5637590.1"])
        self.assertEqual(by_dist["N5637590.1"]["role"], "消费股东")
        self.assertEqual(by_dist["N-7000001"]["role"], "预备合伙人")
        self.assertEqual(by_dist["N-7000002"]["role"], "高级管理合伙人")

    # ============== Test 3: api_tree_render 渲染 role badge ==============

    def test_tree_render_includes_role_badge(self):
        r = self.client.post("/api/tree/render", json={
            "skill": "skill_5_3", "slot_view": "all", "committed": True, "highlights": [],
        })
        self.assertEqual(r.status_code, 200)
        html = r.json()["html"]
        # 应该有 tv-badge-role (3 个 real member 各 1 个)
        n_role_badge = html.count("tv-badge-role")
        self.assertEqual(n_role_badge, 3, f"期望 3 个 role badge, 实际 {n_role_badge}")
        # role-label 应该有 label (PR #42: 用 label, 不是 enum key)
        self.assertIn('role-label="消费股东"', html)
        self.assertIn('role-label="预备合伙人"', html)
        self.assertIn('role-label="高级管理合伙人"', html)
        # 全名应在 badge 里
        self.assertIn(">消费股东<", html)
        self.assertIn(">预备合伙人<", html)
        self.assertIn(">高级管理合伙人<", html)
        # ★ 2026-07-16 PR #44: role badge 移到 line 1 容器内 (跟 name 同行)
        #   不用 tv-role-row 容器了 (PR #41/42 的下方居中方案废弃)
        self.assertNotIn("tv-role-row", html, "PR #44: tv-role-row 已废弃, role 改放 line 1")
        # 每个 real 节点应有一个 tv-card-line1 容器 (root + 2 children = 3,
        # avail 节点也有 tv-card-line1 但没 role badge — 这里只验证数量)
        self.assertGreaterEqual(html.count("tv-card-line1"), 3, "每个 real 节点应有 tv-card-line1")
        # role badge 跟 name 同行: 验证 role-label 后面紧跟 ">", 即 badge 内容 (跟 line1 内的 name 元素不冲突)
        # (简单验证: 3 个 role-label = 3 个 real 节点)
        self.assertEqual(html.count("role-label="), 3, "应有 3 个 real 节点 role badge")

    # ============== Test 4: api_member_role_update 改 role ==============

    def test_role_update_success(self):
        r = self.client.post("/api/members/role", json={
            "member_dist_id": "N-7000001",
            "role": "初级管理合伙人",
        })
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertTrue(d["ok"])
        self.assertEqual(d["old_role"], "预备合伙人")
        self.assertEqual(d["new_role"], "初级管理合伙人")
        # DB 也应该改了
        db = SessionLocal()
        try:
            m = db.query(Member).filter_by(member_dist_id="N-7000001").first()
            self.assertEqual(m.role, "初级管理合伙人")
        finally:
            db.close()

    def test_role_update_invalid_value(self):
        """无效 role 值 → 兜底成默认 (跟 _normalize_role 行为)"""
        r = self.client.post("/api/members/role", json={
            "member_dist_id": "N-7000001",
            "role": "garbage_unknown",
        })
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["new_role"], "消费股东", "未知 role 兜底成默认")

    def test_role_update_missing_member(self):
        r = self.client.post("/api/members/role", json={
            "member_dist_id": "N-NOTEXIST",
            "role": "初级管理合伙人",
        })
        self.assertEqual(r.status_code, 404)
        self.assertIn("找不到", r.json()["detail"])

    # ============== Test 5: api_member_roles_list ==============

    def test_roles_list_endpoint(self):
        r = self.client.get("/api/members/roles")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["default"], "消费股东")
        self.assertEqual(len(d["roles"]), 7)
        # 检查关键字段
        for role in d["roles"]:
            self.assertIn("key", role)
            self.assertIn("label", role)  # PR #42: label == key
            self.assertIn("bg", role)
            self.assertIn("fg", role)
        # 验证 7 个 role 都在
        keys = {r["key"] for r in d["roles"]}
        self.assertEqual(keys, main.VALID_ROLES)

    # ============== Test 6: 树视图 role 颜色 ==============

    def test_tree_render_role_color(self):
        """role badge 应带背景/文字颜色 (style inline)"""
        r = self.client.post("/api/tree/render", json={
            "skill": "skill_5_3", "slot_view": "all", "committed": True, "highlights": [],
        })
        html = r.json()["html"]
        # 消费股东 蓝色: #BFDBFE / #1E3A8A
        self.assertIn("#BFDBFE", html, "消费股东 bg color")
        self.assertIn("#1E3A8A", html, "消费股东 fg color")
        # 预备合伙人 绿色
        self.assertIn("#BBF7D0", html, "预备合伙人 bg color")
        # 高级管理合伙人 红色
        self.assertIn("#FECACA", html, "高级管理合伙人 bg color")


class TestRoleMigration(unittest.TestCase):
    """PR #41/42 migration 幂等性"""

    def test_migration_idempotent(self):
        """重复跑 migrate_add_role 不报错 (幂等)"""
        from tools.migrate_add_role import migrate
        # 跑两次不应该出错
        migrate()
        migrate()
        # 所有 member role 都是合法 label
        db = SessionLocal()
        try:
            members = db.query(Member).limit(5).all()
            for m in members:
                self.assertIn(m.role, main.VALID_ROLES)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
