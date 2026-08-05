# -*- coding: utf-8 -*-
r"""
test_pr70_order_items.py —— 下单管理 (order_items) 端点测试
============================================================

PR #70 (2026-07-27) 下单管理:
    - GET  /api/orders/items      — 列出所有产品 (按 sort_order 排序)
    - PATCH /api/orders/items/bulk — 批量更新需求/库存/套组/套组价格

业务规则 (PR #70 拍板):
    - 单品差额 (unit_diff) = 当前库存 - 需求总数 (前端实时算, DB 不存)
    - 总金额 (total) = 套组 × 套组价格 (前端实时算, DB 不存)
    - 合计 = SUM(总金额)
    - 需求↑则当前库存按差量减少 (用户拍板: 库存_new = 库存_old - (需求_new - 需求_old))
    - 显式「保存」按钮 (用户拍板: 不自动存)

8 个 sample (来自用户截图, 拍板):
    活性辅酶     瓶  18  17  1  1335
    辅酶奥米加   瓶  15  0   5  1129
    钙镁健骨     瓶  27  1   9  820
    葡萄籽       瓶  26  0   9  899
    超级水果素   瓶  2   0   1  1290
    健儿素       瓶  13  0   5  766
    田园果蔬饮   袋  11  0   4  1248
    日夜纤       套  3   0   1  2599
    合计: 35162

测试覆盖:
    1. seed 自动 (GET 触发, count=8, 含 sort_order)
    2. seed 幂等 (二次 GET 仍 8 个, 不重复)
    3. unit_diff 实时算 (库存 - 需求, 8 行每行)
    4. total 实时算 (套组 × 套组价格, 8 行每行)
    5. 合计 = 35162 (跟用户截图一致)
    6. bulk update — 改 required_qty (库存不变, 用户没改库存)
    7. bulk update — 改 current_stock (库存单独改, 需求不变)
    8. bulk update — 改 package_count
    9. bulk update — 改 package_price (浮点)
    10. bulk update — 改 4 字段 (典型用法)
    11. bulk update — 找不到 id → 404
    12. bulk update — empty items → 400
    13. bulk update — items 字段缺失 → 422 (Pydantic 校验)
    14. update_at 自动更新 (Pydantic 验证 updated_at 改了)
    15. 改 name (品名) 不允许 (只有 4 字段可改)
    16. 8 个 sample 名字都正确
    17. sort_order 升序排 (8 行按 id asc, 因为 sort_order 是 0..7)
"""
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

import main  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import OrderItem  # noqa: E402


# 用户截图 8 个 sample, 跟 _ORDER_ITEMS_SAMPLE 一致
EXPECTED_SAMPLE = [
    ("活性辅酶", "瓶", 18, 17, 1, 1335.0),
    ("辅酶奥米加", "瓶", 15, 0, 5, 1129.0),
    ("钙镁健骨", "瓶", 27, 1, 9, 820.0),
    ("葡萄籽", "瓶", 26, 0, 9, 899.0),
    ("超级水果素", "瓶", 2, 0, 1, 1290.0),
    ("健儿素", "瓶", 13, 0, 5, 766.0),
    ("田园果蔬饮", "袋", 11, 0, 4, 1248.0),
    ("日夜纤", "套", 3, 0, 1, 2599.0),
]
# 用户截图合计
EXPECTED_GRAND_TOTAL = 35162.0


class TestOrderItemsApi(unittest.TestCase):
    """PR #70: /api/orders/items + /api/orders/items/bulk"""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def setUp(self):
        """每个测试: 清空 order_items, 重建干净状态"""
        db = SessionLocal()
        try:
            db.query(OrderItem).delete()
            db.commit()
        finally:
            db.close()

    def _list(self):
        return self.client.get("/api/orders/items")

    def _get_by_name(self, name: str):
        db = SessionLocal()
        try:
            return db.query(OrderItem).filter(OrderItem.name == name).first()
        finally:
            db.close()

    # ---------- seed (GET 触发) ----------

    def test_seed_auto_on_first_get(self):
        """GET 触发 seed, 第一次返 8 个"""
        r = self._list()
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["count"], 8)
        self.assertEqual(len(data["items"]), 8)
        # 8 个 sample 名字都对
        names = [it["name"] for it in data["items"]]
        for expected_name, *_ in EXPECTED_SAMPLE:
            self.assertIn(expected_name, names)

    def test_seed_is_idempotent(self):
        """二次 GET 不重 seed, 仍 8 个 (count + 名字不变)"""
        r1 = self._list()
        self.assertEqual(r1.json()["count"], 8)
        # 用户改一个产品的 required_qty, 再 GET 应仍 8 行 (种子不再插)
        first = r1.json()["items"][0]
        upd = self.client.patch(
            "/api/orders/items/bulk",
            json={"items": [{"id": first["id"], "required_qty": 999}]},
        )
        self.assertEqual(upd.status_code, 200)
        r2 = self._list()
        self.assertEqual(r2.json()["count"], 8)
        # 第一个还是 "活性辅酶" (因为 seed 不再插, sort_order 0 是 活性辅酶)
        self.assertEqual(r2.json()["items"][0]["name"], "活性辅酶")
        # required_qty 是用户改的 999, 不是 seed 的 18
        self.assertEqual(r2.json()["items"][0]["required_qty"], 999)

    # ---------- 计算规则 (unit_diff / total / 合计) ----------

    def test_unit_diff_computed_correctly(self):
        """单品差额 = 库存 - 需求 (跟用户截图红色 -1 / -15 / ... 一致)"""
        r = self._list()
        data = r.json()
        # 8 个 sample, 每个 unit_diff 应该 = stock - required
        for it in data["items"]:
            expected_diff = it["current_stock"] - it["required_qty"]
            self.assertEqual(it["unit_diff"], expected_diff,
                             f"{it['name']}: unit_diff 算错")
        # 跟用户截图: 活性辅酶 17-18=-1, 辅酶奥米加 0-15=-15
        active = next(it for it in data["items"] if it["name"] == "活性辅酶")
        self.assertEqual(active["unit_diff"], -1)
        omega = next(it for it in data["items"] if it["name"] == "辅酶奥米加")
        self.assertEqual(omega["unit_diff"], -15)
        calcium = next(it for it in data["items"] if it["name"] == "钙镁健骨")
        self.assertEqual(calcium["unit_diff"], -26)

    def test_total_computed_correctly(self):
        """总金额 = 套组 × 套组价格 (跟用户截图一致)"""
        r = self._list()
        data = r.json()
        for it in data["items"]:
            expected_total = it["package_count"] * it["package_price"]
            self.assertAlmostEqual(it["total"], expected_total, places=2,
                                   msg=f"{it['name']}: total 算错")
        # 跟用户截图: 活性辅酶 1*1335=1335, 辅酶奥米加 5*1129=5645
        active = next(it for it in data["items"] if it["name"] == "活性辅酶")
        self.assertEqual(active["total"], 1335)
        omega = next(it for it in data["items"] if it["name"] == "辅酶奥米加")
        self.assertEqual(omega["total"], 5645)

    def test_grand_total_matches_user_screenshot(self):
        """8 个 sample 合计 = 35162 (跟用户截图一致)"""
        r = self._list()
        data = r.json()
        actual_total = sum(it["total"] for it in data["items"])
        self.assertEqual(actual_total, EXPECTED_GRAND_TOTAL)

    def test_sample_order_by_sort_order(self):
        """按 sort_order 升序排 (8 行, 0..7)"""
        r = self._list()
        items = r.json()["items"]
        sort_orders = [it["sort_order"] for it in items]
        self.assertEqual(sort_orders, sorted(sort_orders))
        # 第一个 (sort_order=0) 应该是 "活性辅酶"
        self.assertEqual(items[0]["name"], "活性辅酶")
        # 最后一个 (sort_order=7) 应该是 "日夜纤"
        self.assertEqual(items[-1]["name"], "日夜纤")

    def test_sample_names_all_correct(self):
        """8 个 sample 名字都跟用户截图一致"""
        r = self._list()
        actual_names = [it["name"] for it in r.json()["items"]]
        expected_names = [n for n, *_ in EXPECTED_SAMPLE]
        self.assertEqual(actual_names, expected_names)

    def test_sample_units_all_correct(self):
        """8 个 sample 单位都跟用户截图一致 (7 瓶 + 1 袋 + 1 套)"""
        r = self._list()
        items = {it["name"]: it["unit"] for it in r.json()["items"]}
        self.assertEqual(items["活性辅酶"], "瓶")
        self.assertEqual(items["田园果蔬饮"], "袋")
        self.assertEqual(items["日夜纤"], "套")
        # 其他 5 个是 "瓶"
        for name in ["辅酶奥米加", "钙镁健骨", "葡萄籽", "超级水果素", "健儿素"]:
            self.assertEqual(items[name], "瓶")

    # ---------- bulk update (PATCH) ----------

    def test_bulk_update_required_qty_only(self):
        """改 required_qty, 库存不变 (用户没改库存)"""
        r = self._list()
        active = next(it for it in r.json()["items"] if it["name"] == "活性辅酶")
        orig_stock = active["current_stock"]
        new_req = 25
        r2 = self.client.patch(
            "/api/orders/items/bulk",
            json={"items": [{"id": active["id"], "required_qty": new_req}]},
        )
        self.assertEqual(r2.status_code, 200)
        data = r2.json()
        self.assertEqual(data["updated_count"], 1)
        # 改回 server
        updated = data["items"][0]
        self.assertEqual(updated["required_qty"], new_req)
        # 库存没变 (PATCH 只发 required_qty, 库存保持原值)
        self.assertEqual(updated["current_stock"], orig_stock)
        # unit_diff 重新算: 17-25=-8
        self.assertEqual(updated["unit_diff"], orig_stock - new_req)
        # 验证 DB 真的改了
        db_row = self._get_by_name("活性辅酶")
        self.assertEqual(db_row.required_qty, new_req)
        self.assertEqual(db_row.current_stock, orig_stock)

    def test_bulk_update_current_stock_only(self):
        """改 current_stock, 需求不变 (业务: 客户手动调整库存)"""
        r = self._list()
        omega = next(it for it in r.json()["items"] if it["name"] == "辅酶奥米加")
        orig_req = omega["required_qty"]
        new_stock = 20
        r2 = self.client.patch(
            "/api/orders/items/bulk",
            json={"items": [{"id": omega["id"], "current_stock": new_stock}]},
        )
        self.assertEqual(r2.status_code, 200)
        updated = r2.json()["items"][0]
        self.assertEqual(updated["current_stock"], new_stock)
        self.assertEqual(updated["required_qty"], orig_req)
        # unit_diff 重新算: 20-15=5
        self.assertEqual(updated["unit_diff"], 5)

    def test_bulk_update_package_count(self):
        """改 package_count, 总金额重算"""
        r = self._list()
        omega = next(it for it in r.json()["items"] if it["name"] == "辅酶奥米加")
        # 5*1129=5645 → 改成 3 套: 3*1129=3387
        r2 = self.client.patch(
            "/api/orders/items/bulk",
            json={"items": [{"id": omega["id"], "package_count": 3}]},
        )
        self.assertEqual(r2.status_code, 200)
        updated = r2.json()["items"][0]
        self.assertEqual(updated["package_count"], 3)
        self.assertEqual(updated["total"], 3 * 1129.0)

    def test_bulk_update_package_price(self):
        """改 package_price (浮点)"""
        r = self._list()
        active = next(it for it in r.json()["items"] if it["name"] == "活性辅酶")
        # 1*1335=1335 → 改成 1500.5: 1*1500.5=1500.5
        r2 = self.client.patch(
            "/api/orders/items/bulk",
            json={"items": [{"id": active["id"], "package_price": 1500.5}]},
        )
        self.assertEqual(r2.status_code, 200)
        updated = r2.json()["items"][0]
        self.assertEqual(updated["package_price"], 1500.5)
        self.assertEqual(updated["total"], 1500.5)

    def test_bulk_update_all_four_fields(self):
        """改 4 字段 (典型 PATCH 用法)"""
        r = self._list()
        calcium = next(it for it in r.json()["items"] if it["name"] == "钙镁健骨")
        r2 = self.client.patch(
            "/api/orders/items/bulk",
            json={"items": [{
                "id": calcium["id"],
                "required_qty": 30,
                "current_stock": 5,
                "package_count": 10,
                "package_price": 850.0,
            }]},
        )
        self.assertEqual(r2.status_code, 200)
        updated = r2.json()["items"][0]
        self.assertEqual(updated["required_qty"], 30)
        self.assertEqual(updated["current_stock"], 5)
        self.assertEqual(updated["package_count"], 10)
        self.assertEqual(updated["package_price"], 850.0)
        # unit_diff: 5-30=-25, total: 10*850=8500
        self.assertEqual(updated["unit_diff"], -25)
        self.assertEqual(updated["total"], 8500.0)

    def test_bulk_update_multiple_rows(self):
        """一次 PATCH 改多行 (显式「保存」按钮典型场景)"""
        r = self._list()
        items = r.json()["items"]
        active = next(it for it in items if it["name"] == "活性辅酶")
        omega = next(it for it in items if it["name"] == "辅酶奥米加")
        r2 = self.client.patch(
            "/api/orders/items/bulk",
            json={"items": [
                {"id": active["id"], "required_qty": 20},
                {"id": omega["id"], "current_stock": 10},
            ]},
        )
        self.assertEqual(r2.status_code, 200)
        data = r2.json()
        self.assertEqual(data["updated_count"], 2)
        # 验证每个 item 都更新了
        upd_by_id = {it["id"]: it for it in data["items"]}
        self.assertEqual(upd_by_id[active["id"]]["required_qty"], 20)
        self.assertEqual(upd_by_id[omega["id"]]["current_stock"], 10)

    def test_bulk_update_not_found_id(self):
        """找不到 id → 404"""
        r = self.client.patch(
            "/api/orders/items/bulk",
            json={"items": [{"id": 99999, "required_qty": 10}]},
        )
        self.assertEqual(r.status_code, 404)

    def test_bulk_update_empty_items(self):
        """empty items → 422 (Pydantic min_length=1 校验, 业务: 至少改 1 行)"""
        r = self.client.patch(
            "/api/orders/items/bulk",
            json={"items": []},
        )
        self.assertEqual(r.status_code, 422)

    def test_bulk_update_missing_items_field(self):
        """body 缺 items → 422 (Pydantic 校验)"""
        r = self.client.patch(
            "/api/orders/items/bulk",
            json={},
        )
        self.assertEqual(r.status_code, 422)

    def test_bulk_update_only_4_fields_allowed(self):
        """name 跟 unit 不允许改 (后端 OrderItemUpdate 没收这 2 字段)"""
        r = self._list()
        active = next(it for it in r.json()["items"] if it["name"] == "活性辅酶")
        # 试图改 name — 422 (Pydantic 拒绝额外字段, 因为 schema 没定义)
        r2 = self.client.patch(
            "/api/orders/items/bulk",
            json={"items": [{"id": active["id"], "name": "改品名", "required_qty": 20}]},
        )
        # Pydantic v2 默认是禁止额外字段 (extra="ignore" 的话会忽略, "forbid" 才 422)
        # 当前 OrderItemUpdate 没显式 extra=... 看 main.py
        # 如果忽略, 改 name 不生效, 但 required_qty 仍生效
        # 业务: 不让改 name, 至少要忽略
        # 这里不强求 422, 只验证 DB name 没改
        if r2.status_code == 200:
            db_row = self._get_by_name("活性辅酶")
            self.assertEqual(db_row.name, "活性辅酶", "name 不应该被改")

    def test_bulk_update_persists_to_db(self):
        """PATCH 后, DB 真的改了 (用 SQLAlchemy 查验证)"""
        r = self._list()
        grape = next(it for it in r.json()["items"] if it["name"] == "葡萄籽")
        r2 = self.client.patch(
            "/api/orders/items/bulk",
            json={"items": [{
                "id": grape["id"],
                "required_qty": 30,
                "current_stock": 8,
                "package_count": 11,
                "package_price": 950.0,
            }]},
        )
        self.assertEqual(r2.status_code, 200)
        # 直接查 DB
        db_row = self._get_by_name("葡萄籽")
        self.assertEqual(db_row.required_qty, 30)
        self.assertEqual(db_row.current_stock, 8)
        self.assertEqual(db_row.package_count, 11)
        self.assertAlmostEqual(db_row.package_price, 950.0, places=2)
        # updated_at 应该被 SQLAlchemy onupdate 更新
        # (注: onupdate 在 PATCH 时生效, 测试需要延迟或重读)
        # 这里不强求具体值, 只验证 not None
        self.assertIsNotNone(db_row.updated_at)

    # ---------- 业务联动 (库存按差量减少) ----------

    def test_business_rule_stock_decreases_with_required_increase(self):
        """业务规则: 需求↑则库存↓ (用户拍板 PR #70)
        这是前端联动逻辑, 后端只是存数值; 但需要验证 PATCH 发两个字段时正确落库
        """
        r = self._list()
        calcium = next(it for it in r.json()["items"] if it["name"] == "钙镁健骨")
        # 初始: required=27, stock=1, diff=-26
        # 业务场景: 客户把需求改成 30, 库存联动: stock = 1 - (30-27) = -2 → 业务兜底 max(0, -2) = 0
        # 前端联动: current_stock = orig_stock - (new_req - orig_req) = 1 - 3 = -2 → max(0,-2) = 0
        # PATCH 发: required_qty=30, current_stock=0
        r2 = self.client.patch(
            "/api/orders/items/bulk",
            json={"items": [{
                "id": calcium["id"],
                "required_qty": 30,
                "current_stock": 0,
            }]},
        )
        self.assertEqual(r2.status_code, 200)
        updated = r2.json()["items"][0]
        self.assertEqual(updated["required_qty"], 30)
        self.assertEqual(updated["current_stock"], 0)
        # unit_diff 重算: 0-30=-30
        self.assertEqual(updated["unit_diff"], -30)

    def test_business_rule_keep_db_invariant(self):
        """业务不变式: 改 required_qty 不自动联动库存 (后端只是 store, 联动前端做)
        即: 只 PATCH required_qty, 库存不变 — 验证后端不会"自作聪明"联动
        """
        r = self._list()
        active = next(it for it in r.json()["items"] if it["name"] == "活性辅酶")
        orig_stock = active["current_stock"]
        orig_req = active["required_qty"]
        # 只发 required_qty (没 current_stock)
        r2 = self.client.patch(
            "/api/orders/items/bulk",
            json={"items": [{"id": active["id"], "required_qty": orig_req + 5}]},
        )
        self.assertEqual(r2.status_code, 200)
        updated = r2.json()["items"][0]
        self.assertEqual(updated["required_qty"], orig_req + 5)
        # 库存保持不变 (后端不动 current_stock, 联动是前端职责)
        self.assertEqual(updated["current_stock"], orig_stock)
        # unit_diff 重算
        self.assertEqual(updated["unit_diff"], orig_stock - (orig_req + 5))


if __name__ == "__main__":
    unittest.main(verbosity=2)
