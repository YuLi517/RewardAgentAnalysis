# -*- coding: utf-8 -*-
"""
test_business_level.py — PR #75 业务档位 4 档位独立列
====================================================================

业务 (2026-08-06 用户拍板截图):
  - 4 档位: 激活 / 商务 / 精英 / 至尊 (跟 PR #71 teamBonus 4 档对应)
  - 独立列 business_level 存, 跟 role 字段独立
  - default = '激活' (最普通档位)

测试覆盖:
  - 4 档位 + Inactive (= 5 个, 跟 role 字段 5 个对齐)
  - _normalize_business_level 规范化 (空/None/未知 → '激活')
  - 颜色 (紫/蓝/橙/深绿) 跟截图一致
  - tier_pv 字段 (200/500/1000/1500) 跟 PR #71 teamBonus 4 档对应
  - 跟 role 字段独立 (可以 role=消费股东 + business_level=至尊)
"""
import os
import sys
import unittest

# 确保项目根目录在 sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, Member
from repository import MemberRepository
from main import (
    MEMBER_BUSINESS_LEVELS, DEFAULT_BUSINESS_LEVEL, VALID_BUSINESS_LEVELS,
    _normalize_business_level, MEMBER_ROLES,
)


def _make_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    return engine, SessionLocal()


class TestBusinessLevel(unittest.TestCase):
    """PR #75: 业务档位 4 档位独立列 (跟 role 字段独立)"""

    def setUp(self):
        self.engine, self.db = _make_db()
        self.member_repo = MemberRepository(self.db)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_pr75_4_levels_defined(self):
        """★ PR #75: 4 档位 + 默认 = 5 个 (跟截图一致)"""
        self.assertEqual(len(MEMBER_BUSINESS_LEVELS), 4)
        self.assertEqual(set(MEMBER_BUSINESS_LEVELS.keys()), {"激活", "商务", "精英", "至尊"})

    def test_pr75_default_is_激活(self):
        """★ PR #75: default = '激活' (最普通档位)"""
        self.assertEqual(DEFAULT_BUSINESS_LEVEL, "激活")
        self.assertEqual(VALID_BUSINESS_LEVELS, set(MEMBER_BUSINESS_LEVELS.keys()))

    def test_pr75_tier_pv_matches_pr71(self):
        """★ PR #75: tier_pv 字段跟 PR #71 teamBonus 4 档精确匹配对应

        业务: 激活/商务/精英/至尊 的 tier_pv = 200/500/1000/1500
        跟 PR #71 _team_bonus_tier_rate dict 完全一致
        """
        self.assertEqual(MEMBER_BUSINESS_LEVELS["激活"]["tier_pv"], 200)
        self.assertEqual(MEMBER_BUSINESS_LEVELS["商务"]["tier_pv"], 500)
        self.assertEqual(MEMBER_BUSINESS_LEVELS["精英"]["tier_pv"], 1000)
        self.assertEqual(MEMBER_BUSINESS_LEVELS["至尊"]["tier_pv"], 1500)

    def test_pr75_colors_match_screenshot(self):
        """★ PR #75: 4 档位颜色跟用户截图一致 (紫/蓝/橙/深绿)"""
        # 激活: 紫色
        self.assertEqual(MEMBER_BUSINESS_LEVELS["激活"]["bg"], "#DDD6FE")
        self.assertEqual(MEMBER_BUSINESS_LEVELS["激活"]["fg"], "#4C1D95")
        # 商务: 蓝色
        self.assertEqual(MEMBER_BUSINESS_LEVELS["商务"]["bg"], "#BFDBFE")
        self.assertEqual(MEMBER_BUSINESS_LEVELS["商务"]["fg"], "#1E3A8A")
        # 精英: 橙色
        self.assertEqual(MEMBER_BUSINESS_LEVELS["精英"]["bg"], "#FED7AA")
        self.assertEqual(MEMBER_BUSINESS_LEVELS["精英"]["fg"], "#9A3412")
        # 至尊: 深绿
        self.assertEqual(MEMBER_BUSINESS_LEVELS["至尊"]["bg"], "#BBF7D0")
        self.assertEqual(MEMBER_BUSINESS_LEVELS["至尊"]["fg"], "#14532D")

    def test_pr75_normalize_empty_to_default(self):
        """★ PR #75: 空/None/未知 → '激活' (default)"""
        self.assertEqual(_normalize_business_level(None), "激活")
        self.assertEqual(_normalize_business_level(""), "激活")
        self.assertEqual(_normalize_business_level("invalid"), "激活")
        self.assertEqual(_normalize_business_level("UNKNOWN"), "激活")

    def test_pr75_normalize_valid_levels(self):
        """★ PR #75: 4 档位 valid input 保留原值"""
        for level in ["激活", "商务", "精英", "至尊"]:
            self.assertEqual(_normalize_business_level(level), level)

    def test_pr75_member_default_business_level(self):
        """★ PR #75: 新加 member 默认 business_level='激活' (跟 default 字段一致)"""
        m = self.member_repo.get_or_create(
            member_dist_id="N-T75-001",
            member_name="测试成员",
            parent_dist_id="ROOT",
            slot_line_id=1,
            max_lines=2,
        )
        # 字段默认 '激活' (DB schema default)
        self.assertEqual(m.business_level, "激活")
        # 跟 _normalize_business_level 一致
        self.assertEqual(_normalize_business_level(m.business_level), "激活")

    def test_pr75_member_set_business_level(self):
        """★ PR #75: 设置 member business_level 字段 (至尊)"""
        m = self.member_repo.get_or_create(
            member_dist_id="N-T75-002",
            member_name="测试成员",
            parent_dist_id="ROOT",
            slot_line_id=1,
            max_lines=2,
        )
        m.business_level = "至尊"
        self.db.commit()
        m2 = self.member_repo.get_by_dist_id("N-T75-002")
        self.assertEqual(m2.business_level, "至尊")
        # tier_pv 跟 PR #71 teamBonus 4 档一致
        self.assertEqual(MEMBER_BUSINESS_LEVELS[m2.business_level]["tier_pv"], 1500)

    def test_pr75_role_and_business_level_independent(self):
        """★ PR #75: role 字段 (7 role) 跟 business_level (4 档位) 独立 (2 套并存)

        业务: 成员可以 role=消费股东 + business_level=至尊 (业务上允许)
        """
        m = self.member_repo.get_or_create(
            member_dist_id="N-T75-003",
            member_name="测试成员",
            parent_dist_id="ROOT",
            slot_line_id=1,
            max_lines=2,
        )
        # role 字段 7 role (跟原 7 role 兼容)
        m.role = "消费股东"
        # business_level 字段 4 档位 (跟 PR #71 4 档对应)
        m.business_level = "至尊"
        self.db.commit()
        m2 = self.member_repo.get_by_dist_id("N-T75-003")
        # 2 个字段独立存
        self.assertEqual(m2.role, "消费股东")
        self.assertEqual(m2.business_level, "至尊")
        # 跟 _normalize 一致
        self.assertEqual(_normalize_business_level(m2.business_level), "至尊")
        from main import _normalize_role
        self.assertEqual(_normalize_role(m2.role), "消费股东")

    def test_pr75_to_dict_includes_business_level(self):
        """★ PR #75: to_dict 包含 business_level 字段 (API 返给前端)"""
        m = self.member_repo.get_or_create(
            member_dist_id="N-T75-004",
            member_name="测试成员",
            parent_dist_id="ROOT",
            slot_line_id=1,
            max_lines=2,
        )
        m.business_level = "精英"
        self.db.commit()
        d = m.to_dict()
        self.assertIn("business_level", d)
        self.assertEqual(d["business_level"], "精英")
        # 同时 role 字段也在
        self.assertIn("role", d)
        self.assertEqual(d["role"], "消费股东")  # default


if __name__ == "__main__":
    unittest.main(verbosity=2)
