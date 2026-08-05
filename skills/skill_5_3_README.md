# Skill 5_3 · 按位反转 (base-5 digit reversal) 添加新成员 (5 叉树)

> Skill 5 的 **#3 派生**:按 `TreeGenerate/verify_l6.py` 反推出来的「按位反转」规律
> 顺次挂入新成员,逐步计算 `commission / pairing / total`,把每一步增量作为历史回放给前端。
> **演示 / 复盘 / 单测**用,不读不写生产网体 `json/Tree_*.json`(除非显式开启 `local_output=true`)。

## 业务背景(从 TreeGenerate 反推)

`D:\Projects\Reward\TreeGenerate\verify_l6.py` 注释说 "Verify the bit-reversal-like pattern",
对 visio 树型图(2 叉版 15 节点)反推:每个父节点 P 在 BFS 序里的配对 = (2P, 2P+1),第 5 层新增的 32 个节点的"树型图位置顺序"按 `bit_reverse(0..31, 5)` 排序。
`verify_l6.py` 验证 L6 前 8 节点 X 坐标 = `64, 96, 80, 112, 72, 104, 88, 120` = `bit_reverse(0..7, 6) + 64`。

skill_5_3 把这个规律推广到 5 叉树(把 base-2 改成 base-5):

> **L+1 阶段新增的 5^L 个新成员,在 "L 层父节点 (5^(L-1) 个) × 5 列" 共 5^L 个槽位里,**
> **按 i=0..5^L-1 顺序, 第 i 个新成员填到第 `bit_reverse_base5(i, L)` 个槽位。**
> **bit_reverse_base5(n, L) = n 的 base-5 表示 (L 位) 各位倒序后转回 10 进制。**

## 业务规则(与 Skill 5 / Skill 5_1 / Skill 5_2 同源)

| 规则 | 值 |
|------|-----|
| 动力线 P | `MAX(子区分数)` |
| 佣金线 L | `SUM(其余 4 个子区分数)` ⚠️ 不是 MIN 是 SUM |
| 单节点基本佣金 | `MIN(P, L) × 15%` |
| 单区封顶 | 13,334 分 |
| 对等奖金 7 代比例 | 15% / 10% / 5% × 5 |

**与 Skill 5_1 / Skill 5_2 的核心区别**:

| 维度 | Skill 5_1 (列优先 BFS) | Skill 5_2 (配对优先 BFS) | **Skill 5_3 (按位反转, 本)** |
|------|------------------------|---------------------------|-------------------------------|
| 落位算法 | 列优先:col0→col1→…→col4 | 凑 L1+L2 配对优先 | **base-5 digit reversal** |
| 5 列都挂? | ❌ v4 起只挂奇数线 (L1/L3/L5) | ❌ 只挂 L1+L2 凑配对 | ✅ **全员 5 列都挂** |
| 业务触发 commission? | ❌ 永远 0 (缺右叉) | ✅ L1+L2 都挂时触发 | ✅ 满 5 列时整体参与 |
| 树型图位置 | 列优先(从左到右) | L1+L2 优先 | **按位反转** (FFT/iDFT 风格) |
| 来源沉淀 | user_add_order_rule.md 2 叉版 | skill_5_1 配套补全 | **TreeGenerate visio 树型图反推** |

## 业务落位规则(「按位反转」)

### 核心公式

新成员在 L+1 阶段的序号 `i` (0-based, 0 ≤ i < 5^L), 槽位 = `bit_reverse_base5(i, L)`:
```
槽位编号 s = bit_reverse_base5(i, L)
父节点 BFS 序 idx = s // 5
col = s % 5  (0-based, 业务 line_id = col + 1)
父节点 = L 层 BFS 序里第 idx 个
新成员 = 父节点的第 col 个孩子 (line_id = col + 1)
```

### 5 叉树 L+1 阶段 5^L 个新成员的填充顺序

| 阶段 | 5^L | 反转位数 | 行为(简表) |
|------|-----|---------|-----------|
| L1 (root 下 5 子) | 5 | 1 | 1位反转=自身:顺序 = L1, L2, L3, L4, L5 |
| L2 (5 个 L1 父 × 5 列) | 25 | 2 | 2位反转=自身:先全部 col 0, 再 col 1, …, 再 col 4 (列优先 BFS) |
| L3 (25 个 L2 父 × 5 列) | 125 | 3 | 3位反转 ≠ 自身, **跟列优先 BFS 不同** |
| L4 | 625 | 4 | 4位反转 |
| L5 | 3,125 | 5 | 5位反转 (compute_L5.py L5 等价 L4 阶段的 5^5=3125) |

### L3 阶段 125 步按位反转行为细节

父 idx 序列(i=0..24, col 0):
```
[0, 5, 10, 15, 20, 1, 6, 11, 16, 21, 2, 7, 12, 17, 22, 3, 8, 13, 18, 23, 4, 9, 14, 19, 24]
```

每个 col(0..4)各重复 1 次 = 25 个新成员/col × 5 col = 125 步。

完整 125 步父 idx 序列 (i=0..124) = 上面 25 个父 idx 序列重复 5 次(每次换 col 0..4)。

### 与 2 叉版的对照验证(verify_l6.py)

| 2 叉版 (verify_l6.py) | 5 叉版 (skill_5_3) |
|------------------------|---------------------|
| L3 阶段(2^2=4 步, 2位反转) | L2 阶段(5^2=25 步, 2位反转) |
| `bit_rev(0..3, 2, 2) = 0, 2, 1, 3` | `bit_rev(0..24, 2, 5) = 0, 5, 10, 15, 20, 1, 6, ...` |
| 父 idx = `0, 1, 0, 1`, col = `0, 0, 1, 1` | 父 idx = `0, 1, 2, 3, 4, 0, 1, ...`, col = `0, 0, 0, 0, 0, 1, 1, ...` |
| 节点 4, 5, 6, 7 (符合 tree-structure.md) | 节点按位反转位置(见 CLI demo) |

| 2 叉版 (compute_L5.py L5 阶段) | 5 叉版 (skill_5_3 L4 阶段) |
|--------------------------------|-----------------------------|
| L5 阶段 32 步, 5位反转 | L4 阶段 625 步, 4位反转 |
| `L5_tree_order = [32 + bit_rev(i, 5) for i in range(32)]` | `slot = bit_rev(i, 4, 5)` for `i in range(625)` |
| `L5_indices_bitrev = [0, 16, 8, 24, 4, 20, 12, 28, ...]` | 父 idx 序列 (L3 阶段填充后) |

| 2 叉版 (verify_l6.py L6 阶段) | 5 叉版 (skill_5_3 L5 阶段) |
|--------------------------------|-----------------------------|
| L6 阶段 64 步, 6位反转 | L5 阶段 3,125 步, 5位反转 |
| Expected first 8 X 坐标 = `64, 96, 80, 112, 72, 104, 88, 120` = `bit_rev(0..7, 6) + 64` | 跟 compute_L5.py L5 阶段类比 (反推父 idx) |

## 快速上手

### 1. 命令式(推荐)

```python
from skill_5_lib import Node5
from skill_5_3 import simulate_addition_bitrev

# 从空 5 叉 root 树开始(默认 root pv=1000, max_children=5)
tree = Node5(uid=1, pv=1000, depth=0, max_children=5)

# 模拟挂入 30 位新成员(每 PV=200,覆盖 L1 + L2 共 30 位)
history = simulate_addition_bitrev(
    tree,
    pv_list=[200] * 30,
    names=[f"新成员{i+1}" for i in range(30)],
    include_pairing=True,
)

# history[0] = {
#   'step': 1, 'uid': -1, 'pv': 200, 'parent_uid': 1,
#   'parent_basic_before': 0.0, 'parent_basic_after': 0.0,
#   'basic_before': 0.0, 'basic_after': 0.0,
#   'pairing_before': 0.0, 'pairing_after': 0.0,
#   'total_before': 0.0, 'total_after': 0.0,
#   'lift_basic': 0.0, 'lift_pairing': 0.0,
#   'lift_total': 0.0, 'lift_pct': None
# }
```

### 2. CLI 演示

```bash
# 默认 30 人 × PV=200(覆盖 L1 + L2, base=5 进制 2 位反转 = 自身 = 列优先 BFS)
python skills/skill_5_3.py

# 自定义 100 人 × PV=150
python skills/skill_5_3.py -n 100 --pv 150

# 跑完整 L3 阶段 125 人 (看真正的 3 位反转行为)
python skills/skill_5_3.py -n 155 --pv 200

# 2 叉版(用 max_children=2, 复现 verify_l6.py 的 L3 阶段 4, 5, 6, 7)
python skills/skill_5_3.py -n 7 --max-children 2

# JSON 模式输出(stdout 流式 JSON,方便 Agent 消费)
python skills/skill_5_3.py -n 30 --pv 200 --json
```

CLI 输出表格(`run_demo_bitrev`):
```
 #   UID    PV   Par    BcΔ    Basic   PairΔ     Pair    TotΔ    Total   Lift%   L
 1    -1   200     1    0.00     0.00    0.00     0.00    0.00     0.00     N/A  L1
 2    -2   200     1   30.00    30.00    0.00     0.00   30.00    30.00     N/A  L2
 3    -3   200     1    0.00    30.00    0.00     0.00    0.00    30.00    +0.00%  L3
 4    -4   200     1    0.00    30.00    0.00     0.00    0.00    30.00    +0.00%  L4
 5    -5   200     1    0.00    30.00    0.00     0.00    0.00    30.00    +0.00%  L5
 6    -6   200    -1   30.00    60.00    0.00     0.00   30.00    60.00  +100.00%  L1
 7    -7   200    -2    0.00    60.00    0.00     0.00    0.00    60.00    +0.00%  L1
 ...
 31   -31   200    -6   60.00   390.00    4.50    27.00   64.50   417.00   +18.30%  L1
 32   -32   200    -7   30.00   420.00    4.50    31.50   34.50   451.50    +8.27%  L1
 33   -33   200    -8   30.00   450.00    4.50    36.00   34.50   486.00    +7.64%  L1
 ...
```

`L` 列显示新成员挂在父节点的第几线(L1=col 0, L2=col 1, ..., L5=col 4)。

### 3. HTTP API(前端 / Agent 集成)

```bash
curl -X POST http://localhost:28080/skills/skill_5_3/batch/run \
  -H "Content-Type: application/json" \
  -d '{
    "members": [
      {"pv": 200, "name": "M1"},
      {"pv": 200, "name": "M2"},
      {"pv": 200, "name": "M3"}
    ],
    "include_pairing": true
  }'
```

返回 JSON 结构跟 `skill_5_1` 完全对齐(只是 `skill="skill_5_3_batch"`)。

## API 参考

### `find_next_slot_bitrev(tree, step)` — 找下一个父节点

```python
def find_next_slot_bitrev(tree: Node5, step: int, base: int = 5) -> Optional[Node5]:
    """按「base 进制 digit reversal」找下一个挂载点的父节点。
    step: 已挂入的新成员数 (0-based), 用于推算当前 level + i + bit_rev
    base: 进制 (5 叉树 = 5, 2 叉树 = 2)
    Returns: 父节点; 树满则返回 None。
    """
```

### `add_user_bitrev(tree, pv, name='', code='')`

```python
def add_user_bitrev(
    tree: Node5, pv: int,
    name: str = "", code: str = "",
    base: int = 5,
    _state: Optional[Dict[str, int]] = None,
) -> Optional[Node5]:
    """按 base 进制 digit reversal 在 tree 上挂一个新成员(in-place)。
    自动选 next slot, append 到对应 parent.children 末尾。
    Returns: 新挂入的 Node5; 树无空位返回 None(并自动跳过)。
    """
```

### `simulate_addition_bitrev(...)` — **核心 API**

```python
def simulate_addition_bitrev(
    tree: Node5,
    pv_list: List[int],
    names: Optional[List[str]] = None,
    codes: Optional[List[str]] = None,
    include_pairing: bool = True,
    parent_dist_id_map: Optional[Dict[int, str]] = None,
    start_rank: int = 0,
    base: int = 5,
) -> List[Dict[str, Any]]:
    """按「按位反转」依次挂入多个新成员, 每一步记录实时利润与父节点增量。

    与 skill_5_1.simulate_addition 结构一致, 但挂载算法不同:
        - skill_5_1: 列优先 BFS (只挂奇数线, commission 永远 0)
        - skill_5_2: 配对优先 BFS (凑 L1+L2 配对, 触发 commission)
        - skill_5_3: 按位反转 (全员 5 列都挂, base-5 digit reversal)
    """
```

### 辅助函数

| 函数 | 用途 |
|------|------|
| `_bit_reverse_base_b(n, bits, base=5)` | n 的 base 进制 digit reversal, 共 bits 位 |
| `_level_of_step(step, base=5)` | 第 step 个新成员(0-based)处于哪个 level |
| `_index_in_level(step, base=5)` | 第 step 个新成员在所在 level 内的 index (0-based) |
| `_bfs_all(node)` | BFS 遍历整棵树(从 skill_5_1 复用) |
| `_snapshot_profit(tree, include_pairing)` | 整树 basic/pairing/total 快照(从 skill_5_1 复用) |
| `AdditionStep` 数据类 | 每一步挂载的完整快照(从 skill_5_1 复用) |
| `_ancestor_chain(root, target, ...)` | root → target 完整祖先链(从 skill_5_1 复用) |
| `load_from_jstree_dict` / `load_tree_from_jstree_file` | 从 officev2 jstree JSON 加载(从 skill_5_1 复用) |
| `history_to_json(history)` | history 列表 → JSON 字符串(从 skill_5_1 复用) |
| `run_demo_bitrev(...)` | CLI 演示入口(打印表格) |

### `AdditionStep` 数据类

跟 skill_5_1 完全一致(从 skill_5_1 复用):

```python
@dataclass
class AdditionStep:
    step: int                              # 第几步(从 1 开始)
    uid: int                               # 新成员 uid
    pv: int                                # 新成员 PV
    parent_uid: int                        # 父节点 uid
    parent_dist_id: str = ""               # 父节点 officev2 distId(可选)
    member_dist_id: str = ""               # 新成员自己的 distId (PREVIEW-N)
    ancestor_chain: List[Dict] = field(default_factory=list)  # 完整祖先链

    parent_basic_before: float             # 父节点挂入前的 basic_commission
    parent_basic_after: float              # 父节点挂入后的 basic_commission ★ 用户视角

    basic_before: float                    # 全树 basic(挂前)
    basic_after: float                     # 全树 basic(挂后)
    pairing_before: float                  # 全树 pairing(挂前)
    pairing_after: float                   # 全树 pairing(挂后)
    total_before: float                    # 全树 total(挂前)
    total_after: float                     # 全树 total(挂后)

    lift_basic: float                      # basic 增量
    lift_pairing: float                    # pairing 增量
    lift_total: float                      # total 增量
    lift_pct: Optional[float]              # 百分比提升;total_before=0 时返回 None
```

## 算法说明

```
simulate_addition_bitrev(tree, pv_list):
    snapshot_before = _snapshot_profit(tree)
    history = []
    step = 0  (累计新成员数, 0-based)
    for pv in pv_list:
        level = _level_of_step(step)               # 当前 step 在哪个 level
        i     = _index_in_level(step)              # 该 level 内的 index
        slot  = _bit_reverse_base_b(i, level, 5)   # 反转得到槽位编号
        parent_bfs_idx = slot // 5                 # 父节点在 BFS 序 (L 层) 里的索引
        col = slot % 5                             # 父节点的第几列
        parent = L 层 BFS 序里第 parent_bfs_idx 个真实成员

        parent_basic_before = basic_commission(parent)
        new_node = Node5(uid=-global_rank, pv=pv, depth=parent.depth+1, line_id=col+1, ...)
        parent.children.append(new_node)
        step += 1

        snapshot_after = _snapshot_profit(tree)
        lift = after - before
        history.append(AdditionStep(...).to_dict())
    return history
```

**复杂度**:
- `_bit_reverse_base_b`: O(bits) = O(level) = O(log_base N)
- `find_next_slot_bitrev` (BFS 找 level 父节点): O(N) per call
- `_snapshot_profit`: O(N²) per call (pairing_bonus 是 7 层递归 × N 节点)
- N 步总计: **O(N³)**(N=30 demo 场景下 < 50ms,够用)

## ⚠️ `lift_pct` 为 None 的情况

跟 skill_5_1 一致:

| 值 | 含义 | 展示建议 |
|----|------|----------|
| `0.0` | 实际提升 0% | `+0.00%` |
| `None` | 挂前 total=0,无法计算百分比 | `N/A` 或 `+inf%` |
| `123.4` | 正常百分比 | `+123.40%` |

## 算法对照表(2 叉 vs 5 叉)

| L 阶段 | 2 叉版 (verify_l6 / compute_L5) | 5 叉版 (skill_5_3) |
|--------|--------------------------------|---------------------|
| L1 | 2 步, 1 位反转 = 自身 | 5 步, 1 位反转 = 自身 (跟列优先 BFS 一致) |
| L2 | 4 步, 2 位反转 = 自身 (节点 4, 5, 6, 7) | 25 步, 2 位反转 = 自身 (跟列优先 BFS 一致) |
| L3 | 8 步, 3 位反转 ≠ 自身 (compute_L5 行为) | 125 步, 3 位反转 ≠ 自身 (跟列优先 BFS 不同!) |
| L4 | 16 步, 4 位反转 ≠ 自身 | 625 步, 4 位反转 ≠ 自身 |
| L5 | 32 步, 5 位反转 (compute_L5.py L5 阶段) | 3,125 步, 5 位反转 |
| L6 | 64 步, 6 位反转 (verify_l6.py 验证 ✓) | 15,625 步, 6 位反转 |

## 业务约束(TODO: v2)

- [ ] `is_repeat=False` 检查:同 PV 是否允许在同一父下挂多次
- [ ] 失活节点(< 100 PV / 4 周)不向上传递分数
- [ ] 时间窗口(周结/日结)
- [ ] 业务规则可配置(目前硬编码 P=MAX, L=SUM, 7 代 15/10/5×5)

## 与 web 集成

- 后端 `POST /skills/skill_5_3/batch/run`(见 `main.py:run_skill_5_3_batch`)
- 前端 `renderSkill_5_3Card`(`static/index.html`)渲染 history 表格 + 汇总卡
- 卡片右上 **按位反转 · base-5 digit reversal** 徽标
- 演示快捷方式:在 chat 输入框输入 `/skill_5_3` → 自动打开 modal + 预填 5 行 PV=200
- 可选持久化:batch 面板勾选「演示完成后保存到本地」→ `local_output=true` → 写入 `json/Tree_demo_5_3.json`

## 相关文件

| 文件 | 作用 |
|------|------|
| `D:\Projects\Reward\TreeGenerate\verify_l6.py` | 2 叉 L6 阶段按位反转验证(本 skill 算法来源) |
| `D:\Projects\Reward\TreeGenerate\compute_L5.py` | 2 叉 L5 阶段按位反转实现参考 |
| `D:\Projects\Reward\TreeGenerate\verify_formula.py` | 2 叉 "bit-reversal-like pattern" 验证 |
| `skills/skill_5_1.py` / `skills/skill_5_1_README.md` | 列优先 BFS (skill_5_3 的对比参考) |
| `skills/skill_5_2.py` | 配对优先 BFS (skill_5_3 的对比参考) |
| `skills/skill_5_lib.py` | 5 叉制 Node5 + 业务计算原语(内部基础库) |
| `skills/skill_5_3.py` (本) | 按位反转 + 5 叉网体实时佣金 |
| `docs/skill_5_1.md` | API SPEC(本 skill 跟它结构对齐) |

---

> **许可**: 与项目其他文档一致, 仅作个人学习与求职展示用。
