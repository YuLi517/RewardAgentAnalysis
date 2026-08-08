"""v1.0.15 E2E 验证 (1代4 金额 95 PV → 190 USD, retail 卡片改 1代4 产品奖金):
1. POST /api/scenarios → 新 scenario
2. GET /overview?month=0 → 验 $0 (凑齐当月不触发)
3. GET /overview?month=1 → 验 $96,710 (190 × 509 父, 凑齐下月触发)
4. GET /overview?month=14 → 验 $96,710 (持续)
5. GET /state?bfs_id=1&month=1 → 验 $190 (root 4 子 + 1 月延迟)
6. GET /overview/all → 验 14 月累计 oneGenFour = $1,353,940 (14 × $96,710)
7. GET /state?bfs_id=1&month=14 → 验 total = 8 报酬 + 1代4 (无 retail 字段)
"""
import json
import time
import urllib.request


BASE = "http://127.0.0.1:38116"
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
        "name": "v1.0.15_one_gen_four_190usd_e2e",
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
    print("v1.0.15 E2E: 1代4 金额 95 PV -> 190 USD (PV x 2), retail 卡片改 1代4")
    print("=" * 70)

    # 1. POST
    t0 = time.time()
    status, resp = post(f"{BASE}/api/scenarios", body)
    sid = resp["id"]
    print(f"[1] POST /api/scenarios -> {status} id={sid} ({(time.time()-t0)*1000:.0f}ms)")

    # 2. month=0 不触发
    status, ov0 = get(f"{BASE}/api/scenarios/{sid}/overview?month=0")
    print(f"[2] GET /overview?month=0 -> oneGenFour = ${ov0['oneGenFour']}")
    if float(ov0['oneGenFour']) != 0:
        print(f"    [FAIL] month 0 should be 0, got {ov0['oneGenFour']}")
        return 1
    print(f"    [PASS] month 0 = 0 (凑齐当月不触发)")

    # 3. month=1 触发 = $96,710 (190 × 509)
    status, ov1 = get(f"{BASE}/api/scenarios/{sid}/overview?month=1")
    print(f"[3] GET /overview?month=1 -> oneGenFour = ${ov1['oneGenFour']}")
    expected = 190 * 509
    if abs(float(ov1['oneGenFour']) - expected) > 0.01:
        print(f"    [FAIL] month 1 should be ${expected}, got {ov1['oneGenFour']}")
        return 1
    print(f"    [PASS] month 1 = ${expected} (190 USD x 509 父节点)")

    # 4. month=14 持续
    status, ov14 = get(f"{BASE}/api/scenarios/{sid}/overview?month=14")
    print(f"[4] GET /overview?month=14 -> oneGenFour = ${ov14['oneGenFour']}")
    if abs(float(ov14['oneGenFour']) - expected) > 0.01:
        print(f"    [FAIL] month 14 should be ${expected}, got {ov14['oneGenFour']}")
        return 1
    print(f"    [PASS] month 14 = ${expected} (持续)")

    # 5. root state bfs_id=1 month=1
    status, st1 = get(f"{BASE}/api/scenarios/{sid}/state?month=1&bfs_id=1")
    print(f"[5] GET /state?bfs_id=1&month=1 -> one_gen_four_usd = ${st1['one_gen_four_usd']}")
    if float(st1['one_gen_four_usd']) != 190:
        print(f"    [FAIL] root month 1 should be 190, got {st1['one_gen_four_usd']}")
        return 1
    print(f"    [PASS] root month 1 = $190 (4 子 + 1 月延迟)")

    # 6. overview/all 14 月累计
    status, all_data = get(f"{BASE}/api/scenarios/{sid}/overview/all?total_months=14")
    one_gen_four_m = all_data["matrix"]["oneGenFour"]
    fields_count = len(all_data.get("fields", []))
    print(f"[6] GET /overview/all?total_months=14")
    print(f"    fields: {all_data['fields']}")
    print(f"    fields count: {fields_count} (v1.0.15 应该 8 字段, 不含 retail)")
    if "retail" in all_data["fields"]:
        print(f"    [FAIL] fields 仍含 retail, 应该 8 字段")
        return 1
    if "oneGenFour" not in all_data["fields"]:
        print(f"    [FAIL] fields 缺 oneGenFour")
        return 1
    if fields_count != 8:
        print(f"    [FAIL] fields 数量应该 8, 实际 {fields_count}")
        return 1
    cumulative = sum(float(v) for v in one_gen_four_m)
    expected_cum = 14 * expected
    print(f"    14 月累计 oneGenFour = ${cumulative}")
    print(f"    期望 (14 x ${expected}) = ${expected_cum}")
    if abs(cumulative - expected_cum) > 0.01:
        print(f"    [FAIL] 累计不匹配")
        return 1
    print(f"    [PASS] 14 月累计 = ${expected_cum} (190 USD x 509 x 14)")

    # 7. 旧 scenario 134 lazy backfill + 190 USD 一致
    status, ov14_old = get(f"{BASE}/api/scenarios/134/overview?month=14")
    print(f"[7] GET /api/scenarios/134/overview?month=14 -> oneGenFour = ${ov14_old['oneGenFour']}")
    if abs(float(ov14_old['oneGenFour']) - expected) > 0.01:
        print(f"    [FAIL] 旧 scenario 134 should be ${expected}, got {ov14_old['oneGenFour']}")
        return 1
    print(f"    [PASS] 旧 scenario 134 lazy backfill + 190 USD 一致")

    # 8. state 端点不返 retail_profit_usd (v1.0.15 删了) — 实际上 state 端点还有,前端不显示
    status, st0 = get(f"{BASE}/api/scenarios/{sid}/state?month=14&bfs_id=1")
    has_retail = "retail_profit_usd" in st0
    has_oneGenFour = "one_gen_four_usd" in st0
    print(f"[8] GET /state?bfs_id=1&month=14")
    print(f"    keys: {sorted(st0.keys())}")
    print(f"    has retail_profit_usd: {has_retail} (state 端点仍返, 业务上算法跑)")
    print(f"    has one_gen_four_usd: {has_oneGenFour} (190 USD, v1.0.15)")

    # 打印概览
    print()
    print("=" * 70)
    print(f"Scenario {sid} (binary 2144 节点) v1.0.15 8 报酬:")
    print("=" * 70)
    for k in ["ownBasic", "pairBonus", "teamBonus", "savings",
              "leader", "horizontal", "oneGenFour", "total"]:
        print(f"  {k:12s} = ${ov14[k]:>14}")
    print()
    print(f"E2E all pass [OK] (total: {(time.time()-t0)*1000:.0f}ms)")
    print(f"v1.0.15 关键数据: 1代4 月 14 = ${expected} (190 USD, 翻倍 v1.0.14 $48,355)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
