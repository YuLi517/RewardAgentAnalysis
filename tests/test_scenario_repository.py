"""PR3 Task 3: ScenarioRepository CRUD 测试"""
import os
import tempfile
import json
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tools.migrate_add_scenarios_table import upgrade
from scenario.repository import ScenarioRepository
from scenario.model import TreeShape, Growth, Revenue, CommissionConfig
from scenario.builder import build_scenario


def _make_engine_with_table():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    upgrade(engine)
    return engine, path


def _make_scenario(name="test_save_load"):
    ts = TreeShape("binary", 10, {0: 1, 1: 4, 2: 8})
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(1500, 100, "4_color_cycle", ("红", "紫", "青绿", "蓝"))
    cc = CommissionConfig(
        False, True, {200: 0.15}, 4, True, Decimal("0.15"), 13334,
        False, 250.0, 0.15, 500.0, False, {}, 500.0, 1000.0,
        False, 13334, 500.0, {}, False, 250.0, {}, False,
    )
    return build_scenario(ts, g, r, cc, name=name)


def test_save_load_roundtrip():
    """save → load roundtrip, 4 组参数 + 派生全对"""
    engine, path = _make_engine_with_table()
    try:
        Session = sessionmaker(bind=engine)
        with Session() as session:
            repo = ScenarioRepository(session)
            s = _make_scenario()
            scenario_id = repo.save(s)
            assert scenario_id > 0
        # Load (用新 session 确认 commit 生效)
        with Session() as session:
            repo = ScenarioRepository(session)
            loaded = repo.load(scenario_id)
            assert loaded is not None
            assert loaded.name == "test_save_load"
            assert loaded.tree_shape.fork_type == "binary"
            assert loaded.tree_shape.max_level == 10
            assert loaded.tree_shape.layer_counts == {0: 1, 1: 4, 2: 8}
            assert loaded.growth.n_regions == 4
            assert loaded.growth.weeks_per_month == 4
            assert loaded.revenue.initial_pv == 1500
            assert loaded.revenue.color_names == ("红", "紫", "青绿", "蓝")
            assert loaded.commission_config.enable_team_bonus is True
            assert loaded.commission_config.own_basic_rate == Decimal("0.15")
            assert loaded.commission_config.team_bonus_tier_rates[200] == 0.15
            # 派生字段也存了 (避免重算)
            assert loaded.total_target == 1 + 4 + 8
    finally:
        engine.dispose()
        try:
            os.unlink(path)
        except (PermissionError, OSError):
            pass


def test_list_scenarios():
    """list_all 返所有 scenarios, 按 id 排序"""
    engine, path = _make_engine_with_table()
    try:
        Session = sessionmaker(bind=engine)
        # save 2 个不同 name 的 scenario
        with Session() as session:
            repo = ScenarioRepository(session)
            s1 = _make_scenario(name="list_test_1")
            s2 = _make_scenario(name="list_test_2")
            id1 = repo.save(s1)
            id2 = repo.save(s2)
        with Session() as session:
            repo = ScenarioRepository(session)
            items = repo.list_all()
            assert len(items) >= 2
            names = [it.name for it in items]
            assert "list_test_1" in names
            assert "list_test_2" in names
    finally:
        engine.dispose()
        try:
            os.unlink(path)
        except (PermissionError, OSError):
            pass


def test_delete_scenario():
    """delete 后 load 返 None"""
    engine, path = _make_engine_with_table()
    try:
        Session = sessionmaker(bind=engine)
        with Session() as session:
            repo = ScenarioRepository(session)
            s = _make_scenario()
            sid = repo.save(s)
        with Session() as session:
            repo = ScenarioRepository(session)
            assert repo.load(sid) is not None
            repo.delete(sid)
        with Session() as session:
            repo = ScenarioRepository(session)
            assert repo.load(sid) is None
    finally:
        engine.dispose()
        try:
            os.unlink(path)
        except (PermissionError, OSError):
            pass


def test_save_overwrites_existing_name():
    """同 name 多次 save: 都成功, id 不同 (新建行)"""
    engine, path = _make_engine_with_table()
    try:
        Session = sessionmaker(bind=engine)
        with Session() as session:
            repo = ScenarioRepository(session)
            s1 = _make_scenario(name="dup_name")
            id1 = repo.save(s1)
        with Session() as session:
            repo = ScenarioRepository(session)
            s2 = _make_scenario(name="dup_name")
            id2 = repo.save(s2)
        assert id1 != id2
        with Session() as session:
            repo = ScenarioRepository(session)
            items = repo.list_all()
            assert sum(1 for it in items if it.name == "dup_name") == 2
    finally:
        engine.dispose()
        try:
            os.unlink(path)
        except (PermissionError, OSError):
            pass
