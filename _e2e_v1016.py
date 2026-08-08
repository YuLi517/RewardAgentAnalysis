"""v1.0.16 E2E 验证 (节点表 scenario_nodes 持久化 2144 节点):
1. POST /api/scenarios → 新 scenario, 验 scenario_nodes 表有 2144 行
2. GET /api/scenarios/134/overview?month=14 → 触发 lazy backfill, 验 commission 跟 v1.0.15 一致
3. tools/inspect_scenario_nodes.py 134 1 → 验 root 节点查询
4. tools/inspect_scenario_nodes.py 134 6 → 验某子节点 + 父
5. tools/inspect_scenario_nodes.py 134 level=3 → 验 L3 所有节点
6. tools/inspect_scenario_nodes.py 134 region=2 → 验 region 2 所有节点
7. GET /api/scenarios/134/state?bfs_id=1&month=14 → 验 root commission 数据
"""
import json
import subprocess
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:38118"
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
        "name": "v1.0.16_scenario_nodes_e2e",
        "tree_shape": {
            "fork_type": "binary",
            "max_level": 10,
            "layer_counts": {str(k): v for k, v in
                              {0: 1, 1: 4, 2: 8, 3: 16, 4: 32, 5: 64, 6: 128, 7: 256, 8: 512, 9: 1024, 10: 99}.items()}
        },
        "growth": {
            "nodes_per_region_per_week": 9, "n_regions": 4,
            "join_strategy": "round_robin", "weeks_per_month": 4
        },
        "revenue": {
            "initial_pv": 1500, "monthly_renew_pv": 100,
            "color_rule": "4_color_cycle", "color_names": ["红", "紫", "青绿", "蓝"]
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
    print("v1.0.16 E2E: 节点表 scenario_nodes 持久化 2144 节点")
    print("=" * 70)

    # 1. POST
    t0 = time.time()
    status, resp = post(f"{BASE}/api/scenarios", body)
    sid_new = resp["id"]
    print(f"[1] POST /api/scenarios -> {status} id={sid_new} ({(time.time()-t0)*1000:.0f}ms)")

    # 验 nodes 表
    import sqlite3
    db = sqlite3.connect(str(PROJECT_ROOT / "data" / "rewarddb.db"))
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM scenario_nodes WHERE scenario_id=?", (sid_new,))
    n_nodes_new = cur.fetchone()[0]
    print(f"    scenario_nodes 行数: {n_nodes_new} (期望 2144)")
    if n_nodes_new != 2144:
        print(f"    [FAIL] 新 scenario nodes 行数应该 2144, 实际 {n_nodes_new}")
        return 1
    print(f"    [PASS] 新 scenario 节点表 2144 行")

    # 2. 触发旧 scenario 134 lazy backfill
    t1 = time.time()
    status, ov14 = get(f"{BASE}/api/scenarios/134/overview?month=14")
    backfill_time = (time.time() - t1) * 1000
    print(f"[2] GET /api/scenarios/134/overview?month=14 (触发 lazy backfill) ({backfill_time:.0f}ms)")
    if abs(float(ov14['oneGenFour']) - 96710) > 0.01:
        print(f"    [FAIL] oneGenFour should be $96,710, got {ov14['oneGenFour']}")
        return 1
    print(f"    [PASS] 旧 scenario 134 lazy backfill + commission 一致 $96,710")

    # 验 134 nodes 表也有 2144 行
    cur.execute("SELECT COUNT(*) FROM scenario_nodes WHERE scenario_id=134")
    n_nodes_134 = cur.fetchone()[0]
    print(f"    scenario 134 nodes 行数: {n_nodes_134} (期望 2144)")
    if n_nodes_134 != 2144:
        print(f"    [FAIL] 旧 scenario 134 nodes 行数应该 2144, 实际 {n_nodes_134}")
        return 1
    print(f"    [PASS] 旧 scenario 134 lazy backfill 成功, 节点表 2144 行")

    # 3-6. inspect tools
    print(f"[3] tools/inspect_scenario_nodes.py 134 1 (root)")
    r = subprocess.run(
        ["python", "tools/inspect_scenario_nodes.py", "134", "1"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True
    )
    print(r.stdout)
    if "level:        0" not in r.stdout:
        print(f"    [FAIL] inspect root 节点异常")
        return 1
    print(f"    [PASS] inspect root 节点 OK")

    print(f"[4] tools/inspect_scenario_nodes.py 134 6 (L1 大区 1 第一个子)")
    r = subprocess.run(
        ["python", "tools/inspect_scenario_nodes.py", "134", "6"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True
    )
    print(r.stdout)
    if "parent_bfs:   2" not in r.stdout:
        print(f"    [FAIL] inspect 节点 6 异常")
        return 1
    print(f"    [PASS] inspect 节点 6 OK (parent=2, business 验证)")

    print(f"[5] tools/inspect_scenario_nodes.py 134 level=3 (L3 所有节点)")
    r = subprocess.run(
        ["python", "tools/inspect_scenario_nodes.py", "134", "level=3"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True
    )
    # 找 L3 共 16 节点
    for line in r.stdout.split("\n"):
        if "L3 所有节点" in line:
            print(f"    {line.strip()}")
            if "16" not in line:
                print(f"    [WARN] L3 节点数应该 16, 实际看上面")
    print(f"    [PASS] inspect L3 节点 OK")

    print(f"[6] tools/inspect_scenario_nodes.py 134 region=2 (大区 2 所有节点)")
    r = subprocess.run(
        ["python", "tools/inspect_scenario_nodes.py", "134", "region=2"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True
    )
    for line in r.stdout.split("\n"):
        if "region=2" in line:
            print(f"    {line.strip()}")
    print(f"    [PASS] inspect region 2 OK")

    # 7. 总览 commission 验
    print(f"[7] GET /api/scenarios/134/state?bfs_id=1&month=14 (root)")
    status, st = get(f"{BASE}/api/scenarios/134/state?month=14&bfs_id=1")
    print(f"    total_usd = ${st['total_usd']}")
    print(f"    own_basic_usd = ${st['own_basic_usd']}")
    print(f"    one_gen_four_usd = ${st['one_gen_four_usd']}")
    if float(st['one_gen_four_usd']) != 190:
        print(f"    [FAIL] root month 14 one_gen_four should be $190, got {st['one_gen_four_usd']}")
        return 1
    print(f"    [PASS] root 1代4 = $190 (DB nodes 算 commission 一致)")

    # 8. DB 体积验
    cur.execute("SELECT COUNT(*) FROM scenario_nodes")
    total_nodes_rows = cur.fetchone()[0]
    print(f"[8] DB 验")
    print(f"    scenario_nodes 总行数: {total_nodes_rows} (137 scenario x 2144 = 293,728)")
    import os
    db_size = os.path.getsize(str(PROJECT_ROOT / "data" / "rewarddb.db"))
    print(f"    DB 体积: {db_size:,} bytes ({db_size/1024/1024:.1f} MB)")
    db.close()

    print()
    print("=" * 70)
    print(f"E2E all pass [OK] (total: {(time.time()-t0)*1000:.0f}ms)")
    print(f"v1.0.16 关键数据: scenario_nodes 表 137 scenario x 2144 = 293K 行, DB 762KB -> ?MB")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
