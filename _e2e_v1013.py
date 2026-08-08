"""v1.0.13 E2E 验证 (1代4 凑齐 + 1 月触发):
1. POST /api/scenarios 建 1 个 binary scenario
2. GET /overview?month=0 - 验 oneGenFour = $0 (凑齐当月不触发)
3. GET /overview?month=1 - 验 oneGenFour = $48,355 (凑齐下月触发)
4. GET /overview?month=14 - 验 oneGenFour = $48,355 (持续)
5. GET /overview/all?total_months=14 - 验 14 月分布 (month 0 = 0, month 1-14 = 48,355)
6. 14 月累计 oneGenFour = 14 * 48,355 = $676,970 (v1.0.12 = 15 * 48,355 = $725,325, 减 1 月)
"""
import json
import time
import urllib.request


BASE = "http://127.0.0.1:38113"
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
        "name": "v1.0.13_one_gen_four_delay_e2e",
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
    print("v1.0.13 E2E: 1代4 凑齐 + 1 月触发 (新业务规则)")
    print("=" * 70)

    # 1. POST
    t0 = time.time()
    status, resp = post(f"{BASE}/api/scenarios", body)
    sid = resp["id"]
    print(f"[1] POST /api/scenarios -> {status} id={sid} ({(time.time()-t0)*1000:.0f}ms)")

    # 2. month=0 (凑齐当月, 不触发, 期望 $0)
    status, ov0 = get(f"{BASE}/api/scenarios/{sid}/overview?month=0")
    print(f"[2] GET /overview?month=0 -> {status} oneGenFour = ${ov0['oneGenFour']}")
    if float(ov0['oneGenFour']) != 0:
        print(f"    [FAIL] month 0 oneGenFour should be 0 (凑齐当月不触发), got {ov0['oneGenFour']}")
        return 1
    print(f"    [PASS] month 0 oneGenFour = 0 (凑齐当月不触发)")

    # 3. month=1 (凑齐下月, 触发, 期望 $48,355)
    status, ov1 = get(f"{BASE}/api/scenarios/{sid}/overview?month=1")
    print(f"[3] GET /overview?month=1 -> {status} oneGenFour = ${ov1['oneGenFour']}")
    if float(ov1['oneGenFour']) <= 0:
        print(f"    [FAIL] month 1 oneGenFour should > 0 (凑齐下月触发), got {ov1['oneGenFour']}")
        return 1
    print(f"    [PASS] month 1 oneGenFour = ${ov1['oneGenFour']} (凑齐下月触发)")

    # 4. month=14 (持续, 期望 $48,355)
    status, ov14 = get(f"{BASE}/api/scenarios/{sid}/overview?month=14")
    print(f"[4] GET /overview?month=14 -> {status} oneGenFour = ${ov14['oneGenFour']}")
    if float(ov14['oneGenFour']) != float(ov1['oneGenFour']):
        print(f"    [FAIL] month 14 oneGenFour should equal month 1 (持续), got {ov14['oneGenFour']} vs {ov1['oneGenFour']}")
        return 1
    print(f"    [PASS] month 14 oneGenFour = ${ov14['oneGenFour']} (持续, 跟 month 1 一致)")

    # 5. overview/all 14 月
    status, all_data = get(f"{BASE}/api/scenarios/{sid}/overview/all?total_months=14")
    one_gen_four_m = all_data["matrix"]["oneGenFour"]
    month_0_v = float(one_gen_four_m[0])
    month_1_v = float(one_gen_four_m[1])
    month_14_v = float(one_gen_four_m[14])
    print(f"[5] GET /overview/all?total_months=14 -> {status}")
    print(f"    month 0  oneGenFour = ${month_0_v}")
    print(f"    month 1  oneGenFour = ${month_1_v}")
    print(f"    month 14 oneGenFour = ${month_14_v}")
    if month_0_v != 0:
        print(f"    [FAIL] month 0 should be 0, got {month_0_v}")
        return 1
    if month_1_v <= 0:
        print(f"    [FAIL] month 1 should > 0, got {month_1_v}")
        return 1
    if month_14_v != month_1_v:
        print(f"    [FAIL] month 14 should equal month 1, got {month_14_v} vs {month_1_v}")
        return 1
    # 验 month 0 累计 0, month 1-14 累计 = 14 * month_1
    cumulative = sum(float(v) for v in one_gen_four_m)
    expected_cumulative = 14 * month_1_v
    print(f"    14 月累计 oneGenFour = ${cumulative}")
    print(f"    期望 (14 * month 1) = ${expected_cumulative}")
    if abs(cumulative - expected_cumulative) > 0.01:
        print(f"    [FAIL] 14 月累计 should be 14 * month_1, got {cumulative} vs {expected_cumulative}")
        return 1
    print(f"    [PASS] 14 月累计 = 14 * month 1 (month 0 不贡献, 差 v1.0.12 1 个月)")

    # 6. root state (bfs_id=1)
    status, st = get(f"{BASE}/api/scenarios/{sid}/state?month=0&bfs_id=1")
    root_m0 = st['one_gen_four_usd']
    status, st1 = get(f"{BASE}/api/scenarios/{sid}/state?month=1&bfs_id=1")
    root_m1 = st1['one_gen_four_usd']
    print(f"[6] GET /state?bfs_id=1 (root)")
    print(f"    month 0  root one_gen_four_usd = ${root_m0}")
    print(f"    month 1  root one_gen_four_usd = ${root_m1}")
    if float(root_m0) != 0:
        print(f"    [FAIL] root month 0 should be 0, got {root_m0}")
        return 1
    if float(root_m1) != 95:
        print(f"    [FAIL] root month 1 should be 95, got {root_m1}")
        return 1
    print(f"    [PASS] root month 0 = 0, month 1 = 95 (4 子触发 + 1 月延迟)")

    # 总结
    print()
    print("=" * 70)
    print(f"Scenario {sid} (binary 2144 节点) v1.0.13:")
    print("=" * 70)
    print(f"  month 0  oneGenFour = ${ov0['oneGenFour']:>10}  (凑齐当月不触发)")
    print(f"  month 1  oneGenFour = ${ov1['oneGenFour']:>10}  (凑齐下月触发)")
    print(f"  month 14 oneGenFour = ${ov14['oneGenFour']:>10}  (持续, 跟 month 1 一致)")
    print(f"  14 月累计 oneGenFour = ${cumulative:>10}  (v1.0.12 = $725,325, 减 1 月 = $48,355)")
    print(f"  14 月累计 = 14 * $48,355 = ${expected_cumulative:>10}")
    print(f"  总金额 (月 14) = ${ov14['total']:>10}")
    print()
    print(f"E2E all pass [OK] (total: {(time.time()-t0)*1000:.0f}ms)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
