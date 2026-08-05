# BUG-04: 佣金计算公式错误 — 3+ 分支时应取其余分支PV之和而非 MIN(P, L)

## 严重级别

**P0 - 阻塞**：核心佣金计算公式与业务规则不符，3+ 分支时佣金结果偏低

## 发现日期

2026-07-22

## 影响范围

- `skills/skill_5_lib.py` L587 — `basic_commission()` 预览计算
- `skills/pair_commission.py` L330 — `_settle_node()` 结算计算
- `main.py` L2892 — 前端树视图 ownBasic 预览
- 所有 3+ 分支的佣金计算结果

## 问题描述

百雅康佣金计算的业务规则按分支数量分两种情况：

- **2 个分支**：`commission = MIN(P, L) × 费率`（P=较大分支PV，L=较小分支PV，取小值配对）
- **3+ 个分支**：先比较所有分支PV大小，找出PV最大的分支，然后 `commission = (其余分支PV之和) × 费率`，不取 MIN

代码中无论分支数量，始终使用 `MIN(P, L) × 费率`。当分支数 ≥3 且其余分支PV之和 > 最大分支PV时，MIN 截断了其余分支PV之和的值，导致佣金偏低。

### 错误代码位置

**skill_5_lib.py L587**：
```python
return min(p_score, l_sum) * COMMISSION_RATE  # ← 始终取 MIN，3+ 分支时错误
```

**pair_commission.py L330**：
```python
pair = min(p_pv, sum_rest)  # ← 始终取 MIN
node_commission = pair * COMMISSION_RATE
```

**main.py L2892**：
```python
own_basic = float(min(p_pv, l_sum) * 0.15)  # ← 始终取 MIN
```

三处均未按分支数量区分公式。

## 复现场景

### 场景 1：4 个分支，其余分支PV之和 > 最大分支PV

root 下 4 个子区：L1=1000, L2=1000, L3=500, L4=300

- 最大分支 PV = 1000（L1）
- 其余分支 PV 之和 = L2+L3+L4 = 1000+500+300 = 1800

**当前代码**（始终 MIN）：
```
commission = MIN(1000, 1800) × 15% = 1000 × 15% = 150
```

**业务规则**（3+ 分支，取其余分支PV之和）：
```
commission = 1800 × 15% = 270
```

**差额：270 - 150 = 120，佣金少算 44.4%。**

### 场景 2：2 个分支，MIN 正确

root 下 2 个子区：L1=1000, L2=800

- 最大分支 PV = 1000
- 其余分支 PV 之和 = 800

**当前代码**：`MIN(1000, 800) × 15% = 120`
**业务规则**：`MIN(1000, 800) × 15% = 120` ✓

2 个分支时 MIN 公式正确，无需修改。

### 场景 3：3 个分支，其余分支PV之和远大于最大分支

root 下 3 个子区：L1=500, L2=1500, L3=1500

- 最大分支 PV = 1500（L2）
- 其余分支 PV 之和 = 500+1500 = 2000

**当前代码**：`MIN(1500, 2000) × 15% = 225`
**业务规则**：`2000 × 15% = 300`

**差额：300 - 225 = 75，佣金少算 25%。**

### 场景 4：3 个分支，其余分支PV之和 < 最大分支PV时无差异

root 下 3 个子区：L1=1000, L2=300, L3=200

- 最大分支 PV = 1000
- 其余分支 PV 之和 = 300+200 = 500

**当前代码**：`MIN(1000, 500) × 15% = 75`
**业务规则**：`500 × 15% = 75` ✓

其余分支PV之和 < 最大分支PV时，MIN(P,其余之和)=其余之和，结果相同。

## 影响评估

| 维度 | 影响 |
|------|------|
| 佣金正确性 | 3+ 分支且其余分支PV之和 > 最大分支PV时佣金系统性偏低，偏差 = (其余之和 - 最大PV) × 费率 |
| 触发条件 | 分支数 ≥3 且其余分支PV之和 > 最大分支PV |
| 影响范围 | 结算、预览、前端显示中所有 3+ 分支的佣金计算 |
| 连锁影响 | 7 代配对奖金基于错误的基本佣金，分润也全部偏低 |
| 静默性 | 无报错，佣金正常写入但金额错误 |

## 修复建议

三处均按分支数量区分公式：

**skill_5_lib.py L587**：
```python
# 旧: return min(p_score, l_sum) * COMMISSION_RATE
if len(sub_pvs) <= 2:
    return min(p_score, l_sum) * COMMISSION_RATE  # 2 分支: MIN(P,L)
else:
    return l_sum * COMMISSION_RATE  # 3+ 分支: 其余分支PV之和 × 费率
```

**pair_commission.py L330**：
```python
# 旧: pair = min(p_pv, sum_rest)
if len(sub_pvs) <= 2:
    pair = min(p_pv, sum_rest)  # 2 分支: MIN(P,L)
else:
    pair = sum_rest  # 3+ 分支: 其余分支PV之和
node_commission = pair * COMMISSION_RATE
```

**main.py L2892**：
```python
# 旧: own_basic = float(min(p_pv, l_sum) * 0.15)
if len(real_child_pvs) <= 2:
    own_basic = float(min(p_pv, l_sum) * 0.15)  # 2 分支
else:
    own_basic = float(l_sum * 0.15)  # 3+ 分支: 其余分支PV之和 × 费率
```

同时需更新 `skill_5_lib.py` 文件头注释（L23）和 `basic_commission()` docstring（L560-566）中的公式描述，明确区分 2 分支和 3+ 分支的规则。

## 验证方法

1. 构造 2 分支场景（L1=1000, L2=800），确认佣金 = MIN(1000,800)×15% = 120
2. 构造 3 分支场景（L1=1000, L2=1000, L3=500），确认佣金 = (1000+500)×15% = 225（非 MIN(1000,1500)×15%=150）
3. 构造 4 分支场景（L1=1000, L2=1000, L3=500, L4=300），确认佣金 = (1000+500+300)×15% = 270
4. 构造 3+ 分支且其余分支PV之和 < 最大分支PV的场景，确认佣金 = 其余之和×15%（与旧代码结果相同）
5. 验证 7 代配对奖金基于正确的佣金计算
6. 验证前端预览 ownBasic 与结算结果一致

## 关联

- bug-02 的复现场景佣金计算也受此影响（3+ 分支时应为其余分支PV之和×15% 而非 MIN(P,L)×15%）
- bug-03 的预览偏差问题在修复此 bug 后需重新评估
