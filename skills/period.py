# -*- coding: utf-8 -*-
"""
period.py —— 业务周期工具 (commission 结算周期, 2026-07-20 PR #55 重构)
====================================================================

业务规则 (2026-07-20 用户拍板):
    - 周期粒度: Sun-Fri (6 天), 不是 ISO 周 (Mon-Sun)
    - 期号格式: "2026-07-12_W29" (开始日 + ISO week, 显式标注)
      - "2026-07-12" = Sun (周期开始日)
      - "W29" = 该周期所在的 ISO week
    - 标准周期: Sun 00:00 → Fri 23:59:59.999 (6 天)
    - 补录窗口: Sat 00:00 → Mon 23:59:59.999 (3 天, "下班前" = Mon 23:59)
      - 补录期间可以补**基本 commission** (own_commission)
      - 补录期间**不能补对等 commission** (pairing_bonus 链路冻结)
    - 关闭期: Tue 00:00 起, 上一周期彻底结束, 不能再补
    - commission_rate: 15% (写死, 跟 officev2 一致, 不参数化)

为什么 ID 包含开始日?
    - 显式标注业务周期起点, 跟 ISO week 范围 (Mon-Sun) 区分
    - 例: "2026-07-12_W29" 范围是 Sun 07-12 → Fri 07-17, 跟 ISO W29 (07-13 ~ 07-19) 不同
    - 数据库 migration 友好: 从旧 "2026-W29" → 新 "2026-07-12_W29" 是一次性字符串 replace

时间戳约定:
    - 所有时间用 unix timestamp (秒, REAL in SQLite), 不用 datetime 对象
    - 跟 models.py 一致 (Stage 2 已确定)
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, date
from typing import Tuple

# ============== 业务常量 ==============

# 跟 officev2 一致, 写死, 不参数化
COMMISSION_RATE: float = 0.15
PAIRING_BONUS_RATIOS: list = [0.15, 0.10, 0.05, 0.05, 0.05, 0.05, 0.05]  # 7 代分润
PAIRING_BONUS_MAX_DEPTH: int = 7

# ★ PR #72 (2026-08-06): 基本佣金每条 commission line 每周 max 13334 PV
#   业务: "每条佣金线每周最大值是13334PV, 超过按 13334 算, 约合 2000 美金"
#   - 13334 * 0.15 = ¥2000.10 ≈ $2000/周 max ownBasic
#   - 5 子区 P/L 配对时, 每个子区 PV 用 min(原 PV, 13334) 算 commission
#   - carry 仍用原 PV (cap 只影响 commission 算)
BASIC_COMMISSION_LINE_PV_CAP: int = 13334

# 补录窗口长度 (周六到下周一, 3 天)
SUPPLEMENT_WINDOW_DAYS: int = 3

# ★ 2026-08-06 PR #73: 储蓄奖金 (Savings Bonus) 业务规则
#   用户原话: "当周的基本佣金收入达到或超过 250 美元时候, 如果您的基本佣金为 1000 美元.
#             您将在储蓄奖金中额外存入 150 美元. 最高 500 美金."
#   业务要点 (用户 2026-08-06 拍板):
#     - 触发门槛: ownBasic (基本佣金) >= 250 USD
#     - 存入比例: ownBasic × 15% (跟 commission rate 同一个 15%, 业务上 commission 数字直接当美元理解)
#     - 存入上限: $500 / 周 (per 周 per 节点)
#     - 累计: 跨期累计到 members.savings_balance 字段 (跟 current_pv_balance 独立, 不混)
#     - 业务示例 (用户拍板):
#         ownBasic = $1000  → savings = $150 (1000×15%, 用户原话)
#         ownBasic = $200   → savings = 0 (< $250 门槛, 不触发)
#         ownBasic = $300   → savings = $45 (300×15%)
#         ownBasic = $2000  → savings = $300 (2000×15%)
#         ownBasic = $3334  → savings = $500.10 (3334×15% = 500.10, 触发 cap → $500)
#         ownBasic = $5000+ → savings = $500 (cap)
#     - 跟 ownBasic 联动: 只算 ownBasic (基本佣金), 不含 pairBonus/teamBonus
#     - 节点自己拿, 不分给 7 代祖先
#     - preview 跟 settle 一致: 实时算 + 主 settle 算
SAVINGS_BONUS_USD_THRESHOLD: float = 250.0  # 触发门槛
SAVINGS_BONUS_USD_RATE: float = 0.15        # 存入比例 (跟 COMMISSION_RATE 同源)
SAVINGS_BONUS_USD_CAP: float = 500.0        # 每周上限 (per 节点)


# ============== 周期 ID 解析 ==============

# 旧 ISO 周格式 "2026-W29" (PR #54 之前)
_PERIOD_ID_RE_OLD = re.compile(r"^(\d{4})-W(\d{2})$")
# 新业务格式 "2026-07-12_W29" (PR #55 起)
_PERIOD_ID_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})_W(\d{2})$")


def _parse_period_id(period_id: str) -> Tuple[date, int]:
    """解析 "YYYY-MM-DD_Www" → (start_date, biz_week)

    业务 W 编号自己数 (跟 ISO week 错位), 验证 start_date 跟 biz_week 一致

    Args:
        period_id: "2026-07-12_W29" 格式
    Returns:
        (start_date, biz_week) — start_date 是 Sun
    Raises:
        ValueError: 格式不对, 或 start_date 不是 Sun, 或 biz_week 算错
    """
    m = _PERIOD_ID_RE.match(period_id)
    if not m:
        raise ValueError(
            f"period_id 格式不合法: {period_id!r} "
            f"(期望 'YYYY-MM-DD_Www', e.g. '2026-07-12_W29')"
        )
    year, month, day, week = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    try:
        start = date(year, month, day)
    except ValueError as e:
        raise ValueError(f"period_id 开始日期不合法: {period_id!r} ({e})")
    if not (1 <= week <= 999):
        raise ValueError(f"period_id 周数越界: {period_id!r} (期望 1-999)")

    # 验证 start_date 确实是 Sun (weekday() == 6 in Python; Mon=0)
    if start.weekday() != 6:
        raise ValueError(
            f"period_id 开始日不是周日: {period_id!r} "
            f"({start.isoformat()} = {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][start.weekday()]})"
        )
    # 验证 biz_week 跟 start_date 一致
    expected_biz_week = _business_week_number(start)
    if expected_biz_week != week:
        raise ValueError(
            f"period_id biz_week 跟开始日不一致: {period_id!r} "
            f"(start_date biz_week = W{expected_biz_week:02d})"
        )
    return start, week


def make_period_id(start_date: date) -> str:
    """从 start_date (Sun) 生成 period_id

    业务周编号 = (start_date - 业务 W1 开始日) / 7 + 1
    业务 W1 开始日 = 包含 2026-01-01 (Thu) 的 Sun, 即 2025-12-28 (Sun)
    (注: 业务 W1 范围 2025-12-28 ~ 2026-01-02, 大部分在 2025 年但业务算 2026 年第 1 周)

    ★ 业务 W 编号跟 ISO week 编号不对齐:
       - 业务 W29 (Sun 2026-07-12) 范围 = 2026-07-12 ~ 2026-07-17
       - ISO W29 范围 = 2026-07-13 (Mon) ~ 2026-07-19 (Sun) — 完全不同

    Args:
        start_date: 周期开始日, 必须是周日
    Returns:
        "YYYY-MM-DD_Www" 格式字符串
    Raises:
        ValueError: start_date 不是周日
    """
    if start_date.weekday() != 6:
        raise ValueError(
            f"start_date 必须是周日: {start_date.isoformat()} "
            f"= {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][start_date.weekday()]}"
        )
    biz_week = _business_week_number(start_date)
    return f"{start_date.isoformat()}_W{biz_week:02d}"


# 业务 W1 开始日: 包含 2026-01-01 的 Sun = 2025-12-28
_BUSINESS_W1_START = date(2025, 12, 28)


def _business_week_number(start_date: date) -> int:
    """业务周编号 (1, 2, 3, ...)

    业务 W1 = 2025-12-28 (Sun) ~ 2026-01-02 (Fri)
    业务 W2 = 2026-01-04 (Sun) ~ 2026-01-09 (Fri)
    ...
    """
    delta_days = (start_date - _BUSINESS_W1_START).days
    if delta_days < 0:
        raise ValueError(f"start_date 早于业务 W1 开始: {start_date.isoformat()} < {_BUSINESS_W1_START.isoformat()}")
    if delta_days % 7 != 0:
        raise ValueError(f"start_date 跟业务 W1 开始日不 7 对齐: {start_date.isoformat()} (delta={delta_days} 天)")
    return delta_days // 7 + 1


# ============== 周期范围计算 ==============

def get_current_period_id(now: datetime | None = None) -> str:
    """返回当前时刻所在的业务周期 ID, e.g. "2026-07-12_W29"

    业务规则:
        - 周日 (00:00 - 23:59) → 该日作为新周期开始
        - 周一-周五 (00:00 - 23:59) → 属于 Sun-Fri 周期
        - 周六 (00:00 - 23:59) → 属于上一周期 (补录窗口期, 但周期 ID 仍指上一周期)
        - 这样保证: Sun-Fri 永远算同一个周期, Sat-Mon 算补录窗口

    Args:
        now: 传入指定时间, 默认 datetime.now()
    Returns:
        "YYYY-MM-DD_Www" 格式字符串
    """
    if now is None:
        now = datetime.now()
    today = now.date()
    weekday = today.weekday()  # Mon=0 ... Sun=6

    # 统一公式: 上一/本周日 = today - (weekday + 1) % 7
    #   Sun (6): (6+1)%7 = 0 → today        (今天就是 Sun)
    #   Mon (0): (0+1)%7 = 1 → today - 1    (昨天是 Sun)
    #   Tue (1): (1+1)%7 = 2 → today - 2
    #   ...
    #   Sat (5): (5+1)%7 = 6 → today - 6    (上周日, Sat-Mon 补录期仍算上一周期)
    start = today - timedelta(days=(weekday + 1) % 7)
    return make_period_id(start)


def get_period_range(period_id: str) -> Tuple[float, float]:
    """返回业务周期的 [start_ts, end_ts] (unix timestamp, 秒)

    业务范围: Sun 00:00:00 → Fri 23:59:59.999 (6 天)
    - start_ts = Sun 00:00:00 的 timestamp
    - end_ts   = Fri 23:59:59.999 的 timestamp (= Sat 00:00:00 - 1ms)

    Args:
        period_id: "YYYY-MM-DD_Www" 格式
    Returns:
        (start_ts, end_ts) unix timestamp tuple
    Raises:
        ValueError: period_id 格式不合法
    """
    start, _ = _parse_period_id(period_id)
    # start 是 Sun 00:00:00
    start_dt = datetime(start.year, start.month, start.day)
    # Fri 23:59:59.999 = Sun + 6 天 - 1ms
    end_dt = start_dt + timedelta(days=6) - timedelta(milliseconds=1)
    return start_dt.timestamp(), end_dt.timestamp()


def get_supplement_range(period_id: str) -> Tuple[float, float]:
    """返回补录窗口的 [start_ts, end_ts] (unix timestamp, 秒)

    业务范围: Sat 00:00:00 → Mon 23:59:59.999 (3 天, "下班前" = Mon 23:59)
    - start_ts = Sat 00:00:00 的 timestamp (= 周期 end_ts + 1ms)
    - end_ts   = Mon 23:59:59.999 的 timestamp

    Args:
        period_id: "YYYY-MM-DD_Www" 格式
    Returns:
        (start_ts, end_ts) unix timestamp tuple
    Raises:
        ValueError: period_id 格式不合法
    """
    start, _ = _parse_period_id(period_id)
    # Sat = Sun + 6 天 00:00 (业务周期 Fri 23:59:59.999 之后的下一天是 Sat)
    sat_dt = datetime(start.year, start.month, start.day) + timedelta(days=6)
    # Mon 23:59:59.999 = Sat 00:00 + 3 天 - 1ms (Sat→Sun→Mon)
    mon_end_dt = sat_dt + timedelta(days=SUPPLEMENT_WINDOW_DAYS) - timedelta(milliseconds=1)
    return sat_dt.timestamp(), mon_end_dt.timestamp()


def can_supplement(period_id: str, now: datetime | None = None) -> bool:
    """判断当前时间是否在补录窗口内

    Args:
        period_id: 业务周期 ID
        now: 传入指定时间, 默认 datetime.now()
    Returns:
        True = 在补录窗口内, False = 已过期
    """
    if now is None:
        now = datetime.now()
    sup_start, sup_end = get_supplement_range(period_id)
    now_ts = now.timestamp()
    return sup_start <= now_ts <= sup_end


def get_period_phase(period_id: str, now: datetime | None = None) -> str:
    """返回当前时间在业务周期的哪个阶段

    Returns:
        "open"       = Sun-Fri 期间 (标准周, 可挂入可结算)
        "supplement" = Sat-Mon 期间 (补录窗口, 只能补基本 commission)
        "closed"     = Tue 起 (周期彻底结束, 不能再补)
    """
    if now is None:
        now = datetime.now()
    period_start, period_end = get_period_range(period_id)
    sup_start, sup_end = get_supplement_range(period_id)
    now_ts = now.timestamp()

    if now_ts < period_start:
        # 还没到 (e.g. 查未来期)
        return "open"  # 暂归 open, 渲染按未来期处理
    if period_start <= now_ts <= period_end:
        return "open"
    if sup_start <= now_ts <= sup_end:
        return "supplement"
    return "closed"


def get_period_id_for_ts(ts: float) -> str:
    """unix timestamp → 业务周期 ID

    Args:
        ts: unix timestamp (秒)
    Returns:
        "YYYY-MM-DD_Www"
    """
    return get_current_period_id(datetime.fromtimestamp(ts))


def list_periods_in_range(
    start_ts: float, end_ts: float
) -> list[str]:
    """返回 [start_ts, end_ts] 区间内所有业务周期 ID (按时间顺序)

    用途: 批量回填历史期 (e.g. 一次性结算过去 4 个业务周期)
    """
    if end_ts < start_ts:
        return []
    seen = set()
    result = []
    cur = datetime.fromtimestamp(start_ts)
    end_dt = datetime.fromtimestamp(end_ts)
    while cur <= end_dt:
        pid = get_current_period_id(cur)
        if pid not in seen:
            seen.add(pid)
            result.append(pid)
        # 一次跳 1 天, 一定跨过 Sun 边界
        cur += timedelta(days=1)
    return result


# ============== 旧 ID 兼容 (migration 用) ==============

def migrate_old_period_id(old_id: str) -> str:
    """旧 "2026-W29" (ISO 周) → 新 "2026-07-12_W29" (业务周)

    业务 W 编号沿用 ISO W 编号 (数字保持一致, 但范围不同):
    - 旧 ISO W29 (Mon 2026-07-13 ~ Sun 2026-07-19) → 业务 W29 (Sun 2026-07-12 ~ Fri 2026-07-17)
    - 业务 W29 开始日 = ISO W29 周一的前一天 (Sun)

    数字虽然保持, 但业务 W<week> 范围 = ISO W<week> 范围 - 1 天 (少最后一天 Sun) + 头一天 Sun
    即业务 W29 ≈ ISO W29 的 Mon-Fri + 头一天 Sun (ISO W28 的 Sun)

    Args:
        old_id: 旧 "YYYY-Www" 格式 (ISO 周)
    Returns:
        新 "YYYY-MM-DD_Www" 格式 (业务周, 编号保持)
    Raises:
        ValueError: 不是旧格式
    """
    m = _PERIOD_ID_RE_OLD.match(old_id)
    if not m:
        raise ValueError(f"不是旧 ID 格式: {old_id!r} (期望 'YYYY-Www')")
    year, week = int(m.group(1)), int(m.group(2))
    # ISO W1 周一 = 1月4日所在周的周一
    jan_4 = date(year, 1, 4)
    jan_4_iso = jan_4.isocalendar()
    week_1_monday = jan_4 - timedelta(days=jan_4_iso[2] - 1)
    # ISO W<week> 周一 = week_1_monday + (week-1) 周
    target_monday = week_1_monday + timedelta(weeks=week - 1)
    # 业务周期 Sun = ISO 周一前一天
    target_sunday = target_monday - timedelta(days=1)
    # 业务 W 编号 = (target_sunday - biz W1 start) / 7 + 1
    # 例: 2026-07-12 (Sun), biz W1 start = 2025-12-28 (Sun)
    #     delta = (2026-07-12 - 2025-12-28).days = 196 = 28 * 7
    #     biz_week = 28 + 1 = 29
    return f"{target_sunday.isoformat()}_W{week:02d}"


# ============== 自检 ==============

if __name__ == "__main__":
    # 打印几个常见日期对应的业务周期
    test_dates = [
        datetime(2026, 7, 12),   # Sun → "2026-07-12_W29"
        datetime(2026, 7, 14),   # Tue → "2026-07-12_W29"
        datetime(2026, 7, 17),   # Fri → "2026-07-12_W29"
        datetime(2026, 7, 18),   # Sat → "2026-07-12_W29" (补录期)
        datetime(2026, 7, 20),   # Mon → "2026-07-12_W29" (补录期)
        datetime(2026, 7, 21),   # Tue → "2026-07-19_W30"
    ]
    for d in test_dates:
        pid = get_current_period_id(d)
        ps, pe = get_period_range(pid)
        ss, se = get_supplement_range(pid)
        phase = get_period_phase(pid, d)
        print(f"{d.date()} ({['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][d.weekday()]}) → {pid} "
              f"period={datetime.fromtimestamp(ps).date()}~{datetime.fromtimestamp(pe).date()} "
              f"supplement={datetime.fromtimestamp(ss).date()}~{datetime.fromtimestamp(se).date()} "
              f"phase={phase}")
    print()
    # 旧 ID 迁移
    for old in ["2026-W28", "2026-W29", "2026-W30", "2026-W52"]:
        print(f"migrate {old} → {migrate_old_period_id(old)}")
