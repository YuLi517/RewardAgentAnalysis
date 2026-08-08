# -*- coding: utf-8 -*-
"""
models.py —— SQLAlchemy 2.x ORM 模型
=====================================

四张表：

  sessions
    - id (TEXT, UUID)
    - title (TEXT, 默认 "新会话"，首条 user 消息自动生成)
    - created_at / updated_at (REAL, unix timestamp)
    - request_count / total_tokens (INTEGER)
    - primary_provider (TEXT, 可选，默认 provider)
    - metadata_json (TEXT, 备用 JSON)

  messages
    - id (INTEGER, autoincrement)
    - session_id (FK → sessions.id, ON DELETE CASCADE)
    - role (TEXT: 'user' | 'assistant' | 'system')
    - content (TEXT, 消息正文)
    - reasoning (TEXT, 思考过程，可选，DeepSeek-R1 / o1 风格)
    - provider / model (TEXT, 实际调用的 provider 和 model)
    - prompt_tokens / completion_tokens / total_tokens (INTEGER)
    - is_fallback (INTEGER 0/1, 是否 fallback 后生成)
    - latency_ms (INTEGER, 该次调用延迟)
    - created_at (REAL)

设计要点：
    1. 时间用 REAL 存 unix timestamp（秒），不用 datetime —— SQLite 原生支持，
       后期切 PG 也只需改 Column 类型，代码层不动。
    2. messages.session_id 加 INDEX，便于按会话查全部消息 + 翻页。
    3. sessions 加 INDEX on updated_at DESC，侧栏按"最近活动"排序。
    4. CASCADE：删 session 时自动删 messages。
    5. messages 的 content 用 TEXT 而不是 VARCHAR —— 不限长度。
    6. relationship 加 lazy='selectin'，避免 N+1 查询。
    7. SQLAlchemy 2.x 用 Mapped[] 注解 relationship（替代旧式 Column/relationship 分开声明）。

★ 2026-07-12 移除:Document + Chunk 表 (Stage 2C 知识库/RAG)。
    - 原 documents 表 + chunks 表整段下线
    - 业务侧只保留 chat (multi-turn 对话) + skills (网体算法) 两条主线
    - 升级前用户上传的 documents 仍在 SQLite DB 里,但 API 不再暴露
      (Base.metadata.create_all 不会主动 drop,需要的话用 ORM 手动 DROP TABLE)
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    String, Integer, Text, Float, Boolean, ForeignKey, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, declarative_base

Base = declarative_base()


# ============== sessions ==============

class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="新会话")
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=lambda: datetime.now().timestamp())
    updated_at: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=lambda: datetime.now().timestamp(),
        index=True,  # 侧栏按 updated_at DESC 排序
    )
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    primary_provider: Mapped[Optional[str]] = mapped_column(String(64))
    metadata_json: Mapped[Optional[str]] = mapped_column(Text)  # 备用 JSON 字段（Stage 3+ tags/tenant 用）

    messages: Mapped[List["Message"]] = relationship(
        "Message",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
        lazy="selectin",
    )

    def to_meta_dict(self) -> dict:
        """侧栏列表用的精简字段（不含 messages 完整内容）"""
        return {
            "session_id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "request_count": self.request_count,
            "total_tokens": self.total_tokens,
            "primary_provider": self.primary_provider,
            "message_count": len(self.messages) if self.messages else 0,
        }

    def __repr__(self):
        return f"<Session id={self.id[:8]}... title={self.title!r} msgs={len(self.messages or [])}>"


# ============== messages ==============

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # 'user' / 'assistant' / 'system'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning: Mapped[Optional[str]] = mapped_column(Text)
    provider: Mapped[Optional[str]] = mapped_column(String(64))
    model: Mapped[Optional[str]] = mapped_column(String(128))
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_fallback: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0 / 1
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=lambda: datetime.now().timestamp())

    session: Mapped["Session"] = relationship("Session", back_populates="messages")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "reasoning": self.reasoning,
            "provider": self.provider,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "is_fallback": bool(self.is_fallback),
            "latency_ms": self.latency_ms,
            "created_at": self.created_at,
        }

    def __repr__(self):
        snippet = (self.content or "")[:30].replace("\n", " ")
        return f"<Message id={self.id} role={self.role} {snippet!r}>"


# ============== 复合索引 ==============

# messages 按 session + created_at 查（侧栏加载历史用）
Index("idx_messages_session_created", Message.session_id, Message.created_at)


# ============================================================
# 业务侧表 (2026-07-14 v1) — 周 commission 结算模型
# ============================================================
# 用户拍板的 C 路径算法:
#   1. 配对规则 = officev2 5 叉动力线 MAX vs SUM (复用 skill_5_lib.basic_commission)
#   2. 周期 = ISO 周 (e.g. "2026-W28", 周一到周日)
#   3. carry = 按成员本人 (成员不管挂哪都带自己的 PV 余额)
#   4. carry 混当周新一起配对 (carry_in + 本周新增 = 当期可配对池)
#   5. commission rate = 15% (写死, 跟 officev2 一致)
#   6. commission 分配 = 7 代祖先链分润 [0.15, 0.10, 0.05×5] (officev2 原版)
#
# 4 张新表 (本文件加 3 张, pv_ledger 在下面):
#   members: 每个挂入的成员一行 (持久化 metadata + 当前 PV 余额)
#   pv_ledger: 每次新增 PV 一行流水 (status: pending/paired/carried)
#   commission_periods: 结算期 (ISO 周, status: open/settled)
#   commission_records: (待加, PR-B 阶段) 每次结算每个成员拿到的 commission 记录

class Member(Base):
    """每个挂入网体的成员一行 (成员级 PV 余额载体)

    设计要点:
      1. member_dist_id 唯一 (e.g. "N9000003.1" officev2 真实号, 或 "PREVIEW-N" 预览)
      2. current_pv_balance = 跨周累积的 PV 余额 (carry + 上周未配对完)
         每次挂入新 PV 时: balance += pv_amount
         每次结算完成时: balance = carry_out (剩余 PV)
      3. last_period_id = 上次结算的 period (便于追溯)
      4. parent_dist_id + slot_line_id = 挂载位置 (即使成员被移走, 余额跟着成员走)
    """
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    member_dist_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True,
    )
    member_name: Mapped[Optional[str]] = mapped_column(String(128))
    parent_dist_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    slot_line_id: Mapped[Optional[int]] = mapped_column(Integer)
    max_lines: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    # ★ PV 余额核心字段
    current_pv_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # ★ 累计 commission (元/PV, 历史总和, 便于侧栏/dashboard 显示)
    total_commission: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # ★ 2026-08-06 PR #73: 储蓄奖金累计 (美元, 跟 current_pv_balance 独立, 不混)
    #   - 跨期累计, 每周 settle 时累加 (主 settle + 补录都加, 跟 ownBasic 同步算)
    #   - 业务: ownBasic ≥ $250 时, savings = min(ownBasic × 15%, $500) 累加
    #   - 跟 commission 字段不同: commission 是 ¥ (PV × 15%), savings 是 USD (commission × 15%)
    savings_balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # ★ 2026-07-16 PR #41/42: 角色标签 (人工在 /add 时选, 后续可改)
    #   - NOT NULL: 每个 member 都有显式角色 (默认 '消费股东')
    #   - 7 种角色 (存全名 label, 不用 enum key):
    #     消费股东 / 预备合伙人 / 合伙人员工 / 初级管理合伙人 / 中级管理合伙人 / 高级管理合伙人 / Inactive
    #   - PR #42: 改 default 为中文 label, 改 String(32) → String(64) 容纳长 label
    #   - 角色常量 + 颜色: 跟 MEMBER_ROLES (main.py) 保持一致
    #   - migration: tools/migrate_add_role.py (幂等, 含 enum key → label 映射)
    role: Mapped[str] = mapped_column(
        String(64), nullable=False, default="消费股东", index=True,
    )
    # ★ 2026-08-06 PR #75: 业务档位 (business_level) — 4 档位独立列, 跟 role 字段独立
    #   - 用户拍板 (2026-08-06): 4 档位用独立列 business_level 存, 不替换 role
    #   - 4 档位: 激活 / 商务 / 精英 / 至尊 (跟 PR #71 teamBonus 4 档精确匹配对应)
    #     - 激活: 200 PV / 15% 培育金 (PR #71 tier rate)
    #     - 商务: 500 PV / 20% 培育金
    #     - 精英: 1000 PV / 25% 培育金
    #     - 至尊: 1500 PV / 30% 培育金
    #   - 业务定位: 业务上 4 档位 跟 PV / max_lines / 培育金 比率对应 (跟 PR #71 一致)
    #     - 业务字段 (PV/max_lines) 跟 business_level 字段独立 (用户自己填, 业务上允许不一致)
    #     - 默认 default = '激活' (最普通档位, 跟原 role 字段 '消费股东' 类似)
    #   - 跟 role 字段关系: 独立 (role 跟 business_level 是 2 个不同维度)
    #     - role 字段 7 role 保留 (badge 身份)
    #     - business_level 字段 4 档位 (业务档位)
    #   - migration: tools/migrate_pr75_business_level.py (幂等, ALTER TABLE + backfill '激活')
    business_level: Mapped[str] = mapped_column(
        String(32), nullable=False, default="激活", index=True,
    )
    # ★ 期间
    created_period_id: Mapped[Optional[str]] = mapped_column(String(16), index=True)
    last_period_id: Mapped[Optional[str]] = mapped_column(String(16))
    # ★ 时间
    created_at: Mapped[float] = mapped_column(
        Float, nullable=False, default=lambda: datetime.now().timestamp(),
    )
    updated_at: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=lambda: datetime.now().timestamp(),
        onupdate=lambda: datetime.now().timestamp(),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "member_dist_id": self.member_dist_id,
            "member_name": self.member_name,
            "parent_dist_id": self.parent_dist_id,
            "slot_line_id": self.slot_line_id,
            "max_lines": self.max_lines,
            "current_pv_balance": self.current_pv_balance,
            "total_commission": self.total_commission,
            "savings_balance": self.savings_balance,  # ★ 2026-08-06 PR #73
            "role": self.role,  # ★ 2026-07-16 PR #41/42 (7 role 字段)
            "business_level": self.business_level,  # ★ 2026-08-06 PR #75 (4 档位独立列)
            "created_period_id": self.created_period_id,
            "last_period_id": self.last_period_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def __repr__(self):
        return (
            f"<Member id={self.id} dist={self.member_dist_id!r} "
            f"name={self.member_name!r} balance={self.current_pv_balance}>"
        )


class PVLedger(Base):
    """每次新增 PV 一行流水 (PV 进出明细, 跨期追踪)

    状态机:
      pending  -> 用户挂入新成员, 等待当期结算
      paired   -> 当期结算时被配对消耗 (有 paired_with_member_id + contribution_pv)
      carried  -> 当期结算时未配对完, 跨期带到下一期 (status 转 carried, 然后下一期重新按 pending 算)

    一行 ledger = 一次"PV 注入事件", 配对消耗可能跨多期 (但通常一期就清掉)
    """
    __tablename__ = "pv_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    member_dist_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    period_id: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    pv_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    # 状态
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", index=True,
    )  # 'pending' | 'paired' | 'carried'
    # 配对信息 (status=paired 时填)
    paired_with_member_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("members.id"),
    )
    paired_with_dist_id: Mapped[Optional[str]] = mapped_column(String(64))
    contribution_pv: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    commission_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # 时间
    created_at: Mapped[float] = mapped_column(
        Float, nullable=False, default=lambda: datetime.now().timestamp(),
    )
    resolved_at: Mapped[Optional[float]] = mapped_column(Float)
    # 备注
    note: Mapped[Optional[str]] = mapped_column(Text)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "member_id": self.member_id,
            "member_dist_id": self.member_dist_id,
            "period_id": self.period_id,
            "pv_amount": self.pv_amount,
            "status": self.status,
            "paired_with_member_id": self.paired_with_member_id,
            "paired_with_dist_id": self.paired_with_dist_id,
            "contribution_pv": self.contribution_pv,
            "commission_amount": self.commission_amount,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "note": self.note,
        }

    def __repr__(self):
        return (
            f"<PVLedger id={self.id} member={self.member_dist_id!r} "
            f"period={self.period_id!r} pv={self.pv_amount} status={self.status}>"
        )


class CommissionPeriod(Base):
    """结算期 (业务周, e.g. "2026-07-12_W29")

    业务规则 (2026-07-20 PR #55):
      - 周期范围: Sun 00:00 → Fri 23:59:59.999 (6 天)
      - 补录窗口: Sat 00:00 → Mon 23:59:59.999 (3 天)
      - 关闭期: Tue 00:00 起, 周期彻底结束

    状态:
      open        -> 本期还有 pending ledger, 尚未结算
      settled     -> 本期已结算, 处于补录窗口期 (Sat-Mon)
                     supplement_until_ts 之前还可以补基本 commission
      closed      -> 补录窗口已结束 (Tue 起), 不能再补
                     等同旧 settled, 保留做兼容
    """
    __tablename__ = "commission_periods"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # "2026-07-12_W29"
    period_type: Mapped[str] = mapped_column(String(16), nullable=False, default="weekly")
    start_at: Mapped[float] = mapped_column(Float, nullable=False)  # Sun 00:00 ts
    end_at: Mapped[float] = mapped_column(Float, nullable=False)    # Fri 23:59:59.999 ts
    # ★ 2026-07-20 PR #55: 补录截止时间 (Mon 23:59:59.999 ts)
    #   - settled 时算 = end_at + 3 天 (Sat + Sun + Mon)
    #   - 现在 < supplement_until_ts → 还能补基本 commission
    #   - 现在 >= supplement_until_ts → 不能再补
    #   - open 状态时 = None (本期还没 settle, 谈不到补录)
    supplement_until_ts: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open", index=True,
    )  # 'open' | 'settled' | 'closed'
    total_commission: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_pv_consumed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_pv_carried: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    settled_at: Mapped[Optional[float]] = mapped_column(Float)
    settled_by: Mapped[Optional[str]] = mapped_column(String(64))  # admin user / "system"
    # ★ 2026-07-20 PR #55: 补录 commission 总和 (基本 only, 对等不补)
    #   - 区分 main settle commission (含对等) vs supplement commission (仅基本)
    supplement_commission: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    supplement_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[float] = mapped_column(
        Float, nullable=False, default=lambda: datetime.now().timestamp(),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "period_type": self.period_type,
            "start_at": self.start_at,
            "end_at": self.end_at,
            "status": self.status,
            "total_commission": self.total_commission,
            "total_pv_consumed": self.total_pv_consumed,
            "total_pv_carried": self.total_pv_carried,
            "member_count": self.member_count,
            "settled_at": self.settled_at,
            "settled_by": self.settled_by,
            "note": self.note,
            "created_at": self.created_at,
        }

    def __repr__(self):
        return (
            f"<CommissionPeriod id={self.id!r} status={self.status} "
            f"total={self.total_commission:.2f}>"
        )


# ============== 业务表复合索引 ==============
# pv_ledger 按 period + status 查 (结算时拉所有 pending)
Index("idx_pv_ledger_period_status", PVLedger.period_id, PVLedger.status)
# commission_periods 按 end_at DESC 查 (列表按时间倒序)
Index("idx_periods_end_at", CommissionPeriod.end_at.desc())


# ============================================================
# ★ 2026-07-27 PR #70: 下单管理 (order_items)
#   - 用户 2026-07-27 反馈的「下单管理」按钮
#   - 一张表显示:品名 / 单位 / 需求总数 / 当前库存 / 单品差额 / 套组 / 套组价格 / 总金额
#   - 业务规则:
#     - 单品差额 = 当前库存 - 需求总数 (实时算, 不存)
#     - 总金额 = 套组 × 套组价格 (实时算, 不存)
#     - 合计 = SUM(总金额) (前端算)
#     - 客户增加需求数量时, 当前库存自动按差量减少 (用户拍板 PR #70)
# ============================================================
class OrderItem(Base):
    """下单管理 — 每次备货一行

    设计要点:
      1. name 唯一 (品名, e.g. "活性辅酶")
      2. unit (单位: 瓶/袋/套)
      3. required_qty 跟 current_stock 都是 Integer (瓶/袋/套的整数计数)
      4. package_count 跟 package_price 算 总金额 (单套组的价格)
      5. sort_order 用于前端表格显示顺序
      6. 单品差额 (库存 - 需求) + 总金额 (套组 × 套组价格) 都是前端实时算, 不存 DB
    """
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    unit: Mapped[str] = mapped_column(String(8), nullable=False, default="瓶")
    required_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    package_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    package_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    # ★ 2026-07-27 PR #70: created_at 跟 updated_at 跟其他表保持一致
    created_at: Mapped[float] = mapped_column(
        Float, nullable=False, default=lambda: datetime.now().timestamp(),
    )
    updated_at: Mapped[float] = mapped_column(
        Float, nullable=False, default=lambda: datetime.now().timestamp(),
        onupdate=lambda: datetime.now().timestamp(),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "unit": self.unit,
            "required_qty": self.required_qty,
            "current_stock": self.current_stock,
            "package_count": self.package_count,
            "package_price": self.package_price,
            "sort_order": self.sort_order,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def __repr__(self):
        return (
            f"<OrderItem id={self.id} name={self.name!r} "
            f"required_qty={self.required_qty} stock={self.current_stock}>"
        )


# ============================================================
# ★ 2026-08-07 P1 PR3 Task 1: Scenario ORM (40 列, scenarios 表)
#   - 大重构 (2026-08-07 拍板) — 运营系统改造成"分析推理系统" (招商/路演实时计算器)
#   - 4 组参数 (TreeShape/Growth/Revenue/CommissionConfig) 拍平 40 列存 SQLite
#   - 客户路演实时调参: POST /api/scenarios 创建, 2 × GET 读
#   - 派生字段 (total_target/total_weeks/total_months) 也存表 (避免重复算)
#   - JSON 字段 (tree_layer_counts_json/cc_team_bonus_tier_rates_json/cc_pair_bonus_ratios_json/
#     cc_leader_dividend_tiers_json/cc_horizontal_leader_tiers_json/revenue_color_names_json)
#     6 个 JSON 字段 + 34 个标量 = 40 列
# ============================================================
class Scenario(Base):
    """场景: 4 组参数拍平 40 列, 客户路演实时调参用

    业务定位 (P1 大重构):
      - 客户: 调 4 组参数, 实时看 8 种报酬在 X 月累计
      - 路演: 1 次 session 多 scenarios 对比, 选最优
      - PR3: 持久化 (这表) + 3 个 FastAPI 路由

    设计要点:
      1. 4 个嵌套 dataclass (TreeShape/Growth/Revenue/CommissionConfig) 拍平 40 列
      2. JSON 字段用 Text 存 (SQLite 原生支持, 避免 JSONB 复杂度)
      3. Boolean 字段存 0/1 (SQLAlchemy 自动转)
      4. 派生字段 (total_target/total_weeks/total_months) 也存, 避免重复算
      5. 缓存绑定到 id(scenario_instance) 不是 row id, 防内存泄漏
    """
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # ★ created_at 用 String(32) 存 ISO ts (PR3 plan 拍板, 跟其他 Float 风格不同)
    #   - 业务: 客户看场景列表按创建时间排序, 字符串比 Float 易读
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)

    # ============== tree_shape (4 列) ==============
    tree_fork_type: Mapped[str] = mapped_column(String(16), nullable=False)
    tree_max_level: Mapped[int] = mapped_column(Integer, nullable=False)
    tree_layer_counts_json: Mapped[str] = mapped_column(Text, nullable=False)

    # ============== growth (4 列) ==============
    growth_nodes_per_region_per_week: Mapped[int] = mapped_column(Integer, nullable=False)
    growth_n_regions: Mapped[int] = mapped_column(Integer, nullable=False)
    growth_join_strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    growth_weeks_per_month: Mapped[int] = mapped_column(Integer, nullable=False)

    # ============== revenue (4 列) ==============
    revenue_initial_pv: Mapped[int] = mapped_column(Integer, nullable=False)
    revenue_monthly_renew_pv: Mapped[int] = mapped_column(Integer, nullable=False)
    revenue_color_rule: Mapped[str] = mapped_column(String(32), nullable=False)
    revenue_color_names_json: Mapped[str] = mapped_column(Text, nullable=False)

    # ============== commission_config (21 列) ==============
    cc_enable_retail_profit: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cc_enable_team_bonus: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cc_team_bonus_tier_rates_json: Mapped[str] = mapped_column(Text, nullable=False)
    cc_team_bonus_window_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    cc_enable_own_basic: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cc_own_basic_rate: Mapped[float] = mapped_column(Float, nullable=False)
    cc_own_basic_line_pv_cap: Mapped[int] = mapped_column(Integer, nullable=False)
    cc_enable_savings: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cc_savings_usd_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    cc_savings_rate: Mapped[float] = mapped_column(Float, nullable=False)
    cc_savings_cap_usd: Mapped[float] = mapped_column(Float, nullable=False)
    cc_enable_pair_bonus: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cc_pair_bonus_ratios_json: Mapped[str] = mapped_column(Text, nullable=False)
    cc_pair_bonus_4th_usd_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    cc_pair_bonus_5th_usd_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    cc_enable_leader_dividend: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cc_leader_dividend_threshold_pv: Mapped[int] = mapped_column(Integer, nullable=False)
    cc_leader_dividend_share_usd: Mapped[float] = mapped_column(Float, nullable=False)
    cc_leader_dividend_tiers_json: Mapped[str] = mapped_column(Text, nullable=False)
    cc_enable_horizontal_leader: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cc_horizontal_leader_share_usd: Mapped[float] = mapped_column(Float, nullable=False)
    cc_horizontal_leader_tiers_json: Mapped[str] = mapped_column(Text, nullable=False)
    cc_enable_opportunity_points: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # ============== 派生 (3 列) ==============
    total_target: Mapped[int] = mapped_column(Integer, nullable=False)
    total_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    total_months: Mapped[int] = mapped_column(Integer, nullable=False)

    # ============== v1.0.14 1代4 4子锁定 (1 列, 可空) ==============
    # 业务: 每个父节点 (非叶) 在凑齐 4 子时刻, 4 个 bfs_id + m_first 锁定到 JSON
    #       1代4 计算 = 查表, 不动态 BFS (避免每次重算可能出错)
    # 格式: {"locks": {bfs_id: {"subs": [4 bfs_ids], "m_first": int}}, "version": 1}
    # nullable=True: 旧 134 个 scenario 没这字段, 首次 GET 时 lazy backfill
    one_gen_four_locks_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def to_dict(self) -> dict:
        """侧栏列表 / 详情页用的字段拍平 (含 JSON 反序列化)
        业务注意: JSON object key 总是 string, 但 TreeShape/Growth 业务字段要求 int key,
        这里在 to_dict 时把 layer_counts / *_tier_rates / *_tiers 的 key 统一转 int,
        保持跟 scenario/builder.py 输入一致 (Dict[int, int] 而不是 Dict[str, int])
        """
        import json
        # layer_counts: Dict[int, int] (TreeShape 要求 int key)
        layer_counts_raw = json.loads(self.tree_layer_counts_json)
        layer_counts = {int(k): v for k, v in layer_counts_raw.items()}
        # *_tier_rates / *_tiers: Dict[int, float] 或 Dict[int, int] (业务上 PV 值是 int)
        def _int_keys(d):
            return {int(k): v for k, v in d.items()}
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "tree_shape": {
                "fork_type": self.tree_fork_type,
                "max_level": self.tree_max_level,
                "layer_counts": layer_counts,
            },
            "growth": {
                "nodes_per_region_per_week": self.growth_nodes_per_region_per_week,
                "n_regions": self.growth_n_regions,
                "join_strategy": self.growth_join_strategy,
                "weeks_per_month": self.growth_weeks_per_month,
            },
            "revenue": {
                "initial_pv": self.revenue_initial_pv,
                "monthly_renew_pv": self.revenue_monthly_renew_pv,
                "color_rule": self.revenue_color_rule,
                "color_names": json.loads(self.revenue_color_names_json),
            },
            "commission_config": {
                "enable_retail_profit": self.cc_enable_retail_profit,
                "enable_team_bonus": self.cc_enable_team_bonus,
                "team_bonus_tier_rates": _int_keys(json.loads(self.cc_team_bonus_tier_rates_json)),
                "team_bonus_window_weeks": self.cc_team_bonus_window_weeks,
                "enable_own_basic": self.cc_enable_own_basic,
                "own_basic_rate": self.cc_own_basic_rate,
                "own_basic_line_pv_cap": self.cc_own_basic_line_pv_cap,
                "enable_savings": self.cc_enable_savings,
                "savings_usd_threshold": self.cc_savings_usd_threshold,
                "savings_rate": self.cc_savings_rate,
                "savings_cap_usd": self.cc_savings_cap_usd,
                "enable_pair_bonus": self.cc_enable_pair_bonus,
                "pair_bonus_ratios": _int_keys(json.loads(self.cc_pair_bonus_ratios_json)),
                "pair_bonus_4th_usd_threshold": self.cc_pair_bonus_4th_usd_threshold,
                "pair_bonus_5th_usd_threshold": self.cc_pair_bonus_5th_usd_threshold,
                "enable_leader_dividend": self.cc_enable_leader_dividend,
                "leader_dividend_threshold_pv": self.cc_leader_dividend_threshold_pv,
                "leader_dividend_share_usd": self.cc_leader_dividend_share_usd,
                "leader_dividend_tiers": _int_keys(json.loads(self.cc_leader_dividend_tiers_json)),
                "enable_horizontal_leader": self.cc_enable_horizontal_leader,
                "horizontal_leader_share_usd": self.cc_horizontal_leader_share_usd,
                "horizontal_leader_tiers": _int_keys(json.loads(self.cc_horizontal_leader_tiers_json)),
                "enable_opportunity_points": self.cc_enable_opportunity_points,
            },
            "total_target": self.total_target,
            "total_weeks": self.total_weeks,
            "total_months": self.total_months,
        }

    def __repr__(self):
        return f"<Scenario id={self.id} name={self.name!r} target={self.total_target}>"
