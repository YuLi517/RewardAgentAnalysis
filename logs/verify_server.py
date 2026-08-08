"""验证 v1.0.0 server 端点"""
import requests

print("=== /docs ===")
r = requests.get("http://127.0.0.1:38080/docs", timeout=5)
print(f"  status: {r.status_code}")

print()
print("=== /api/scenarios (list) ===")
r = requests.get("http://127.0.0.1:38080/api/scenarios", timeout=10)
print(f"  status: {r.status_code}")
if r.status_code == 200:
    rows = r.text.strip().split("\n")
    print(f"  rows: {len(rows) - 1} (excl header)")
    print(f"  first 3: {rows[1:4]}")

print()
print("=== /api/scenarios/1/state?month=14&bfs_id=0 ===")
r = requests.get("http://127.0.0.1:38080/api/scenarios/1/state?month=14&bfs_id=0", timeout=60)
print(f"  status: {r.status_code}")
if r.status_code == 200:
    import json
    d = json.loads(r.text)
    print(f"  own_basic: ${d['own_basic_usd']}")
    print(f"  pair_bonus: ${d['pair_bonus_usd']}")
    print(f"  total: ${d['total_usd']}")

print()
print("=== /api/scenarios/1/overview?month=14 ===")
r = requests.get("http://127.0.0.1:38080/api/scenarios/1/overview?month=14", timeout=10)
print(f"  status: {r.status_code}")
if r.status_code == 200:
    d = json.loads(r.text)
    print(f"  fields: {list(d.keys())}")
    for k, v in d.items():
        print(f"  {k}: {v}")
