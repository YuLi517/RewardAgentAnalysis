"""Pytest 全局 fixtures (P1.6 Task 4 加)

业务:
- ScenarioRepository._process_cache 是类级别 LRUDict, 跨测试复用
- 每个测试可能用 fresh temp DB, 但 cache 残留旧 id → 测试失败
- autouse fixture clear_process_cache 每个测试前清空, 保证隔离
"""
import pytest

from scenario.repository import ScenarioRepository


@pytest.fixture(autouse=True)
def clear_process_cache():
    """每个测试前清空 ScenarioRepository 类级别 _process_cache

    业务:
    - 测试 create fresh temp DB, 期望 id 从 1 开始干净
    - 类级别 cache 跨测试, 前一测试 id=1 残留 → 后一测试 load(id=1) 拿旧数据
    - 业务代码不调, 仅测试隔离用
    """
    ScenarioRepository.clear_cache()
    yield
    # 测试后也清, 避免后续 (manual) 调试时残留
    ScenarioRepository.clear_cache()
