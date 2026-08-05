# BUG-01: 结算引擎核心缺陷 — 树结构不完整 + root 余额清零 + consumed 计算错误

## 严重级别

**P0 - 阻塞**：核心佣金计算结果错误

## 发现日期

2026-07-22

## 影响范围

- `skills/pair_commission.py` — `settle_period()`、`_build_settle_tree()`、`_settle_node()`、`_write_settle_result()`
- 所有结算操作

## 问题描述

结算引擎存在三个相互关联的核心缺陷，根因均为 `_build_settle_tree()` 的 PR-A 简化实现：

### 缺陷 A：结算树不构建真实层级结构

`_build_settle_tree()` 只拉取本期有 pending ledger 的成员，不读取完整 5 叉树。所有成员被扁平挂到 root 下，`slot_line_id` 被覆盖为 `i+1`，而非使用真实的 `parent_dist_id` + `slot_line_id`。

```python
# pair_commission.py L170-172 — 只取有 pending ledger 的成员
member_ids = {e.member_id for e in pending}
members = {m.id: m for m in (member_repo.get(mid) for mid in member_ids) if m}

# pair_commission.py L270 — 扁平挂载，slot 被覆盖
for i, m in enumerate(sorted_members[:5]):
    slot = SlotNode(slot_line_id=i + 1, ...)  # ← 不是真实 slot_line_id
    root.children.append(slot)
```

**影响**：跨期结算时，已有成员的 carry_in PV 不参与配对，新增成员被放到错误位置，P vs L 基于不完整子区 PV，佣金计算错误。

### 缺陷 B：Root 节点 carry_out 不被计算，结算后余额清零

`_settle_node()` 只为子节点计算 `carry_out_by_dist`，root 没有父节点来计算它的 carry_out。`_write_settle_result()` 中所有成员（含 root）的 `current_pv_balance` 被设为 `carry_out_by_dist` 中的值，root 不在该字典中，默认为 0。

```python
# pair_commission.py L489-491 — root 也在 members 里
for member in members.values():
    new_balance = result.carry_out_by_dist.get(member.member_dist_id, 0)
    member_repo.carry_out(member.id, new_balance)  # root → 0
```

**影响**：每次结算后 root（王常军）的 `current_pv_balance` 被清零。若 root 有 pending ledger，`consumed = pv_amount - 0 = pv_amount`，全部被标记为 paired（全额消耗），不管实际配对消耗了多少。

### 缺陷 C：Ledger consumed 计算混淆 carry_in 与本期 PV

结算树中节点的 `pv = carry_in + ledger_pv`，但 `_write_settle_result()` 中计算 consumed 时用的是 `entry.pv_amount`（仅本期 ledger PV），而 `carry_out` 是基于 `pv_total`（carry_in + ledger_pv）算出的剩余总量。

```python
# pair_commission.py L465-466
carry_out = result.carry_out_by_dist.get(entry.member_dist_id, 0)
consumed = entry.pv_amount - carry_out  # ← 应该是 pv_total - carry_out

# 例: carry_in=200, ledger=500, 实际配对消耗300, carry_out=400
# consumed = 500 - 400 = 100 (实际消耗了 300)
```

**影响**：当成员有 carry_in 时，ledger 的 consumed 计算错误，ledger 状态标记与实际配对消耗不一致。

## 复现场景

### 场景 1：缺陷 A — 跨期结算佣金错误

前置：空树，root=王常军(PV=0)。算法 base=2（默认 effective_max_active_lines=2，只挂 L1+L2）。

---

#### 第 1 期：添加 A(PV=1000)、B(PV=800)

按 base-5 digit reversal 算法（base=2），A 挂 root.L1，B 挂 root.L2。

**DB 真实树结构**（添加后）：
```
王常军 (PV=0)
├── L1: A (PV=1000, pending ledger)
├── L2: B (PV=800, pending ledger)
├── L3: (空, 未激活)
├── L4: (空, 未激活)
└── L5: (空, 未激活)
```

**结算树**（当前代码 _build_settle_tree 构造，members={root, A, B}）：
```
王常军 (pv=0)
├── slot1: A (pv=0+1000=1000)    ← carry_in=0 + ledger=1000
├── slot2: B (pv=0+800=800)
├── slot3: None
├── slot4: None
└── slot5: None
```

第 1 期**扁平树恰好与真实树一致**（因为 A、B 确实是 root 的直接子节点），所以第 1 期结算结果正确：

- P=A=1000, L=B=800, pair=MIN(1000,800)=800
- root.commission = 800 × 15% = 120 ✓
- A carry_out = 1000-800 = 200
- B carry_out = 0（全额消耗）

**第 1 期结算后 DB 状态**：
```
王常军 (PV=0, commission=120)
├── L1: A (PV=200, 即 carry_out=200)
├── L2: B (PV=0)
├── L3: (空)
├── L4: (空)
└── L5: (空)
```

---

#### 第 2 期：添加 C(PV=500)、D(PV=300)

按 base-2 digit reversal 算法，L2 层（step 2,3）：
- step=2: bit_reverse(0, 2, base=2)=0 → parent=A, col=0 → C 挂 A.L1
- step=3: bit_reverse(1, 2, base=2)=2 → parent=B, col=0 → D 挂 B.L1

**DB 真实树结构**（添加后）：
```
王常军 (PV=0)
├── L1: A (PV=200, carry_in=200, 无本期新增 ledger)
│   └── L1: C (PV=500, pending ledger)
├── L2: B (PV=0, carry_in=0, 无本期新增 ledger)
│   └── L1: D (PV=300, pending ledger)
├── L3: (空)
├── L4: (空)
└── L5: (空)
```

**预期结算树**（如果代码正确构建完整树）：
```
王常军 (pv=0)
├── L1: A (pv=carry_in 200 + ledger 0 = 200)
│   └── L1: C (pv=0+500=500)
├── L2: B (pv=0)
│   └── L1: D (pv=0+300=300)
├── L3: None
├── L4: None
└── L5: None
```

后序遍历计算：
1. A 节点：子区 P=C=500, L=0, pair=0, A.commission=0
   - C carry_out = 500
2. B 节点：子区 P=D=300, L=0, pair=0, B.commission=0
   - D carry_out = 300
3. root 节点：子区 P=A=200, L=B=0, pair=0, root.commission=0

**预期第 2 期总 commission = 0**（C 和 D 各自只有一个子区，无法配对；A 的 carry_in=200 也没有对位）

**实际结算树**（当前代码构造，pending ledger 只有 C 和 D，members={root, C, D}，A/B 不在 members 中）：
```
王常军 (pv=0)
├── slot1: C (pv=0+500=500)    ← C 被放到 slot1，不是真实的 A.L1
├── slot2: D (pv=0+300=300)    ← D 被放到 slot2，不是真实的 B.L1
├── slot3: None
├── slot4: None
└── slot5: None
```

- P=500(C), L=300(D), pair=MIN(500,300)=300
- root.commission = 300 × 15% = **45**

---

#### 差异对比

| 维度 | 预期（完整树） | 实际（扁平树） |
|------|---------------|---------------|
| C 的位置 | A.L1（单子区，无法配对） | root.slot1（参与 root 配对） |
| D 的位置 | B.L1（单子区，无法配对） | root.slot2（参与 root 配对） |
| A 的 carry_in=200 | 参与配对基数（但 L=0 未配上） | 丢失，A 不在结算树中 |
| 第 2 期 commission | 0 | 45（凭空多出） |
| commission 归属 | 无 | root |
| A 的 PV 余额 | 200（保留 carry_in） | 0（被清零） |

**这个场景的后果更严重**：预期不应该产生任何佣金（C 和 D 各自独占一个子区无法配对），但扁平树让 C、D 直接成为 root 的子节点，凭空算出 45 的佣金。同时 A 的 200 carry_in 被清零。

### 场景 2：缺陷 B — root 余额清零

**第 1 期**：root 有 PV=500（通过 ledger），添加 A(root.L1, PV=1000)，结算。
- 结算后 root 的 `carry_out_by_dist` 中没有 root 的记录
- root 的 `current_pv_balance` 被设为 0
- root 的 ledger consumed = 500 - 0 = 500，全部标记 paired

**预期**：root 的未配对 PV 应 carry 到下期，实际被清零。

### 场景 3：缺陷 C — consumed 计算错误

成员 A 上期 carry_in=200，本期新增 ledger PV=500，结算后 carry_out=400。
- 实际配对消耗 = 200 + 500 - 400 = 300
- 代码计算 consumed = 500 - 400 = 100
- 差额 200（carry_in 部分的消耗被忽略）

## 影响评估

| 维度 | 影响 |
|------|------|
| 佣金正确性 | 跨期结算佣金计算错误，carry_in PV 丢失 |
| 数据一致性 | root 余额被清零，consumed 计算错误，ledger 状态标记不准确 |
| 静默性 | 无报错、无日志告警，错误数据正常写入 DB |
| 业务影响 | 成员实发佣金金额错误，配对奖金 7 代分润也基于错误基础 |

## 修复建议

统一修复方案：**重构 `_build_settle_tree()` 为从 DB 递归构建完整树**。

1. 查询所有 Member 记录（不仅是有 pending ledger 的）
2. 按 `parent_dist_id` + `slot_line_id` 递归构建完整 5 叉树（复用 `_build_tree_from_db` 的索引逻辑）
3. 每个节点注入 `carry_in (current_pv_balance) + 本期新增 PV (从 pending ledger 聚合)`
4. 对完整树做后序遍历计算佣金
5. 为 root 节点计算 carry_out（root 自身 PV 不参与子节点配对，应全额 carry）
6. 在 `SettleResult` 中记录 `consumed_pv_by_dist`（实际配对消耗量），而非从 `carry_out` 反推 consumed

## 验证方法

1. 第 1 期：添加 2+ 成员，结算，确认 carry_out 正确
2. 第 2 期：添加新成员，结算，对比预期佣金
3. 检查老成员的 carry_in 是否参与配对
4. 检查 root 结算后余额是否保留（非清零）
5. 检查 ledger 的 consumed 是否与实际配对消耗一致
6. 验证 PV 守恒：consumed + carried = carry_in + 本期新增 PV

## 关联

- 外部审计报告：C-01（树平铺）、C-02（[:5]截断）、C-03（root 清零）、C-04（consumed 混淆）
- 测试计划：LD-01-01、LD-01-02
