"""P1.6: 预热机制 — 后台 thread 启动时算 14 月, 1st call 0 延迟

业务 (P1.6 §4.2):
- server 启动时, 后台 daemon thread 遍历所有 scenarios
- 每个 scenario 算 0-14 月 overview, 填充父进程 LRU 缓存
- 失败不阻塞 startup (daemon + try/except 包裹)
- 1st call 直接 hit LRU, 0 延迟

实现细节:
- 后台 thread `p16-warmer` daemon=True, 失败 print 不 raise
- 用模块级 set 记录已预热 scenario id, 避免重复预热
- 用 lock 保护 set, 防止多进程并发写
- 调 scenario._cache.set 跟 compute_month_overview 一样, 但不重计算已缓存
- 接受 sessionmaker (非 session), 后台 thread 自己创建/关闭 session (防 race)
"""
from __future__ import annotations
import threading
from typing import Set

from scenario.model import Scenario
from scenario.overview import compute_month_overview
from scenario.repository import ScenarioRepository


# 预热状态: 哪些 scenario 已预热
_warmed: Set[int] = set()
_lock = threading.Lock()


def warm_scenario(scenario: Scenario, total_months: int = 14) -> None:
    """预热 1 个 scenario 的 0-total_months 月, 填充 LRU 缓存

    注:
    - 1 个 scenario 算 15 次 (m=0..14), 每次 1-2s, 总 ~15-30s
    - 已预热的 scenario 跳过 (避免重复)
    - 失败 raise 让 warm_all_scenarios 接住 (单 scenario 失败不影响其他)
    """
    if scenario.id is None:
        return
    if scenario.id in _warmed:
        return
    for m in range(0, total_months + 1):
        # 1 次算 + 缓存 (compute_month_overview 内部走 scenario._cache)
        compute_month_overview(scenario, month=m)
    with _lock:
        _warmed.add(scenario.id)


def warm_all_scenarios(session_factory, total_months: int = 14) -> None:
    """server 启动时预热所有 scenarios (后台 thread)

    Args:
        session_factory: SQLAlchemy sessionmaker (非 session!)
            后台 thread 自己创建/关闭 session, 避免父进程跟后台 thread 共享
            session 引发的 race condition (父进程 close 时 thread 还在用)
        total_months: 预热几个月 (默认 14, 跟 P1.5 一致)

    注: 后台 thread daemon=True, 失败不阻塞 startup
    """
    def _background():
        db = session_factory()  # 后台 thread 自己创建 session
        try:
            repo = ScenarioRepository(db)
            for sid in repo.list_ids():
                s = repo.load(sid)
                if s is None:
                    continue
                warm_scenario(s, total_months)
        except Exception as e:
            # 预热失败不影响 server 启动
            print(f"[P1.6 warmer] 预热失败 (非致命): {e}")
        finally:
            db.close()

    t = threading.Thread(target=_background, daemon=True, name="p16-warmer")
    t.start()
