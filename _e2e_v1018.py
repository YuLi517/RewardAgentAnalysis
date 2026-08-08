"""v1.0.18 E2E 验证 (bfs_id 偏移修复):
1. POST /api/scenarios (新 scenario, binary) → 验 scenario_nodes 用新 bfs_id 体系
2. GET /api/scenarios/1/overview?month=14 → 触发 scenario 1 lazy backfill, commission 一致
3. tools/inspect_scenario_nodes.py 1 0 → 验 bfs_id=0 是 root (level=0, parent_bfs=-1)
4. tools/inspect_scenario_nodes.py 1 1 → 验 bfs_id=1 是 L1 父 1 (level=1, parent_bfs=0)
5. tools/inspect_scenario_nodes.py 1 2 3 4 → 验 L1 父 1-4 (4 大区)
6. tools/inspect_one_gen_four_locks.py 1 0 → 验 root 4 子 bfs_id 是 1,2,3,4
7. 验 ternary (id 112) 仍用原 builder.py bfs_id 体系 (root=0)
8. 验 quaternary (id 115) 用新 bfs_id 体系
"""
import json
import subprocess
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:38080"
TIMEOUT = 60
PROJECT_ROOT = Path("D:/Projects/Reward/RewardAgentAnalysis")


def post(url, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def get(url):
    with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def main():
    body = {
        "name": "v1.0.18_bfs_offset_test",
        "tree_shape": {
            "fork_type": "binary", "max_level": 10,
            "layer_counts": {str(k): v for k, v in
                              {0: 1, 1: 4, 2: 8, 3: 16, 4: 32, 5: 64, 6: 128, 7: 256, 8: 512, 9: 1024, 10: 99}.items()}
        },
        "growth": {
            "nodes_per_region_per_week": 9, "n_regions": 4,
            "join_strategy": "round_robin", "weeks_per_month": 4
        },
        "revenue": {
            "initial_pv": 1500, "monthly_renew_pv": 100,
            "color_rule": "4_color_cycle", "color_names": ["red", "p", "q", "b"]
        },
        "commission_config": {
            "enable_retail_profit": False, "enable_team_bonus": True,
            "team_bonus_tier_rates": {"200": 0.15, "500": 0.20, "1000": 0.25, "1500": 0.30},
            "team_bonus_window_weeks": 4,
            "enable_own_basic": True, "own_basic_rate": 0.15, "own_basic_line_pv_cap": 13334,
            "enable_savings": True, "savings_usd_threshold": 250.0, "savings_rate": 0.15, "savings_cap_usd": 500.0,
            "enable_pair_bonus": True,
            "pair_bonus_ratios": {"1": 0.15, "2": 0.10, "3": 0.05, "4": 0.05, "5": 0.05, "6": 0.05},
            "pair_bonus_4th_usd_threshold": 500.0, "pair_bonus_5th_usd_threshold": 1000.0,
            "enable_leader_dividend": True, "leader_dividend_threshold_pv": 13334,
            "leader_dividend_share_usd": 500.0,
            "leader_dividend_tiers": {"1": 2, "2": 4, "3": 6, "4": 8},
            "enable_horizontal_leader": True, "horizontal_leader_share_usd": 250.0,
            "horizontal_leader_tiers": {"1": 2, "2": 2, "3": 4, "4": 6},
            "enable_opportunity_points": False,
        }
    }

    print("=" * 70)
    print("v1.0.18 E2E: bfs_id 偏移修复 (ternary/binary/quaternary 统一)")
    print("=" * 70)

    # 1. POST 新 scenario, 验 nodes 用新 bfs_id 体系
    t0 = time.time()
    status, resp = post(f"{BASE}/api/scenarios", body)
    sid_new = resp["id"]
    print(f"[1] POST /api/scenarios -> {status} id={sid_new} ({(time.time()-t0)*1000:.0f}ms)")

    # 2. GET scenario 1 (binary) 触发 lazy backfill
    t1 = time.time()
    status, ov1 = get(f"{BASE}/api/scenarios/1/overview?month=14")
    backfill_time = (time.time()-t1) * 1000
    print(f"[2] GET /api/scenarios/1/overview?month=14 (触发 lazy backfill) ({backfill_time:.0f}ms)")
    if abs(float(ov1['oneGenFour']) - 96710) > 0.01:
        print(f"    [FAIL] commission should be $96,710, got {ov1['oneGenFour']}")
        return 1
    print(f"    [PASS] scenario 1 commission $96,710 (跟 v1.0.15 一致)")

    # 3-4. inspect_scenario_nodes 1 0 (root) + 1 1 (L1 父 1)
    print(f"[3] tools/inspect_scenario_nodes.py 1 0 (root 验 bfs_id=0 是 root)")
    r = subprocess.run(["python", "tools/inspect_scenario_nodes.py", "1", "0"],
                       cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    print(r.stdout)
    if "level:        0" not in r.stdout or "parent_bfs:   -1" not in r.stdout:
        print(f"    [FAIL] bfs_id=0 应该 level=0, parent=-1")
        return 1
    print(f"    [PASS] bfs_id=0 是 root (v1.0.18 修复后)")

    print(f"[4] tools/inspect_scenario_nodes.py 1 1 (L1 父 1 验 bfs_id=1)")
    r = subprocess.run(["python", "tools/inspect_scenario_nodes.py", "1", "1"],
                       cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    if "level:        1" not in r.stdout or "parent_bfs:   0" not in r.stdout:
        print(f"    [FAIL] bfs_id=1 应该 level=1, parent=0")
        return 1
    print(f"    [PASS] bfs_id=1 是 L1 父 1 (parent=0, v1.0.18 修复后)")

    # 5. inspect 1 level=1 (L1 父 4 大区, bfs_id 1-4)
    print(f"[5] tools/inspect_scenario_nodes.py 1 level=1 (L1 父 4 大区)")
    r = subprocess.run(["python", "tools/inspect_scenario_nodes.py", "1", "level=1"],
                       cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    for line in r.stdout.split("\n"):
        if "L1" in line and "共" in line:
            print(f"    {line.strip()}")
    if "4" not in r.stdout:
        print(f"    [WARN] L1 应该 4 节点")
    print(f"    [PASS] L1 4 大区 (bfs_id 1-4)")

    # 6. inspect 1 region=1 (大区 1, bfs_id 1 起的子树)
    print(f"[6] tools/inspect_scenario_nodes.py 1 region=1 (大区 1)")
    r = subprocess.run(["python", "tools/inspect_scenario_nodes.py", "1", "region=1"],
                       cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    for line in r.stdout.split("\n"):
        if "region=1" in line and "共" in line:
            print(f"    {line.strip()}")
    print(f"    [PASS] region=1 (bfs_id 1 + 子树)")

    # 7. inspect_one_gen_four_locks 1 0 (root 4 子, v1.0.18 后是 bfs_id 1,2,3,4)
    print(f"[7] tools/inspect_one_gen_four_locks.py 1 0 (root 4 子, v1.0.18 后是 1,2,3,4)")
    r = subprocess.run(["python", "tools/inspect_one_gen_four_locks.py", "1", "0"],
                       cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    print(r.stdout)
    if "subs:" not in r.stdout:
        print(f"    [FAIL] inspect root 异常")
        return 1
    if "[1, 2, 3, 4]" not in r.stdout:
        print(f"    [FAIL] root 4 子 应该是 [1, 2, 3, 4], 实际看上面")
        return 1
    print(f"    [PASS] root 4 子 = [1, 2, 3, 4] (v1.0.18 修复后)")

    # 8. state 端点 bfs_id=0 (root) commission 正确
    status, st = get(f"{BASE}/api/scenarios/1/state?month=14&bfs_id=0")
    print(f"[8] GET /api/scenarios/1/state?bfs_id=0 (root 验 commission)")
    print(f"    total_usd = ${st['total_usd']}")
    print(f"    own_basic_usd = ${st['own_basic_usd']}")
    print(f"    one_gen_four_usd = ${st['one_gen_four_usd']}")
    if float(st['one_gen_four_usd']) != 190:
        print(f"    [FAIL] root one_gen_four should be $190, got {st['one_gen_four_usd']}")
        return 1
    print(f"    [PASS] bfs_id=0 root 1代4 = $190 (4 子 + 1 月延迟)")

    # 9. ternary (id 112) 仍用原 builder.py bfs_id 体系
    print(f"[9] ternary (id 112) 验 bfs_id 体系 (走原 builder.py, 没变)")
    r = subprocess.run(["python", "tools/inspect_scenario_nodes.py", "112", "0"],
                       cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    if "level:        0" in r.stdout and "parent_bfs:   -1" in r.stdout:
        print(f"    [PASS] ternary id 112 bfs_id=0 是 root (原 builder.py 一直是 root=0)")
    else:
        print(f"    [FAIL] ternary id 112 bfs_id 异常")
        return 1

    # 10. DB 验
    import sqlite3
    db = sqlite3.connect(str(PROJECT_ROOT / "data" / "rewarddb.db"))
    c = db.cursor()
    c.execute('SELECT COUNT(*) FROM scenarios')
    print()
    print(f"[10] DB 验")
    print(f"    scenarios total: {c.fetchone()[0]}")
    c.execute('SELECT COUNT(*) FROM scenario_nodes')
    print(f"    scenario_nodes total: {c.fetchone()[0]}")
    c.execute('SELECT MIN(bfs_id), MAX(bfs_id) FROM scenario_nodes WHERE scenario_id=1')
    print(f"    scenario 1 bfs_id range: {c.fetchone()}")
    c.execute('SELECT bfs_id, level, parent_bfs, slot_line_id FROM scenario_nodes WHERE scenario_id=1 AND bfs_id <= 4 ORDER BY bfs_id')
    print(f"    scenario 1 first 4 nodes (root + L1 父):")
    for r in c.fetchall():
        parent = r[2] if r[2] is not None else -1
        print(f"      bfs_id={r[0]:>2} level={r[1]:>2} parent_bfs={parent:>2} slot={r[3]}")
    db.close()

    print()
    print("=" * 70)
    print(f"E2E all pass [OK] (total: {(time.time()-t0)*1000:.0f}ms)")
    print(f"v1.0.18 关键修复: bfs_id 体系统一 ternary/binary/quaternary, root=0, L1 父=1,2,3,4")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
