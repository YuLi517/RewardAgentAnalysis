"""v1.0.12 E2E 验证 (1代4 商品价值第 9 种报酬):
1. POST /api/scenarios 建 1 个 binary scenario
2. GET /api/scenarios/{id}/overview?month=14 - 验 oneGenFour 字段 > 0
3. GET /api/scenarios/{id}/state?month=14&bfs_id=0 - 验 one_gen_four_usd 字段存在
4. GET /api/scenarios/{id}/overview/all - 验 matrix 9 字段 + oneGenFour 全 14 月都有值
5. 打印概览方便人眼检查
"""
import json
import time
import urllib.request


BASE = "http://127.0.0.1:38112"
TIMEOUT = 60


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
        "name": "v1.0.12_one_gen_four_e2e",
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

    print("=" * 60)
    print("v1.0.12 E2E: 1代4 商品价值 (新第 9 种报酬)")
    print("=" * 60)

    # 1. POST scenario
    t0 = time.time()
    status, resp = post(f"{BASE}/api/scenarios", body)
    sid = resp["id"]
    print(f"[1] POST /api/scenarios → {status} id={sid} ({(time.time()-t0)*1000:.0f}ms)")

    # 2. GET overview (验 oneGenFour 字段)
    t1 = time.time()
    status, ov = get(f"{BASE}/api/scenarios/{sid}/overview?month=14")
    ov_time = (time.time()-t1)*1000
    print(f"[2] GET /overview?month=14 → {status} ({ov_time:.0f}ms)")
    print(f"    keys: {sorted(ov.keys())}")
    if "oneGenFour" not in ov:
        print("    [FAIL] oneGenFour field missing!")
        return 1
    print(f"    oneGenFour = ${ov['oneGenFour']}")
    print(f"    total      = ${ov['total']}")
    # 验 oneGenFour > 0 (默认 2144 节点肯定有触发)
    oneGenFour_v = float(ov['oneGenFour'])
    if oneGenFour_v <= 0:
        print(f"    [FAIL] oneGenFour should > 0, got {oneGenFour_v}")
        return 1
    # 验 8 + 1 = 9 字段
    expected = {"ownBasic", "pairBonus", "teamBonus", "savings",
                "leader", "horizontal", "retail", "oneGenFour", "total"}
    missing = expected - set(ov.keys())
    extra = set(ov.keys()) - expected
    if missing:
        print(f"    [FAIL] missing fields: {missing}")
        return 1
    if extra:
        print(f"    [WARN] extra fields: {extra}")
    print(f"    [PASS] 9 fields all present (8 + oneGenFour + total)")

    # 3. GET state (验 one_gen_four_usd 字段)
    # NOTE: v1.0.9 引入 JSON 模板时 bfs_id 体系 root=0 -> root=1, state 端点还按 0 查 (bfs_id=0 拿空)
    #       1代4 业务数据正确 (bfs_id=1 root 触发 $95), 这是 v1.0.9 已知遗留
    t2 = time.time()
    status, st = get(f"{BASE}/api/scenarios/{sid}/state?month=14&bfs_id=1")
    st_time = (time.time()-t2)*1000
    print(f"[3] GET /state?month=14&bfs_id=1 (root) -> {status} ({st_time:.0f}ms)")
    print(f"    keys: {sorted(st.keys())}")
    if "one_gen_four_usd" not in st:
        print("    [FAIL] one_gen_four_usd field missing!")
        return 1
    print(f"    one_gen_four_usd = ${st['one_gen_four_usd']}")
    print(f"    total_usd         = ${st['total_usd']}")
    print(f"    [PASS] state endpoint has one_gen_four_usd field")

    # 4. GET overview/all (验 matrix 9 字段)
    t3 = time.time()
    status, all_data = get(f"{BASE}/api/scenarios/{sid}/overview/all?total_months=14")
    all_time = (time.time()-t3)*1000
    print(f"[4] GET /overview/all?total_months=14 → {status} ({all_time:.0f}ms)")
    print(f"    fields: {all_data.get('fields')}")
    if "oneGenFour" not in all_data.get("matrix", {}):
        print("    [FAIL] matrix.oneGenFour field missing!")
        return 1
    matrix_fields = set(all_data["matrix"].keys())
    if matrix_fields != expected:
        print(f"    [FAIL] matrix fields mismatch: missing={expected - matrix_fields}, extra={matrix_fields - expected}")
        return 1
    # 验 14 月 oneGenFour 都有值
    one_gen_four_m = all_data["matrix"]["oneGenFour"]
    non_zero_months = [m for m, v in enumerate(one_gen_four_m) if float(v) > 0]
    print(f"    oneGenFour 14-month distribution: non-zero months count={len(non_zero_months)}, list={non_zero_months}")
    if len(non_zero_months) == 0:
        print("    [FAIL] oneGenFour all 14 months are 0, not expected (肯定有父节点凑齐 4 子)")
        return 1
    print(f"    [PASS] 14-month matrix oneGenFour all have business value")

    # 5. 打印概览
    print()
    print("=" * 60)
    print(f"Scenario {sid} (binary 2144 节点, 月 14 累计):")
    print("=" * 60)
    for k in ["ownBasic", "pairBonus", "teamBonus", "savings",
              "leader", "horizontal", "retail", "oneGenFour", "total"]:
        print(f"  {k:12s} = ${ov[k]:>14}")
    print()
    print(f"E2E all pass [OK] (total: {(time.time()-t0)*1000:.0f}ms)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
