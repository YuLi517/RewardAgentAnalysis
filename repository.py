"""
repository.py —— Session / Message 数据库操作封装
==================================================

设计目标：
    1. 业务层（main.py）只调 repository，不直接写 SQL
    2. 单一职责：每个方法一个明确动作（get / create / append / list / search / delete）
    3. 兼容 stage1 的 SessionManager 接口语义（get_or_create / append / get_history / clear / list_sessions）
       —— 这样 main.py 改造最小，只需把内存 dict 操作换成 repo 调用。

搜索策略（LIKE 即可，Stage 2 不上 FTS5）：
    - title 命中 OR 任一 message.content 命中
    - 用 LIKE '%kw%'（SQLite 默认 NOCASE 不开，区分大小写 —— 中文场景无所谓）
    - 10 万级数据走 LIKE 没问题；上百万再换 FTS5 或外部 ES

翻页策略：
    - offset / limit（简单，对侧栏"加载更多"够用）
    - 总数单独查一次（select count） —— 单会话表几千行以下没问题

★ 2026-07-12 移除:DocumentRepository / ChunkRepository (Stage 2C RAG 知识库)
    - 仅保留 SessionRepository 单一职责
"""

import time
import uuid
from typing import List, Optional, Tuple

from sqlalchemy import select, or_, func
from sqlalchemy.orm import Session as DbSession

from models import (
    Session as SessionModel, Message as MessageModel,
)


# ============== 工具 ==============

def generate_session_id() -> str:
    return str(uuid.uuid4())


def _now() -> float:
    return time.time()


def _truncate_title(content: str, n: int = 30) -> str:
    """生成会话标题：首条 user 消息前 n 字"""
    content = (content or "").strip().replace("\n", " ")
    if len(content) <= n:
        return content
    return content[:n] + "…"


# ============== SessionRepository ==============

class SessionRepository:
    """所有 Session / Message 相关 DB 操作。"""

    def __init__(self, db: DbSession):
        self.db = db

    # ----- commit / rollback -----
    def commit(self):
        self.db.commit()

    def rollback(self):
        self.db.rollback()

    # ----- Session 基础 -----

    def get(self, sid: str) -> Optional[SessionModel]:
        return self.db.get(SessionModel, sid)

    def get_or_create(
        self,
        sid: Optional[str],
        primary_provider: Optional[str] = None,
    ) -> Tuple[str, SessionModel]:
        """兼容 stage1 接口语义：传 sid 就用，不存在就创建。"""
        if sid:
            s = self.db.get(SessionModel, sid)
            if s:
                return sid, s
        new_sid = generate_session_id()
        now = _now()
        s = SessionModel(
            id=new_sid,
            title="新会话",
            created_at=now,
            updated_at=now,
            primary_provider=primary_provider,
        )
        self.db.add(s)
        self.db.flush()  # 立即可见
        return new_sid, s

    # ----- Session 列表 / 搜索 / 翻页 -----

    def list_sessions(
        self,
        page: int = 1,
        page_size: int = 20,
        q: Optional[str] = None,
    ) -> Tuple[List[SessionModel], int]:
        """返回 (本页列表, 命中总数)。按 updated_at DESC。"""
        page = max(1, page)
        page_size = max(1, min(page_size, 100))

        stmt = select(SessionModel)

        if q:
            like = f"%{q}%"
            # 命中条件：title 含 OR 任一 message.content 含
            hit_sids_subq = (
                select(MessageModel.session_id)
                .where(MessageModel.content.like(like))
                .distinct()
            )
            stmt = stmt.where(
                or_(
                    SessionModel.title.like(like),
                    SessionModel.id.in_(hit_sids_subq),
                )
            )

        # 总数
        total_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.db.execute(total_stmt).scalar() or 0

        # 分页
        paged_stmt = (
            stmt.order_by(SessionModel.updated_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        items = list(self.db.execute(paged_stmt).scalars())
        return items, total

    def update_title(self, sid: str, title: str) -> bool:
        s = self.db.get(SessionModel, sid)
        if not s:
            return False
        title = (title or "").strip()[:255] or "新会话"
        s.title = title
        s.updated_at = _now()
        return True

    def touch(self, sid: str, **kwargs):
        """更新 updated_at 和任意字段（用于 fallback 时记录 primary_provider 等）"""
        s = self.db.get(SessionModel, sid)
        if not s:
            return
        s.updated_at = _now()
        for k, v in kwargs.items():
            if hasattr(s, k):
                setattr(s, k, v)

    def delete(self, sid: str) -> bool:
        s = self.db.get(SessionModel, sid)
        if not s:
            return False
        self.db.delete(s)  # CASCADE 自动删 messages
        return True

    # ----- Message -----

    def append_message(
        self,
        sid: str,
        role: str,
        content: str,
        reasoning: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        is_fallback: bool = False,
        latency_ms: int = 0,
    ) -> MessageModel:
        """追加一条消息（不 commit，由外层 commit）。"""
        m = MessageModel(
            session_id=sid,
            role=role,
            content=content,
            reasoning=reasoning,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            is_fallback=1 if is_fallback else 0,
            latency_ms=latency_ms,
            created_at=_now(),
        )
        self.db.add(m)
        # 同步更新 session 元数据
        s = self.db.get(SessionModel, sid)
        if s:
            s.updated_at = _now()
            if role == "user":
                # 首条 user 消息自动设标题
                if s.title == "新会话" or not s.title:
                    s.title = _truncate_title(content)
                s.request_count = (s.request_count or 0) + 1
            elif role == "assistant":
                s.total_tokens = (s.total_tokens or 0) + total_tokens
        return m

    def get_messages(self, sid: str) -> List[MessageModel]:
        stmt = (
            select(MessageModel)
            .where(MessageModel.session_id == sid)
            .order_by(MessageModel.created_at)
        )
        return list(self.db.execute(stmt).scalars())

    def get_history_openai(self, sid: str, max_messages: int = 10) -> list:
        """返回 OpenAI 格式（role+content），最近 N 条，用于 LLM 上下文拼接。"""
        msgs = self.get_messages(sid)
        recent = msgs[-max_messages:]
        return [{"role": m.role, "content": m.content} for m in recent]

    # ----- 统计 -----

    def count_sessions(self) -> int:
        return self.db.execute(select(func.count(SessionModel.id))).scalar() or 0

    def count_messages(self) -> int:
        return self.db.execute(select(func.count(MessageModel.id))).scalar() or 0


# ============================================================
# 业务侧 Repository (2026-07-14 v1) — 周 commission 结算
# ============================================================
# 三个独立 Repository:
#   MemberRepository       — members 表 CRUD + PV 余额更新
#   PVLedgerRepository     — pv_ledger 表 CRUD + 按 period 拉 pending
#   CommissionPeriodRepository — commission_periods 表 CRUD + 状态机

from models import (
    Member, PVLedger, CommissionPeriod,
)


class MemberRepository:
    """members 表操作"""

    def __init__(self, db: DbSession):
        self.db = db

    def get(self, member_id: int) -> Optional[Member]:
        return self.db.get(Member, member_id)

    def get_by_dist_id(self, dist_id: str) -> Optional[Member]:
        stmt = select(Member).where(Member.member_dist_id == dist_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_or_create(
        self,
        member_dist_id: str,
        member_name: Optional[str] = None,
        parent_dist_id: Optional[str] = None,
        slot_line_id: Optional[int] = None,
        max_lines: int = 2,
        created_period_id: Optional[str] = None,
    ) -> Member:
        """按 dist_id 找或创建 (幂等)

        - 存在: 不修改, 直接返回
        - 不存在: 创建, current_pv_balance=0, 挂载位置记入
        """
        m = self.get_by_dist_id(member_dist_id)
        if m:
            return m
        now = _now()
        m = Member(
            member_dist_id=member_dist_id,
            member_name=member_name,
            parent_dist_id=parent_dist_id,
            slot_line_id=slot_line_id,
            max_lines=max_lines,
            current_pv_balance=0,
            total_commission=0.0,
            created_period_id=created_period_id,
            last_period_id=created_period_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(m)
        self.db.flush()
        return m

    def add_pv(self, member_id: int, pv_amount: int) -> int:
        """给成员余额 +pv_amount, 返回新余额

        注意: 不在这里写 ledger! ledger 由 caller 单独写, 避免事务嵌套
        """
        m = self.get(member_id)
        if not m:
            raise ValueError(f"member_id={member_id} 不存在")
        m.current_pv_balance = (m.current_pv_balance or 0) + pv_amount
        m.updated_at = _now()
        return m.current_pv_balance

    def carry_out(self, member_id: int, new_balance: int) -> int:
        """结算完成后, 把成员余额设为新的 carry_out 值"""
        m = self.get(member_id)
        if not m:
            raise ValueError(f"member_id={member_id} 不存在")
        m.current_pv_balance = max(0, new_balance)  # 不允许负数
        m.updated_at = _now()
        return m.current_pv_balance

    def add_commission(self, member_id: int, commission: float) -> float:
        """累加 commission 到成员历史总和 (历史展示用)"""
        m = self.get(member_id)
        if not m:
            raise ValueError(f"member_id={member_id} 不存在")
        m.total_commission = (m.total_commission or 0.0) + commission
        m.updated_at = _now()
        return m.total_commission

    def add_savings(self, member_id: int, savings_usd: float) -> float:
        """★ 2026-08-06 PR #73: 累加储蓄奖金 (美元) — 跨期累计, 跟 total_commission 独立"""
        m = self.get(member_id)
        if not m:
            raise ValueError(f"member_id={member_id} 不存在")
        m.savings_balance = (m.savings_balance or 0.0) + savings_usd
        m.updated_at = _now()
        return m.savings_balance

    def set_last_period(self, member_id: int, period_id: str) -> None:
        """结算后写 last_period_id (追溯用)"""
        m = self.get(member_id)
        if m:
            m.last_period_id = period_id
            m.updated_at = _now()

    def list_by_parent(self, parent_dist_id: str) -> List[Member]:
        """列某父节点下所有成员 (按 slot_line_id 排序)"""
        stmt = (
            select(Member)
            .where(Member.parent_dist_id == parent_dist_id)
            .order_by(Member.slot_line_id)
        )
        return list(self.db.execute(stmt).scalars())

    def list_all(self, limit: int = 500) -> List[Member]:
        """列全部成员 (admin 页面用)"""
        stmt = select(Member).order_by(Member.created_at.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars())

    def count(self) -> int:
        return self.db.execute(select(func.count(Member.id))).scalar() or 0


class PVLedgerRepository:
    """pv_ledger 表操作"""

    def __init__(self, db: DbSession):
        self.db = db

    def get(self, ledger_id: int) -> Optional[PVLedger]:
        return self.db.get(PVLedger, ledger_id)

    def append(
        self,
        member_id: int,
        member_dist_id: str,
        period_id: str,
        pv_amount: int,
        note: Optional[str] = None,
    ) -> PVLedger:
        """新增一笔 pending ledger (挂入新 PV 时调)"""
        if pv_amount <= 0:
            raise ValueError(f"pv_amount 必须 > 0, 实际 {pv_amount}")
        entry = PVLedger(
            member_id=member_id,
            member_dist_id=member_dist_id,
            period_id=period_id,
            pv_amount=pv_amount,
            status="pending",
            contribution_pv=0,
            commission_amount=0.0,
            created_at=_now(),
            note=note,
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def list_pending(self, period_id: str) -> List[PVLedger]:
        """拉本期所有 pending ledger (结算时用)

        按 member_id 排序, 确定性顺序, 便于调试
        """
        stmt = (
            select(PVLedger)
            .where(PVLedger.period_id == period_id, PVLedger.status == "pending")
            .order_by(PVLedger.member_id, PVLedger.id)
        )
        return list(self.db.execute(stmt).scalars())

    def list_by_member(self, member_id: int) -> List[PVLedger]:
        """查某成员所有 ledger 流水 (按时间顺序)"""
        stmt = (
            select(PVLedger)
            .where(PVLedger.member_id == member_id)
            .order_by(PVLedger.created_at, PVLedger.id)
        )
        return list(self.db.execute(stmt).scalars())

    def list_by_period(self, period_id: str) -> List[PVLedger]:
        """查某期所有 ledger (任何状态)"""
        stmt = (
            select(PVLedger)
            .where(PVLedger.period_id == period_id)
            .order_by(PVLedger.member_id, PVLedger.id)
        )
        return list(self.db.execute(stmt).scalars())

    def mark_paired(
        self,
        ledger_id: int,
        paired_with_member_id: int,
        paired_with_dist_id: str,
        contribution_pv: int,
        commission_amount: float,
    ) -> None:
        """标记 ledger 为 paired (当期配对消耗)"""
        e = self.get(ledger_id)
        if not e:
            raise ValueError(f"ledger_id={ledger_id} 不存在")
        if e.status != "pending":
            raise ValueError(f"ledger_id={ledger_id} 状态不是 pending (={e.status}), 不可标记 paired")
        e.status = "paired"
        e.paired_with_member_id = paired_with_member_id
        e.paired_with_dist_id = paired_with_dist_id
        e.contribution_pv = contribution_pv
        e.commission_amount = commission_amount
        e.resolved_at = _now()

    def mark_carried(self, ledger_id: int, note: Optional[str] = None) -> None:
        """标记 ledger 为 carried (跨期带到下周)"""
        e = self.get(ledger_id)
        if not e:
            raise ValueError(f"ledger_id={ledger_id} 不存在")
        if e.status != "pending":
            raise ValueError(f"ledger_id={ledger_id} 状态不是 pending, 不可标记 carried")
        e.status = "carried"
        e.resolved_at = _now()
        if note:
            e.note = (e.note or "") + f" | {note}"

    def count_pending(self, period_id: str) -> int:
        return self.db.execute(
            select(func.count(PVLedger.id))
            .where(PVLedger.period_id == period_id, PVLedger.status == "pending")
        ).scalar() or 0


class CommissionPeriodRepository:
    """commission_periods 表操作"""

    def __init__(self, db: DbSession):
        self.db = db

    def get(self, period_id: str) -> Optional[CommissionPeriod]:
        return self.db.get(CommissionPeriod, period_id)

    def get_or_create(self, period_id: str, start_at: float, end_at: float) -> CommissionPeriod:
        """按 period_id 找或创建 (状态默认 open)"""
        p = self.get(period_id)
        if p:
            return p
        p = CommissionPeriod(
            id=period_id,
            period_type="weekly",
            start_at=start_at,
            end_at=end_at,
            status="open",
            created_at=_now(),
        )
        self.db.add(p)
        self.db.flush()
        return p

    def list_periods(self, limit: int = 50) -> List[CommissionPeriod]:
        """列所有结算期 (按 end_at DESC)"""
        stmt = select(CommissionPeriod).order_by(CommissionPeriod.end_at.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars())

    def list_open_periods(self) -> List[CommissionPeriod]:
        """列所有 open 期 (待结算)"""
        stmt = (
            select(CommissionPeriod)
            .where(CommissionPeriod.status == "open")
            .order_by(CommissionPeriod.end_at)
        )
        return list(self.db.execute(stmt).scalars())

    def mark_settled(
        self,
        period_id: str,
        total_commission: float,
        total_pv_consumed: int,
        total_pv_carried: int,
        member_count: int,
        settled_by: str = "system",
        supplement_until_ts: Optional[float] = None,
    ) -> None:
        """标记期为 settled (结算完成)

        ★ 2026-07-20 PR #55: supplement_until_ts 参数
          - 主 settle 时设: = end_at + 3 天 (Mon 23:59:59.999)
          - 业务规则: Sun-Fri 是主 settle, Sat-Mon 是补录窗口, Tue 起 closed
        """
        p = self.get(period_id)
        if not p:
            raise ValueError(f"period_id={period_id} 不存在")
        p.status = "settled"
        p.total_commission = total_commission
        p.total_pv_consumed = total_pv_consumed
        p.total_pv_carried = total_pv_carried
        p.member_count = member_count
        p.settled_at = _now()
        p.settled_by = settled_by
        if supplement_until_ts is not None:
            p.supplement_until_ts = supplement_until_ts

    def add_supplement_commission(
        self,
        period_id: str,
        supplement_commission: float,
        supplement_count: int,
    ) -> None:
        """累加补录 commission + 计数 (★ 2026-07-20 PR #55)

        业务规则: 补录 commission 只算 own_commission, 不算对等 (ancestor 链已冻结)
        period.status 保持 'settled' (补录期间), supplement_until_ts 过期后由
        migration 脚本或下次 load 改成 'closed'
        """
        p = self.get(period_id)
        if not p:
            raise ValueError(f"period_id={period_id} 不存在")
        p.supplement_commission = (p.supplement_commission or 0.0) + supplement_commission
        p.supplement_count = (p.supplement_count or 0) + supplement_count

    def mark_closed_if_expired(self, period_id: str, now_ts: float) -> bool:
        """如果补录窗口过期, 标 closed (★ 2026-07-20 PR #55)

        Returns:
            True = 改了状态, False = 没改
        """
        p = self.get(period_id)
        if not p:
            return False
        if p.status != "settled":
            return False
        if p.supplement_until_ts is None:
            return False
        if p.supplement_until_ts < now_ts:
            p.status = "closed"
            return True
        return False
