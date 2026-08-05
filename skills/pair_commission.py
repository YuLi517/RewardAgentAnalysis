# -*- coding: utf-8 -*-
"""
pair_commission.py —— 周 commission 结算核心算法
====================================================

用户拍板规则 (2026-07-14):
    Q1-A: 周期 = ISO 周 (2026-W28)
    Q2-C: 算法 = officev2 5 叉动力线 MAX vs SUM + carry 余额混搭
    Q3-A: carry 按成员本人 (成员跟 PV 走, 不跟槽位)
    Q4-B: 一上来全套 (本文件是 PR-A 算法核心)

D1-D5 默认:
    D1: 15% 写死 (跟 officev2 一致)
    D2: carry_in + 本周新增 = 当期可配对池
    D3: ISO 周
    D4: 不加 payout 状态, "应计" 概念
    D5: 7 代祖先链分润 [0.15, 0.10, 0.05, 0.05, 0.05, 0.05, 0.05]

算法结构:
    settle_period(period_id, db) 入口
        1. 拉本期所有 pending ledger
        2. 拉相关 members (含 carry_in balance)
        3. 构造 "settle tree" (跟 officev2 真实树结构同形, 槽位 PV = carry_in + 本期新增)
        4. 后序遍历: 算每节点 commission + 每槽位 carry_out
        5. pairing_bonus 7 代祖先链分润
        6. 写 ledger (paired/carried) + 更新 members (balance, total_commission, last_period_id)
        7. 标记 period = settled

复用 officev2:
    skill_5_lib.basic_commission(node)  — 节点本节点拿的 commission (15% × MIN(MAX, SUM_rest))
    skill_5_lib.pairing_bonus(root)     — 7 代祖先链分润
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from models import Member, PVLedger, CommissionPeriod
from repository import (
    MemberRepository, PVLedgerRepository, CommissionPeriodRepository,
)
from skills.period import (
    COMMISSION_RATE, PAIRING_BONUS_RATIOS, PAIRING_BONUS_MAX_DEPTH,
    get_period_range,
)

log = logging.getLogger(__name__)


# ============== 算法内部数据结构 ==============

@dataclass
class SlotNode:
    """settle tree 节点 (跟 officev2 jstree 同形, 但只存必要字段)

    - dist_id: 节点 officev2 号, avail 节点用空字符串
    - member_dist_id: 该槽位挂载的成员 dist_id (avail 节点 None)
    - pv: 该槽位当期可结算 PV = member.carry_in_balance + 本期 ledger.pv_amount
    - slot_line_id: 在父下的 1-based 位置
    - is_avail: 是否空位占位 (不参与配对)
    - children: 5 个子槽位 (按 slot_line_id 1..5 顺序, 不存在的补 None)
    """
    dist_id: str
    member_dist_id: Optional[str] = None
    pv: int = 0
    slot_line_id: int = 0
    is_avail: bool = False
    children: List[Optional["SlotNode"]] = field(default_factory=list)


@dataclass
class SettleResult:
    """单期结算结果"""
    period_id: str
    total_commission: float = 0.0
    total_pv_consumed: int = 0
    total_pv_carried: int = 0
    member_count: int = 0
    # 每个节点的 commission (用于 pairing_bonus 7 代分润)
    commission_by_dist: Dict[str, float] = field(default_factory=dict)
    # 每个成员的 carry_out (PV 余额, 写到 members.current_pv_balance)
    carry_out_by_dist: Dict[str, int] = field(default_factory=dict)
    # 7 代分润后, 每个 ancestor 拿到多少 commission
    ancestor_share_by_dist: Dict[str, float] = field(default_factory=dict)
    # 配对详情 (调试 / 审计用)
    pairs_log: List[dict] = field(default_factory=list)


# ============== 入口 ==============

def settle_period(
    period_id: str,
    db: DbSession,
    settled_by: str = "system",
    supplement_only: bool = False,
    dry_run: bool = False,
) -> SettleResult:
    """结算指定期

    Args:
        period_id: 业务周期 ID, e.g. "2026-07-12_W29"
        db: SQLAlchemy session
        settled_by: 操作者标识 (admin user / "system" / "supplement")
        supplement_only: True = 补录模式 (只算 own_commission, 不动对等 7 代分润)
                          False (默认) = 主 settle (own + pairing)
        dry_run: ★ PR #65: True = 算 preview, 不写 DB, 不 commit, 跳过 status check
                  用于前端账单视图 (open/settled/closed 都能算)
                  False (默认) = 正常写 DB

    业务规则 (PR #55, 2026-07-20):
      - 主 settle: Sun-Fri 期间或 Sat-Mon 期间都可以主动触发
        - 算 own_commission (基本) + pairing_bonus (7 代对等) → members.total_commission
        - 算 carry_out → members.current_pv_balance
        - period.status: open → settled
        - 写 period.supplement_until_ts = end_at + 3 天 (Mon 23:59)
      - 补录 (supplement_only): Sat-Mon 期间, 只能补 basic commission
        - 算 own_commission (基本, 跟主 settle 一样)
        - 跳过 pairing_bonus (对等链已冻结, 主 settle 时已发)
        - period.status 必须 = settled
        - now_ts < supplement_until_ts (Mon 23:59 之前)
        - 写 period.supplement_commission + supplement_count
        - 实际业务数据: 补录的 ledger 通常是 Sun-Fri 之后才加的 (主 settle 时还没存在)

    Returns:
        SettleResult 含本期总 commission / 总消耗 PV / 总 carry PV / 每个成员 carry_out
    Raises:
        ValueError: period_id 不存在 / 状态不对 / 补录时间过期 / 没有 pending ledger
    """
    import time as _time
    from skills.period import can_supplement

    period_repo = CommissionPeriodRepository(db)
    period = period_repo.get(period_id)
    if not period:
        raise ValueError(f"period_id={period_id!r} 不存在, 请先用 get_or_create 初始化")

    if not dry_run:
        # 正常模式: 状态校验
        if supplement_only:
            # 补录模式: period 必须 settled + 补录窗口内
            if period.status not in ("settled",):
                raise ValueError(
                    f"补录失败: period_id={period_id!r} 状态={period.status!r}, "
                    f"必须先主 settle (status=settled) 才能补录"
                )
            if period.supplement_until_ts is None:
                raise ValueError(
                    f"补录失败: period_id={period_id!r} 没有 supplement_until_ts "
                    f"(可能迁移时没设, 跑 tools/migrate_pr55_period_id.py 修)"
                )
            now_ts = _time.time()
            if now_ts > period.supplement_until_ts:
                raise ValueError(
                    f"补录失败: period_id={period_id!r} 补录窗口已过期 "
                    f"(now={now_ts:.0f} > supplement_until_ts={period.supplement_until_ts:.0f}, "
                    f"Mon 23:59 之后不可补)"
                )
        else:
            # 主 settle: 不能重复
            if period.status in ("settled", "closed"):
                raise ValueError(
                    f"period_id={period_id!r} 已 {period.status}, 不可重复结算 "
                    f"(settled_at={period.settled_at})"
                )
    else:
        # dry_run: 跳过 status check, 任何 status 都能算 preview
        log.info(f"settle_period({period_id}, dry_run=True): 跳过 status check, 模拟算 commission")

    ledger_repo = PVLedgerRepository(db)
    if dry_run:
        # dry_run: 拿该期所有 ledger (status=pending/paired/carried 都算, 跟当时主 settle 算法一致)
        #  - 主 settle 后: 大部分 paired (配对消耗) + 一部分 carried (PV 余下)
        #  - 这样 settled 期也能反推 own_commission / ancestor_share
        all_entries = ledger_repo.list_by_period(period_id)
        pending = [e for e in all_entries if e.status in ("pending", "paired", "carried")]
    else:
        pending = ledger_repo.list_pending(period_id)

    if not pending:
        log.info(f"settle_period({period_id}, dry_run={dry_run}): 没有 ledger, 跳过")
        result = SettleResult(period_id=period_id)
        if dry_run:
            return result
        return result

    member_repo = MemberRepository(db)
    # 拉所有相关成员
    member_ids = {e.member_id for e in pending}
    members = {m.id: m for m in (member_repo.get(mid) for mid in member_ids) if m}
    # ★ 2026-07-17 PR #53: 也把 root member (parent_dist_id=空 + slot_line_id=0) 加到 members
    #   _build_settle_tree 找 root 用 — 没 root 就 fallback 虚拟 __VIRTUAL_ROOT__, 配对 commission 丢失
    from sqlalchemy import select as _sa_select
    _root_stmt = _sa_select(Member).where(
        Member.parent_dist_id.is_(None),
        Member.slot_line_id.is_(None) | (Member.slot_line_id == 0),
    ).limit(1)
    _root_m = db.execute(_root_stmt).scalar_one_or_none()
    if _root_m is not None and _root_m.id not in members:
        members[_root_m.id] = _root_m
        log.debug(f"settle_period: root member added to members (id={_root_m.id}, dist_id={_root_m.member_dist_id})")

    log.info(
        f"settle_period({period_id}, supplement_only={supplement_only}): "
        f"{len(pending)} pending ledger, {len(members)} members"
    )

    # 构造 settle tree
    settle_tree = _build_settle_tree(pending, members, dry_run=dry_run)

    # 算 commission + carry
    # ★ 2026-07-17 PR #53: member_count 保持 = pending ledger 涉及数 (不含 root)
    #   members 字典加了 root 用于 _build_settle_tree 找真实根, 但 member_count 还是按 ledger 数
    _pending_member_count = len({e.member_id for e in pending})
    result = SettleResult(period_id=period_id, member_count=_pending_member_count)
    if settle_tree:
        # 后序遍历: 算 commission + 每槽位 carry_out
        _settle_node(settle_tree, result)

    # ★ 2026-07-20 PR #55: 补录模式跳过 pairing_bonus (对等链已冻结)
    if not supplement_only:
        if settle_tree:
            _apply_pairing_bonus(settle_tree, result)
    else:
        log.info(
            f"settle_period({period_id}, supplement_only=True): "
            f"跳过 pairing_bonus, 只算 own_commission"
        )

    # ★ PR #65: dry_run 模式: 算完 result 直接 return, 不写 DB
    #  - 用于前端账单视图 (open/settled/closed 都能算, 不影响真实数据)
    if dry_run:
        log.info(
            f"settle_period({period_id}, dry_run=True) PREVIEW: "
            f"total_commission={result.total_commission:.2f} "
            f"total_pv_consumed={result.total_pv_consumed} "
            f"members={len(result.commission_by_dist)}"
        )
        return result

    # 写 DB
    _write_settle_result(
        period_id, result, pending, members, db, settled_by,
        supplement_only=supplement_only,
    )

    return result


# ============== Settle Tree 构造 ==============

def _build_settle_tree(
    pending: List[PVLedger],
    members: Dict[int, Member],
    dry_run: bool = False,
) -> Optional[SlotNode]:
    """从 pending ledger + members 构造 settle tree

    ★ PR #66 修复: 按 parent_dist_id 递归构造真正的 5 叉树形
      旧实现 (PR #53 遗留): `sorted_members[:5]` 把所有非 root member 当 root children
        → 树形扁平化, 父节点 1 区/2 区 算不出 A 子区 (A own + C own)
        → 用户截图 (2026-07-23) 反馈: 王常军 own=150 (错), 期望 300
      新实现: 递归按 parent_dist_id 构造真树, 子槽位 = 5 个直系子 (按 slot_line_id 1-5)
        缺的槽位补 None (avail 占位, _settle_node 跳过)
    """
    if not members:
        return None

    # ★ 2026-07-17 PR #53: 用真实 root (王常军) 当 settle tree 根
    #   找真实 root member (parent_dist_id=空 + slot_line_id=0)
    _root_member = None
    for _m in members.values():
        if (not _m.parent_dist_id) and ((_m.slot_line_id or 0) == 0):
            _root_member = _m
            break
    if _root_member is not None:
        # 真实 root: 用其 dist_id, pv = carry_in + 本期新增
        _root_ledger_pv = sum(e.pv_amount for e in pending if e.member_id == _root_member.id)
        _root_pv_total = (_root_member.current_pv_balance or 0) + _root_ledger_pv
        root = SlotNode(
            dist_id=_root_member.member_dist_id,
            member_dist_id=_root_member.member_dist_id,
            pv=_root_pv_total,
            slot_line_id=0,
            is_avail=False,
        )
    else:
        # 没 root (DB 异常, 不应该有) → fallback 虚拟根, __VIRTUAL_ROOT__ sentinel
        root = SlotNode(dist_id="__VIRTUAL_ROOT__", slot_line_id=0)

    # ★ PR #65 dry_run: 临时把 current_pv_balance 设 0
    #  (carry_in 是历史 settle 算过的, dry_run 是"模拟"现在 settle, 不应该重复算)
    #  适配 PR #66 _build_recursive: 递归前清, 递归后还原
    _carry_backup: Optional[Dict[int, int]] = None
    if dry_run:
        _carry_backup = {m.id: m.current_pv_balance for m in members.values()}
        for m in members.values():
            m.current_pv_balance = 0

    def _build_recursive(parent_dist_id: str) -> List[Optional[SlotNode]]:
        """递归构造 parent 的 5 个子槽位 (按 slot_line_id 1-5 排序, 缺补 None)"""
        # 找 parent_dist_id 的所有直接子 (排除 root, 避免 self-as-child)
        children = [
            m for m in members.values()
            if m.parent_dist_id == parent_dist_id
            and m is not _root_member
        ]
        # 按 slot_line_id 排序 (1..5), None 排最后
        children.sort(key=lambda m: (m.slot_line_id if m.slot_line_id is not None else 999))
        slots: List[SlotNode] = []
        for cm in children:
            ledger_pv = sum(e.pv_amount for e in pending if e.member_id == cm.id)
            pv_total = (cm.current_pv_balance or 0) + ledger_pv
            slot = SlotNode(
                dist_id=cm.member_dist_id,
                member_dist_id=cm.member_dist_id,
                pv=pv_total,
                slot_line_id=cm.slot_line_id or (len(slots) + 1),
                is_avail=False,
            )
            # 递归构造子节点的 5 个子槽位
            slot.children = _build_recursive(cm.member_dist_id)
            slots.append(slot)
        # 补齐到 5 个槽位 (缺的填 None, _settle_node 跳过)
        while len(slots) < 5:
            slots.append(None)
        return slots

    if _root_member is not None:
        root.children = _build_recursive(_root_member.member_dist_id)
    else:
        # 虚拟根 fallback: 没法按 parent_dist_id 递归, 退化为"非 root 全当 root children"
        sorted_members = sorted(
            [m for m in members.values() if m.parent_dist_id or m.slot_line_id],
            key=lambda m: m.id
        )
        for i, m in enumerate(sorted_members[:5]):
            ledger_pv = sum(e.pv_amount for e in pending if e.member_id == m.id)
            pv_total = (m.current_pv_balance or 0) + ledger_pv
            slot = SlotNode(
                dist_id=m.member_dist_id,
                member_dist_id=m.member_dist_id,
                pv=pv_total,
                slot_line_id=i + 1,
                is_avail=False,
            )
            root.children.append(slot)
        while len(root.children) < 5:
            root.children.append(None)

    # dry_run 还原 current_pv_balance (rollback 应该也会清, 但保险)
    if _carry_backup is not None:
        for m in members.values():
            m.current_pv_balance = _carry_backup.get(m.id, 0) or 0

    return root


# ============== 核心算法: 节点 commission + 槽位 carry ==============

def _settle_node(node: SlotNode, result: SettleResult) -> Tuple[float, int]:
    """递归算节点 commission + 子区 carry_out

    ★★★ PR #68 翻案 PR #66 own-P 配对: 2026-07-27 用户截图反馈
        - 节点 own PV **直接 carry, 不参与 commission 配对**
        - 5 子区 P/L 配对: P = max(5 子区 c_pv_total 递归累加), L = sum(其他 4 子区)
          - pair = MIN(P, L) × 15% = 节点 commission
        - own 剩 = own (100% carry 给节点自己, 不参与配对)
        - P 剩 = P - pair → 写给 P 子区根 carry
        - L 剩 = L × (1 - pair/L) 各 → 写给 L 子区根 carry
        - "子区总 PV" (return 第二值) = own + sum(子节点 c_pv_total) 递归累加
          父节点当 sub_pvs 用, 让父能看到子孙 PV (用户的"1区/2区" = 父节点 5 子区递归累加)

    PR #66 旧算法 (own-P 配对消耗):
        - own_pair = MIN(own, P) 让 own 参与 commission 配对
        - 业务验证: A (own=1500, 5 子区 C=1000, 4 空) own_pair=1000, commission=150
        - 错! 用户截图 (2026-07-27) 反馈: "A 本期应该拿不到佣金, 因为他的 2 区还没有挂任何新成员"
        - A 的 5 子区 (4 区 C=1000 + 1, 2, 3, 5 区空) P=1000, L=0, pair=0, commission=0 ✓

    Returns:
        (node_commission, node_pv_total)
        - node_commission: 本节点 5 子区 P/L 配对 commission (15% × pair)
        - node_pv_total: 本节点"子区总 PV" (own + 子孙 PV 递归累加), 给父节点配对用

    业务场景验证 (PR #68):
        tree: root → A(L1) + B(L2), A → C(L1), B → D(L1)
        PV: A=1500, B=1000, C=1500, D=1000
        root: own=0, 5 子区递归 = A 子区(3000) + B 子区(2000) + 3 空
              P=3000, L=2000, pair=MIN(3000, 2000)=2000, commission=300 ✓
              own 0 carry, P(A) 剩 1000 写给 A, L(B) 剩 0 写给 B
        A: own=1500, 5 子区递归 = C 子区(1500) + 4 空
             P=1500, L=0, pair=0, commission=0 ✓
             own 1500 carry 给 A, P(C) 剩 1500 写给 C
        C: own=1500, 5 子区=0 (叶子)
             没子区, return 0.0, 1500
             own 1500 carry 给 C (没子区, 直接 carry)
        B: own=1000, 5 子区递归 = D 子区(1000) + 4 空
             P=1000, L=0, pair=0, commission=0
             own 1000 carry, P(D) 剩 1000 写给 D
        D: own=1000, 5 子区=0 (叶子)
             return 0.0, 1000, own 1000 carry

    T5 测试兼容 (L2 own=100, 5 子区 L3=100 + L4=100):
        P=100, L=100, pair=100, commission=15 ✓
        (PR #66 老算法 own_pair=100, sub_pair=0, commission=15 数值碰巧一样;
         PR #68 新算法 own 不参与, 但 5 子区 P/L 配对 pair=100, commission=15 数值也 15)
    """
    # 1. 递归算子区
    #    child_results 元素: (slot_lid, child_or_None, c_commission, c_pv_total)
    child_results = []
    for child in node.children:
        if child is None:
            child_results.append((0, None, 0.0, 0))
            continue
        c_commission, c_pv_total = _settle_node(child, result)
        child_results.append((child.slot_line_id, child, c_commission, c_pv_total))

    # 2. 算 5 子区 c_pv_total 列表 (递归累加, 用户的"1区/2区"视角)
    sub_pvs = []
    for slot_lid, c, _c_comm, c_pv_total in child_results:
        if c is not None:
            sub_pvs.append((slot_lid, c_pv_total))

    # ★★★ PR #68 重构: own carry 只非叶子写, 叶子由父 p_remain 覆盖 (避免双计)
    #   叶子 own 等于父 p_remain (叶子的 own = 父 subarea 唯一成员的 PV),
    #     父写 p_remain 到叶子已经覆盖了 own carry, 不需要再写 own
    #   非叶子 own 是单独 ledger PV, 跟父 p_remain (subarea unconsumed) 累加
    #   业务 (用户 2026-07-27 反馈): "A 本期应该拿不到佣金, 因为 2 区没新成员"
    #     A 是非叶子 (有 C), own 1500 carry, 加上根 p_remain 1000 = 2500
    #     C 是叶子, own 1500, 父 A p_remain 1500 覆盖 = 1500
    own_pv = node.pv

    if not sub_pvs:
        # ★ 叶子节点: 没子区, commission = 0, pv_total = own (给父节点当 sub_pvs)
        #   own carry 不写 — 父节点会写 p_remain 到此叶子 (覆盖了 own)
        return 0.0, node.pv

    # ★ 非叶子: own carry 写 (ADD 模式, 父节点之后会写 p_remain 累加)
    if node.member_dist_id:
        existing = result.carry_out_by_dist.get(node.member_dist_id, 0)
        result.carry_out_by_dist[node.member_dist_id] = int(existing) + int(own_pv)

    # ★ officev2 5 叉 P vs L: 1 个最强 P (1 个子区) + 4 个其他 L (最多 4 个子区)
    #   多个相等 max_pv 时, 取 1 个当 P, 其余算 L
    sorted_by_pv_desc = sorted(sub_pvs, key=lambda x: -x[1])
    p_slot_lid, p_pv = sorted_by_pv_desc[0]  # P 子区 PV (= max)
    l_pvs = [p for _, p in sorted_by_pv_desc[1:5]]  # L 4 子区 PV
    sum_rest = sum(l_pvs)

    # 3. ★ PR #68: 5 子区 P/L 配对 (own 不参与)
    #   旧 (PR #66): own_pair = MIN(own, P) 参与配对
    #   新 (PR #68): own 不参与, commission = 5 子区 P/L 配对 pair × 15%
    sub_pair = min(p_pv, sum_rest)
    node_commission = sub_pair * COMMISSION_RATE

    # ★ 跳过虚拟根 sentinel (PR #53), 真实根直接进 commission_by_dist
    if node.dist_id and node.dist_id != "__VIRTUAL_ROOT__":
        result.commission_by_dist[node.dist_id] = node_commission

    # 4. carry 算法:
    #    own (100%) → 节点自己 carry (上面已写)
    #    P 剩 (p_pv - sub_pair) → P 子区根 carry (子节点, ADD 模式)
    #    L 剩 (各 L × (1 - sub_pair/L)) → L 子区根 carry (子节点, ADD 模式)
    p_remain = p_pv - sub_pair
    if sum_rest > 0 and sub_pair > 0:
        consumed_ratio = sub_pair / sum_rest
    else:
        consumed_ratio = 0

    # 5. 写每个子槽位的 carry (ADD 模式, 累加到子节点已有的 own carry 上)
    for slot_lid, c, _c_comm, c_pv_total in child_results:
        if c is None or c.member_dist_id is None:
            continue
        if slot_lid == p_slot_lid:
            # P 子区: 剩 = p_remain
            this_carry = p_remain
        else:
            # L 子区: 剩 = c_pv_total × (1 - consumed_ratio)
            this_carry = c_pv_total * (1 - consumed_ratio)
        existing_child = result.carry_out_by_dist.get(c.member_dist_id, 0)
        result.carry_out_by_dist[c.member_dist_id] = int(existing_child) + int(this_carry)

    # 7. 累计统计
    result.total_commission += node_commission
    result.total_pv_consumed += int(sub_pair)

    # 记录配对日志
    result.pairs_log.append({
        "node_dist_id": node.dist_id,
        "max_pv": p_pv,
        "sum_rest": sum_rest,
        "pair_pv": int(sub_pair),
        "commission": round(node_commission, 4),
        "carry_p": int(p_remain),
        "own_carry": int(own_pv),
    })

    # 8. ★ PR #66: 本节点"子区总 PV" = own + sum(子节点 c_pv_total) (递归累加)
    #    给父节点当 sub_pvs 用, 让父算 own 时能正确看到本子树的 PV
    #    旧 (PR #58): return max_pv, 只看 1 层 (直接子 max) — 父节点少算子孙 PV
    #    PR #66: 改为递归累加, 兼容 PR #68 (own 不参与配对, 但子区总 PV 仍递归)
    _sum_sub = own_pv
    for _slot_lid, _c, _c_comm, _c_pv in child_results:
        if _c is not None and _c_pv > 0:
            _sum_sub += _c_pv
    return node_commission, _sum_sub


# ============== Pairing Bonus 7 代分润 ==============

def _apply_pairing_bonus(
    root: SlotNode,
    result: SettleResult,
) -> None:
    """沿 7 代祖先链分润每个节点的 commission

    对每个非 root 节点 n:
        自身 commission = basic_commission(n) (已算)
        ancestor share = basic_commission(n) × [0.15, 0.10, 0.05, 0.05, 0.05, 0.05, 0.05]
                       分别给第 1/2/3/4/5/6/7 代 ancestor
    """
    # ★ 2026-07-17 PR #53: 虚拟根 sentinel 改 "__VIRTUAL_ROOT__" (旧是 "ROOT" 跟真实 distId 冲突)
    #   - 真实 root (王常军) 是顶级, ancestors=[], 它自己的 commission 不分给任何人 (自己拿)
    #   - 虚拟根 fallback (DB 异常) 用 "__VIRTUAL_ROOT__" sentinel, 不进链也不写 commission
    #   实际链: L3.ancestors = [L2, L1] (depth=0=L2 第1代, depth=1=L1 第2代)
    node_to_ancestors: Dict[str, List[str]] = {}

    def _collect(node: SlotNode, ancestors: List[str]) -> None:
        if node.dist_id and node.dist_id != "__VIRTUAL_ROOT__":
            node_to_ancestors[node.dist_id] = list(ancestors)
        for child in node.children:
            if child is not None:
                # 虚拟根不进链; 真实节点加到 ancestors
                if node.dist_id and node.dist_id != "__VIRTUAL_ROOT__":
                    _collect(child, ancestors + [node.dist_id])
                else:
                    _collect(child, ancestors)

    _collect(root, [])

    # 对每个节点 n, 把它自己的 commission 按比例分给 ancestors
    for node_dist, commission in result.commission_by_dist.items():
        if commission <= 0:
            continue
        ancestors = node_to_ancestors.get(node_dist, [])
        for depth, ancestor_dist in enumerate(ancestors[:PAIRING_BONUS_MAX_DEPTH]):
            ratio = PAIRING_BONUS_RATIOS[depth]
            share = commission * ratio
            result.ancestor_share_by_dist[ancestor_dist] = (
                result.ancestor_share_by_dist.get(ancestor_dist, 0.0) + share
            )


# ============== 写 DB ==============

def _write_settle_result(
    period_id: str,
    result: SettleResult,
    pending: List[PVLedger],
    members: Dict[int, Member],
    db: DbSession,
    settled_by: str,
    supplement_only: bool = False,
) -> None:
    """把结算结果写回 DB

    步骤:
      1. 标 ledger = paired / carried
      2. 更新 members.current_pv_balance = carry_out
      3. 更新 members.total_commission += share (主 settle: own + ancestor, 补录: own only)
      4. 更新 members.last_period_id
      5. 标 period = settled (主 settle) / 更新 supplement_commission (补录)

    Args:
        supplement_only: True = 补录模式
          - 跳过 ancestor_share (对等链已冻结)
          - 累加 period.supplement_commission + supplement_count
          - 标 ledger note 区分
    """
    ledger_repo = PVLedgerRepository(db)
    member_repo = MemberRepository(db)

    # 1. 写 ledger 状态
    for entry in pending:
        carry_out = result.carry_out_by_dist.get(entry.member_dist_id, 0)
        consumed = entry.pv_amount - carry_out
        if consumed >= entry.pv_amount:
            # 全部消耗
            ledger_repo.mark_paired(
                entry.id,
                paired_with_member_id=entry.member_id,  # self-pair 占位 (本期全消)
                paired_with_dist_id=entry.member_dist_id,
                contribution_pv=consumed,
                commission_amount=consumed * COMMISSION_RATE,
            )
        elif consumed <= 0:
            # 完全 carry
            ledger_repo.mark_carried(entry.id, note=f"carry_out={carry_out}")
        else:
            # 部分消耗, 部分 carry (本 PR-A 简化: 整笔 mark_carried, 余额写 carry)
            # ★ 真实工程做法: 应该 split 成 2 行 ledger (paired + carried)
            #   本阶段先简化为: carry 全量, 记 note
            ledger_repo.mark_carried(
                entry.id,
                note=f"consumed={consumed} carry_out={carry_out} (PR-A 简化: 整笔 carry)",
            )

    # 2. 更新 members.current_pv_balance (carry_out)
    for member in members.values():
        new_balance = result.carry_out_by_dist.get(member.member_dist_id, 0)
        member_repo.carry_out(member.id, new_balance)
        member_repo.set_last_period(member.id, period_id)

    # 3. 更新 members.total_commission
    #    主 settle: own + ancestor 都加 (对等分润)
    #    补录: 只加 own, ancestor 跳过 (对等链已冻结)
    for dist_id, share in result.commission_by_dist.items():
        m = member_repo.get_by_dist_id(dist_id)
        if m:
            member_repo.add_commission(m.id, share)
    if not supplement_only:
        for dist_id, share in result.ancestor_share_by_dist.items():
            m = member_repo.get_by_dist_id(dist_id)
            if m:
                member_repo.add_commission(m.id, share)

    # 4. 标 period 状态
    total_carried = sum(result.carry_out_by_dist.values())
    period_repo = CommissionPeriodRepository(db)
    if supplement_only:
        # 补录: 累加 supplement_commission + supplement_count, period 保持 settled
        period_repo.add_supplement_commission(
            period_id=period_id,
            supplement_commission=result.total_commission,  # 补录只算 own, total = own
            supplement_count=result.member_count,
        )
    else:
        # 主 settle: 标 settled + 写 supplement_until_ts (Mon 23:59:59.999)
        from skills.period import get_supplement_range
        _, sup_end = get_supplement_range(period_id)
        period_repo.mark_settled(
            period_id=period_id,
            total_commission=result.total_commission,
            total_pv_consumed=result.total_pv_consumed,
            total_pv_carried=total_carried,
            member_count=result.member_count,
            settled_by=settled_by,
            supplement_until_ts=sup_end,
        )

    db.commit()

    log.info(
        f"settle_period({period_id}, supplement_only={supplement_only}) DONE: "
        f"total_commission={result.total_commission:.2f} "
        f"total_pv_consumed={result.total_pv_consumed} "
        f"total_pv_carried={total_carried} "
        f"member_count={result.member_count}"
    )


# ============== 辅助: 触发 / 周期初始化 ==============

def get_or_create_period(period_id: str, db: DbSession) -> CommissionPeriod:
    """获取或创建结算期 (start_at/end_at 自动算)"""
    start, end = get_period_range(period_id)
    return CommissionPeriodRepository(db).get_or_create(period_id, start, end)


# ============== 自检 ==============

if __name__ == "__main__":
    print("pair_commission 自检需要 DB, 请通过 pytest 跑 tests/test_pair_commission.py")
    print(f"COMMISSION_RATE = {COMMISSION_RATE}")
    print(f"PAIRING_BONUS_RATIOS = {PAIRING_BONUS_RATIOS}")
