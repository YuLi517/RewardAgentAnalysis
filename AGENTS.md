# AGENTS.md — RewardAgentAnalysis 项目开发指南

> 给未来在这个项目工作的 agent (Mavis / OpenCode / Codex / Cursor / Aider / Devin / Gemini CLI / ...)
> 读完这个文件, 你应该知道: 怎么改代码、怎么测、怎么提 PR、踩过什么坑、业务规则是什么。

---

## 1. 项目概览

**RewardAgentAnalysis** — 5 叉树 9 层网体 member/commission 系统, 阶段 3 演进中。

- **GitHub**: https://github.com/YuLi517/RewardAgentAnalysis
- **技术栈**: FastAPI + SQLAlchemy + SQLite + 原生 HTML/CSS/JS (没用 React)
- **LLM 路由**: MiniMax (主), 跑 chat 跟 skill 调用
- **核心特性**:
  - 5 叉树按位反转 (base-5 digit reversal) 挂入算法
  - ISO 周结算, 15% commission rate, 7 代祖先链配对奖 `[0.15, 0.10, 0.05×5]`
  - 「挂满 9 层」渐进解锁业务规则 (PR #18 拍板)
  - 算法 base 动态 (PR #18, 跟随 root.effective_max_active_lines() = 2/4/5)
  - 周 commission 结算 (PVLedger + CommissionPeriod)
  - 成员编码格式 `N5637590.X` (PR #50 拍板, root=1, 尾号依次 +1)

---

## 2. 业务规则 (user 拍板, 不可擅改)

### 2.1 「挂满 9 层」渐进解锁 (PR #18)

- **默认 eff (effective_max_active_lines) = 2** (root 只能往 line 1+2 挂人)
- **line 1 + line 2 都满 9 层 (max_depth >= 9) → eff=4** (line 3+4 解锁)
- **line 1-4 都满 9 层 → eff=5** (line 5 解锁)
- "line 满" 定义: 该 line 父节点下面有 9 层子孙, **不含** line 自己
- root.eff 计算: 渲染层 (`_compute_effective_active_from_json` in main.py) 跟算法层
  (`effective_max_active_lines` in skills/skill_5_lib.py) **必须一致** (PR #25 教训)

### 2.2 root 节点

- root distId = `N5637590.1`, name = `王常军`
- **root 现在是 Member 表的一行** (PR #28 加的), 字段:
  - `parent_dist_id = NULL`
  - `slot_line_id = 0` (跟 1..5 区分)
  - `current_pv_balance = 0`, `total_commission = 0.0`
  - `created_period_id = '2026-W28'` (比最早成员早)
  - `last_period_id = NULL`
- 部署 PR #28 后跑 `python tools/init_root_member.py` (幂等)

### 2.2c 业务周 (Sun-Fri) + 补录窗口 (Sat-Mon) (PR #55 拍板, 2026-07-20)

- **业务周期 ID 格式**: `2026-07-12_W29` (开始日 + ISO week)
  - 旧格式 `2026-W29` (ISO 周, Mon-Sun) 已废弃
  - 业务 W 编号沿用 ISO W 编号 (数字保持), 但范围是 Sun-Fri
  - 业务 W29 范围: 2026-07-12 (Sun) ~ 2026-07-17 (Fri 23:59:59.999) — 跟 ISO W29 (Mon-Sun) 不同
- **业务周期范围**:
  - **open**: Sun 00:00 → Fri 23:59:59.999 (6 天), 标准期, 可挂入可主 settle
  - **supplement**: Sat 00:00 → Mon 23:59:59.999 (3 天, "下班前"), 补录窗口
    - 只能补**基本 commission** (own_commission, 15% × MIN(P, L))
    - 跳过 pairing_bonus (7 代对等分润, 对等链已冻结)
  - **closed**: Tue 00:00 起, 周期彻底结束, 不能再补
- **主 settle** vs **补录**:
  - 主 settle: `?supplement_only=false` (默认), 算 own + 7 代对等 → members.total_commission
  - 补录: `?supplement_only=true`, 算 own only → period.supplement_commission + supplement_count
  - 状态转移: open → settled (主 settle) → closed (Tue 起, 补录截止)
- 部署 PR #55 后跑 `python tools/migrate_pr55_period_id.py` (idempotent)
  - 旧 ID `2026-W29` → 新 `2026-07-12_W29`
  - 重算 commission_periods.start_at / end_at (Sun-Fri 范围) + supplement_until_ts (Mon 23:59)
  - 调整 status: settled + supplement_until_ts 过期 → closed

### 2.3 批量重置测试数据 (PR #56 拍板, 2026-07-20)

- **API**: `POST /api/admin/reset_test_data?confirm=true`
- **删除**: 所有非 root members (N-7* + N5637590.* 除 root) + 全部 PV 流水 + 全部结算期
- **保留**: root 成员 (N5637590.1 王常军), 字段重置 (carry=0, total_commission=0, last_period_id=NULL)
- **重建**: 当前 commission_period (PR #55 业务周, 重新 init)
- **保护**: `confirm=false` 时返回 400 (防误点); UI 二次确认 (浏览器 `confirm()` 弹窗)
- **删除顺序** (防 FK constraint): pv_ledger → members (除 root) → commission_periods
- **UI 按钮**: toolbar "🗑️ 重置" (警示红, 跟金的"结算"和蓝紫的"补录"区分)
- **业务场景**: 测试期间反复加成员试算法, 节点爆满, 一键回到初始状态
- 用法:
  ```bash
  # 浏览器点 "🗑️ 重置" 按钮 + 二次确认
  # 或直接 API:
  curl -X POST "http://127.0.0.1:38080/api/admin/reset_test_data?confirm=true"
  ```

### 2.2b 成员编码格式 `N5637590.X` (PR #50 拍板, 2026-07-17)

- 全部 member distId 用 `N5637590.X` 格式 (尾号 = DB 中按 id asc 的序号)
- root = `N5637590.1` (王常军), 其他按 id asc 依次 +1 (`N5637590.2`, `N5637590.3`, ...)
- 新成员分配: commit_preview 用 `PREVIEW-N` 编号作为 `N5637590.N` (跟 preview 同号计数器)
- **u测试 fixture 字符串可保持 N-7 格式** (内部 fixture, 不依赖算法)
- 改 distId 格式必查 §5.18 列出的所有引用点

### 2.3 算法 base 动态 (PR #18/22)

- 算法 base 不固定 5, 而是跟随 root.eff
- 但 base 只决定 *L1* 几叉, L2 之后每个父都按自己 eff 决定几叉
- 算法遍历顺序: `for level in range(1, max_level+1): for i in range(base^level): slot = bit_reverse_base_b(i, level, base)`
- 跳过 (父满 / col 已被占 / line_id > parent.eff)

### 2.4 批量添加表格化 (PR #57 拍板, 2026-07-21)

- **UI**: 4 列表格 (姓名 / PV / 角色下拉 / 删除按钮), 不用 textarea
- **默认 3 行** (空), "+ 添加一行 (Enter)" 加新行
- **不用"本批默认角色"工具栏** (用户决定: 全部用表格输入, 每行独立选)
- **角色下拉**: 7 个角色 (消费股东/预备合伙人/合伙人员工/初级管理合伙人/中级管理合伙人/高级管理合伙人/Inactive)
- **默认角色**: 消费股东
- **键盘**: Tab 跳列 (浏览器默认), Enter 加行/提交 (最后一行 Enter 直接提交)
- **严格校验**: 姓名空 / PV 非数字 → 红框 (`row-input.invalid`) + `qaMsg` 错误 + 自动 focus 第一个错误输入
- **提交按钮**: 实时显示有效行数, 文本 `"批量挂入并写盘 (N 位)"`
- **API 兼容**: 走 `quickMountAndCommit(members, modal)`, `members[i].role` 字段 API 已支持 (PR #46 拍板)
- **删除**: 每行 🗑️ 按钮, 至少留 1 行
- 改批量添加 UI 必查 §5.24 列出的所有引用点

### 2.5 父节点 commission preview 徽章 (PR #58 拍板, 2026-07-21)

- **业务**: 子节点本期 PV 出现后, 父节点**实时**显示能从本期 PV 拿到的 commission (own + 7 层对等)
- **计算**: `_build_tree_from_db` 注入 `ownBasic` + `commissionPreview` 字段
  - `ownBasic = MIN(MAX 子区 periodPv, SUM 其余 4) × 15%`
  - `pairBonus` = 7 层对等, 按 `[0.15, 0.10, 0.05×5]` 分给 1/2/3/4/5/6/7 代祖先
  - `commissionPreview = ownBasic + pairBonus`
  - 跟 `settle_period._settle_node + _apply_pairing_bonus` 规则**完全一致**
- **渲染**: 紫色徽章 `本期可拿 ¥X.XX`
  - 只在 `currentPeriodStatus == "open"` 时显示 (settled 期已落账, 不算 preview)
  - 0 commission 不显示
  - tooltip 详细: `own basic: ¥X + 7层对等 pair: ¥Y = ¥Z\n基于本期 periodPv 模拟`
- **视觉分级**:
  - 绿 (#DCFCE7 / #166534)  本期 PV (新增)
  - 黄 (#FEF3C7 / #92400E)  剩余 PV (carry)
  - 金 (#FEF3C7 / #92400E)  累计 $ (历史 settle)
  - 紫 (#EDE9FE / #6D28D9)  本期可拿 (模拟, period=open) ← **新**
  - 紫色暗示"未来/预测", 跟"实际累计"区分
- **业务示例**: z1=500 + z2=300 → 王常军 ownBasic=¥45, pairBonus=¥0, 总 ¥45
- 改 commission preview 必查 §5.25 列出的所有引用点

### 2.6 PV 输入框自由输入 + 自定义 spinner (PR #59/#60 拍板, 2026-07-21)

- **业务**: PV 值用户可输任意正整数 (1, 50, 99, 100, 任意), 同时支持 +/- 按钮快速调整 (100 整数倍)
- **PR #59 (基础)**: 5 个 PV input 全部 `type="number" min="1" step="1"` → `type="text" inputmode="numeric" pattern="[0-9]+"`
  - 去掉 `min` / `step` 属性 (text input 上无效)
  - 加 `inputmode="numeric"` (移动端仍是数字键盘)
  - 加 `pattern="[0-9]+"` (HTML5 验证整数)
  - JS `parseInt` + `isNaN` 校验仍工作 (PR #57 已有)
- **PR #60 (增强)**: 自定义 +/- spinner 按钮 (跳 100), 跟 native number spinner 视觉一致
  - `.pv-stepper` wrapper: input + 2 按钮 (上下叠, 右侧内嵌)
  - 按钮 click: 读 input 当前值 ± 100, 写回, 触发 input 事件
  - `< 0` clamp (业务: PV >= 0)
  - 5 个 input 全部 wrap (PR #59 兼容)
- **5 个 input 位置**:
  1. `id="skillPvInput"` (skill modal)
  2. `name="pv"` (tvCompactForm)
  3. `id="qaPv"` (单加成员)
  4. `class="row-input row-pv"` (批量添加 row, 用户截图)
  5. `class="batch-pv"` (skill 批量)
- 改 PV input 必查 §5.26 列出的所有引用点

### 2.7 批量添加页面重新设计 (PR #61 拍板, 2026-07-21)

- **业务**: 视觉一致 + 键盘 accessibility + 状态反馈 (focus/hover/disabled)
- **CSS scope 修复 (PR #60 遗留)**: 去掉 `.tree-view` 前缀, `.pv-stepper` 通用
  - 5 个 PV input 位置 (skill/form/single/batch/skill batch) 全部生效
  - 之前 modal/form 内 stepper 失效 (按钮堆在下方)
- **UI design skill 应用** (Apple/Google/Stripe 风格):
  - focus 状态: input 边框变主色 #5AA4AE + box-shadow 0 0 0 2px (rgba 半透明)
  - invalid focus: 边框变 #EF4444 + box-shadow
  - hover 状态: row-input 边框略深 #B5C9CE (提示可交互)
  - focus-visible: 按钮键盘 focus 可见 (accessibility)
  - disabled 状态: #qaSubmit:disabled { opacity 0.5; cursor not-allowed }
  - 严格 8pt grid: 2/4/6/8/12/16/24 (CSS 间距 1px 边距用作绝对定位, 严格度低)
  - transition 0.12s (hover/focus 平滑)
- **设计 token**: 主色 #5AA4AE, 错误色 #EF4444, 边框色 #D1D5DB/#B5C9CE, hover bg #E5E7EB
- 改批量添加 UI 必查 §5.27 列出的所有引用点

### 2.8 +/- 位置互换 + 宋代配色 (PR #62 拍板, 2026-07-21)

- **业务 1**: + 在上, - 在下 (用户反馈, 跟 native number spinner 一致)
- **业务 2**: 应用宋代配色 (5 色 token)
- **+/- 位置互换**:
  - `.pv-step-btn.plus { top: 1px }` (在上, 跟 native 一致)
  - `.pv-step-btn.minus { bottom: 1px }` (在下)
  - 中间 border 1px 仍保留 (上下叠视觉)
- **宋代配色 (5 色 token)**:
  - `#5AA4AE` (天水碧, 主色) — submit bg, focus 边框, 加行 hover 实线
  - `#D6ECF0` (月白, 浅色) — input 边框, add-row-btn 虚线, cancel bg, +/- hover bg
  - `#758A99` (墨灰, 辅色) — +/- 按钮文字, 提示文字
  - `#F0C239` (缃色, 点缀) — 装饰色 token 备查
  - `#C0EBD7` (青白, 深色) — +/- active, row-del hover, cancel hover
- **设计 token 替换**:
  - input border: #D1D5DB → #D6ECF0 (月白)
  - +/- bg: #F9FAFB → #FFFFFF (跟 input 融合)
  - +/- hover: #E5E7EB → #D6ECF0 (月白)
  - +/- active: #D1D5DB → #C0EBD7 (青白)
  - +/- 文字: #6B7280 → #758A99 (墨灰)
  - cancel bg: #F3F4F6 → #D6ECF0 (月白)
  - cancel hover: #E5E7EB → #C0EBD7 (青白)
  - row-hint 文字: #9CA3AF → #758A99 (墨灰)
  - row-del hover bg: #FEF2F2 → #C0EBD7 (青白)
  - 警示色 (红 #EF4444) 保留 — 跨业务统一 error 状态
- **UI Design 原则 (宋代水墨)**: 主色+浅色+辅色+深色 4 层级, 中间点缀色 highlight
- 改 +/- 位置或配色必查 §5.28 列出的所有引用点

### 2.10 节点 own 不参与 commission 配对 + 5 子区 P/L 配对 (PR #68 拍板, 2026-07-27) — **翻案 PR #66 own-P 配对**

- **业务**: 用户截图 (2026-07-27) 反馈 A 节点显示 "本期可拿 ¥150", 用户说 "A 本期应该拿不到佣金, 因为他的 2 区还没有挂任何新成员"
- **PR #66 旧算法 (own-P 配对消耗, 错!)**:
  - `own_pair = MIN(own, P)` 让 own 跟 P 配对, own 算 commission
  - 业务验证: A (own=1500, 5 子区 C=1500) 旧算法 own_pair=1500, commission=150 — **错!**
- **PR #68 新算法 (own 不参与 commission 配对)**:
  - 节点 own PV **直接 carry, 不参与 commission 配对**
  - 5 子区 P/L 配对: `P = max(5 子区 c_pv_total 递归累加)`, `L = sum(其他 4 子区)`
  - `pair = MIN(P, L)`, `commission = pair × 15%`
  - own 100% carry 给节点自己 (不参与配对, 全 carry)
  - 父节点 P 剩 (p_pv - sub_pair) → P 子区根 carry (子节点, ADD 模式)
  - 父节点 L 剩 (各 L × (1 - sub_pair/L)) → L 子区根 carry (子节点, ADD 模式)
  - "子区总 PV" (return 第二值) = own + sum(子节点 c_pv_total) 递归累加 (PR #66 保留)
- **避免双计**: own carry 只非叶子写, 叶子 own 由父 p_remain 覆盖 (叶子 own = 父 p_remain 数值上相同, 不重复写)
- **业务场景验证 (ABCD 4 member 树, PV 1500/1000/1500/1000)**:
  - root: own=0, 5 子区递归 A 子区(3000) + B 子区(2000)
    P=3000, L=2000, pair=2000, commission=**300** ✓
    A carry = 1500 (own) + 1000 (根 p_remain) = 2500
    B carry = 1000 (own) + 0 (根 l_remain) = 1000
  - A: own=1500, 5 子区 C(1500) + 4 空
    P=1500, L=0, pair=0, commission=**0** ✓
    A carry = 1500 (own, 非叶子写) + 1000 (根 p_remain) = 2500
    C carry = 0 (own, 叶子不写) + 1500 (A p_remain) = 1500
  - B: own=1000, 5 子区 D(1000) + 4 空
    P=1000, L=0, pair=0, commission=**0** ✓
    B carry = 1000 (own) + 0 (根 l_remain) = 1000
    D carry = 0 (own, 叶子不写) + 1000 (B p_remain) = 1000
  - C/D: 叶子, own 不写 (避免跟父 p_remain 双计)
- **T5 测试兼容** (L2 own=100, 5 子区 L3=100 + L4=100):
  - 旧算法 own_pair=100, sub_pair=0, commission=15
  - 新算法 P=100, L=100, pair=100, commission=15
  - 数值碰巧一致 ✓
- **业务术语**: "1 区/2 区" = 父节点的 5 子区递归累加 (own 跟 commission 配对无关, own 是节点独立 ledger PV)
- 改算法或树形构造必查 §5.32 + §5.33 + §5.34 列出的所有引用点

### 2.11 团队培育奖金 (PR #69 拍板, 2026-07-27) + tooltip 文案改写

- **业务**: 用户截图 (2026-07-27) 反馈 tooltip 文案 + 加 团队培育奖金 字段
  > 用户原话: "看他的1区和2区是否是新增的成员, 假设1区（左支）新增成员with 1500PV,
  > 2区（右支）新增成员with 1000PV, 团队培育奖金=1500*30% + 1000*30% = 750"
- **新算法** (main.py._build_tree_from_db):
  - 1区 (左支) 新PV = 递归累加 slot 1 子树的 periodPv
  - 2区 (右支) 新PV = 递归累加 slot 2 子树的 periodPv
  - teamBonus = (1区 + 2区) × 30%
  - 只加到节点自己, 不分给祖先 (跟 7 层对等不同维度, 7 层对等是"节点 ownBasic 分给祖先", 团队培育是"节点培养下线奖励")
- **commissionPreview 公式变更**:
  - 旧 (PR #58-#68): ownBasic + pairBonus (7 层对等)
  - 新 (PR #69): ownBasic + pairBonus + teamBonus
- **Tooltip 文案变更** (用户截图反馈):
  - 旧: "本期可拿 (模拟) — own basic: ¥X + 7层对等 pair: ¥Y = ¥Z\n基于本期 periodPv 模拟, 跟 settle_period 规则一致"
  - 新: "本期可拿 — 基本佣金: ¥X + 对等奖金: ¥Y + 团队培育奖金: ¥Z = ¥W"
  - 旧文案移除: "（模拟）" / "own basic" / "7层对等 pair" / "基于本期 periodPv 模拟..." 句
  - 新文案使用: "基本佣金" / "对等奖金" / "团队培育奖金"
- **业务场景 (6 member 树, A=1500/B=1500/C=1000/D=1500/E=1200)**:
  - root: ownBasic 450 + pairBonus 22.5 + teamBonus 2010 = ¥2482.50
    (1区=A subtree=3700, 2区=B subtree=3000, 3700*0.3 + 3000*0.3 = 2010)
  - A: ownBasic 150 + pairBonus 0 + teamBonus 660 = ¥810
    (1区=C=1000, 2区=E=1200, 1000*0.3 + 1200*0.3 = 660)
  - B: ownBasic 0 + pairBonus 0 + teamBonus 450 = ¥450
    (1区=D=1500, 2区=空=0)
  - C/D/E: 叶子, teamBonus=0
- 改 tooltip / commission 公式必查 §5.34 列出的所有引用点

### 2.12 下单管理 (PR #70 拍板, 2026-07-27)

- **业务**: 用户 2026-07-27 截图反馈 "增加一个下单管理按钮, 里面是一张表, 显示了目前的库存和这次准备下单的数量, 单价, 可以把图里面的内容作为 Sample, 放到数据库表里面. 客户在增加购买的数量的时候, 也相应减少库存的数量, 并且同时计算出各项金额"
- **2 个新 endpoint**:
  - `GET /api/orders/items`: 列出所有产品 (按 sort_order 排序), 返 items + 实时算的 `unit_diff` + `total`
  - `PATCH /api/orders/items/bulk`: 批量更新, body `{items: [{id, required_qty?, current_stock?, package_count?, package_price?}, ...]}`, 一次提交所有改过的行
- **新表 `order_items`**: id, name (唯一), unit, required_qty, current_stock, package_count, package_price, sort_order, created_at, updated_at
- **业务规则 (PR #70 拍板)**:
  1. **单品差额 (unit_diff) = 当前库存 - 需求总数** (前端实时算, 不存 DB, 跟用户截图红色 -1 / -15 / -26 一致)
  2. **总金额 (total) = 套组 × 套组价格** (前端实时算, 不存 DB, 跟用户截图 1335 / 5645 / 7380 一致)
  3. **合计 = SUM(总金额)** = 35162 (8 个 sample 跟用户截图一致)
  4. **需求↑则当前库存按差量减少** (用户拍板): `库存_new = 库存_orig - (需求_new - 需求_orig)`
     - 公式的 `orig` 来自打开 modal 时的 server 值, 不是当前 input 值
     - 这样用户改 1 次或改多次, 库存都按"原始"算, 避免累计计算错误
     - 联动 `max(0, ...)` 兜底, 不让库存 < 0
  5. **显式「保存」按钮** (用户拍板): 改完手动点, 一次 PATCH 改过的行
     - 改过的行 `.modified` 边框 (淡蓝青色), "保存"按钮显示 dirty 行数
     - PATCH 发 4 字段: `required_qty` / `current_stock` (联动算的, 也存) / `package_count` / `package_price`
  6. **品名 (name) / 单位 (unit) 不允许改** (key, 改需要更复杂 UI, 当前 Pydantic schema 没暴露这 2 字段)
- **8 个 sample 产品** (用户截图, 拍板):
  | 品名 | 单位 | 需求总数 | 当前库存 | 单品差额 | 套组 | 套组价格 | 总金额 |
  |---|---|---|---|---|---|---|---|
  | 活性辅酶 | 瓶 | 18 | 17 | -1 | 1 | 1335 | 1335 |
  | 辅酶奥米加 | 瓶 | 15 | 0 | -15 | 5 | 1129 | 5645 |
  | 钙镁健骨 | 瓶 | 27 | 1 | -26 | 9 | 820 | 7380 |
  | 葡萄籽 | 瓶 | 26 | 0 | -26 | 9 | 899 | 8091 |
  | 超级水果素 | 瓶 | 2 | 0 | -2 | 1 | 1290 | 1290 |
  | 健儿素 | 瓶 | 13 | 0 | -13 | 5 | 766 | 3830 |
  | 田园果蔬饮 | 袋 | 11 | 0 | -11 | 4 | 1248 | 4992 |
  | 日夜纤 | 套 | 3 | 0 | -3 | 1 | 2599 | 2599 |
  | | | | | | | **合计:** | **35162** |
- **前端 UI**:
  - toolbar 加 "📋 下单管理" 按钮 (蓝青色渐变, 跟主色 settle 金 / 补录紫 / 重置红 区分)
  - modal: 8 列表格 (品名/单位/需求总数/当前库存/单品差额/套组/套组价格/总金额) + 合计行 tfoot
  - 改过的行 .modified (淡蓝青色边框 + 背景)
  - "保存" 按钮文字实时显示 dirty 行数 (e.g. "💾 保存 (1 行)")
- **关键决策**:
  - 需求↑库存↓联动**只在前端做** (后端只是 store): 后端 PATCH 时, 如果只发 `required_qty` 不发 `current_stock`, 库存保持原值
  - 这样业务不变式: 后端不"自作聪明"联动, 联动逻辑只在前端
  - 显式「保存」避免误操作: 客户改了一堆, 不点保存就关 modal, 全部丢失 (跟用户拍板一致)
- **跟 §11 UAT 规则一致**: 改完代码不主动重打 UAT.zip, 等用户指示 (e.g. "打包" / "重打" / "rebuild")
- **跟 §12 测试隔离一致**: 测试在 worktree 跑 + 复制 `data/` 从主仓, 不污染 live DB
- 改下单管理必查 §5.35 列出的所有引用点

### 2.10a 子区 PV 递归累加 (PR #66 拍板, 2026-07-23, **被 PR #68 翻案**)

- **业务**: 用户截图 (2026-07-23) 反馈 4 member 树 ABCD 算出 root own=150 PV, 期望 300 PV
- **原用户业务规则** (commit 时从用户反馈文字反推, 后来被 PR #68 翻案):
  - **节点 own 跟 5 子区中 P (max) 配对消耗**: `own_pair = MIN(own, P)`
    - own 是 L, P 是 P, MIN(own, P) = 配对消耗
  - **5 子区 P/L 配对消耗**: `sub_pair = MIN(P - own_pair, L_sum)`
  - **节点 commission = (own_pair + sub_pair) × 15%** (T5 测试兼容: own 配对也算 commission)
  - **own 剩 → 节点 carry, P 剩 → P 子区根 carry, L 剩 → L 子区根 carry (按比例)**
  - **子区总 PV (return 第二值) = own + sum(子节点 c_pv_total)** 递归累加 (PR #68 保留)
- **业务场景** (用户截图, 旧算法, 已翻案):
  - tree: root → A(L1) + B(L2), A → C(L1), B → D(L1)
  - PV: A=1500, B=1000, C=1500, D=1000
  - root: 1 区 = A 子区 = A own + C own = 3000, 2 区 = B 子区 = B own + D own = 2000
  - 配对 MIN(3000, 2000) = 2000, root own = 2000 × 15% = **300 PV** ✓ (翻案前后一致, root own=0 不参与配对)
- **关键修复**: `_build_settle_tree` 必须按 `parent_dist_id` 递归构造真 5 叉树, 不能把所有非 root member 当 root children
- 翻案原因: 用户 2026-07-27 反馈 "A 本期应该拿不到佣金", 业务规则反复推翻, "1 区/2 区" = 父 5 子区递归累加, own 跟 commission 配对无关
- 改算法或树形构造必查 §5.32 + §5.34 列出的所有引用点

### 2.9 UAT 清理 + 打包 + 客户文档 (PR #63 拍板, 2026-07-21)

- **业务**: 清理主仓无用文件 + 准备 UAT 客户包 + 写一份客户使用文档
- **清理 9 个文件** (净删 2083 行):
  - 历史脚本 (业务已迁): `tools/render_decision.py` / `commit_member.py` / `gen_dense_demo.py` / `init_tree_empty_5_3.py` / `_push_session_diff.py`
  - 早期文档: `skills/user_add_order_rule.md` (4 层二叉树, 跟 5 叉 9 层 commission 不对齐)
  - 缓存/备份/私人: `_commit_pr14.py` / `.env.MiniMax` / `json/Tree_empty_5_3.json.bak` / `json/fang.json` (148KB) / `uvi.*.log`
- **LLM 路由改 optional** (PR #63 业务决策):
  - 旧: `LLM_PROVIDERS` 默认 "deepseek", 未配 key 触发 `raise ValueError` hard fail
  - 新: `LLM_PROVIDERS` 默认 "", 未配时 graceful skip, commission 系统照常工作
  - chat 端点 (`/chat` `/sessions` `/v1/models`) 在 router 找不到 provider 时返回 503
  - 业务侧 (commission / 树视图 / 期间结算) **零影响**
- **启动脚本去 hardcode**:
  - `start_uvicorn.bat`: `cd /d %~dp0` 替代 `D:\Projects\Reward\RewardAgentAnalysis`
  - `tools/start_server.ps1`: `$PSScriptRoot\..` 替代 hardcode
  - 客户双击 / 任意路径启动都能跑
- **README 改写**:
  - 不再讲过时的 Stage 3 multi-skill 引擎
  - 主线业务: 5 叉树 9 层 commission 系统
  - 跟 CUSTOMER_GUIDE 明确分工: README = 技术开发, GUIDE = 客户使用
- **CUSTOMER_GUIDE.md (17KB) + CUSTOMER_GUIDE.html (28KB) — 客户文档**:
  - 9 章: 产品简介 / 5 分钟上手 / 核心功能 / 业务规则 / 角色 / FAQ / 备份 / 故障 / 反馈
  - 30+ 表格 + 16 FAQ
  - HTML 单文件: 宋代配色 (天水碧/墨灰/月白/青白) + 🖨️ 打印按钮 + @media print CSS
  - 客户可直接看 HTML, 也可浏览器打印导出 PDF
- **tools/build_uat_zip.py — 打包脚本** (新):
  - 排除: tests/ .git/ .worktrees/ .pytest_cache/ __pycache__/ .claude/ data/ uvi*.log .env
  - 输出: `outputs/RewardAgentAnalysis-UAT-v0.1.zip` (288KB, 29 文件)
  - 客户解压后 `pip install -r requirements.txt && python main.py` 启动
- **UAT 包内容**: 核心代码 (4 .py) + 启动 (3) + 算法 (skills/) + UI (static/) + 工具 (tools/) + 数据 (json/) + 文档 (README/GUIDE × 2/AGENTS) + LICENSE
- 改 LLM 路由 / 启动脚本 / 打包必查 §5.29 列出的所有引用点

---

## 3. 开发工作流

### 3.1 Worktree (强制)

**任何代码改动必须在 worktree, 禁止在主仓直接改**。`D:\Projects\Reward\RewardAgentAnalysis\` 是主仓, 永远保持 clean。

```powershell
cd D:\Projects\Reward\RewardAgentAnalysis
git worktree add -b feat-xxx .worktrees/feat-xxx main
# 复制 .env + json/
Copy-Item .env .worktrees\feat-xxx\.env -Force
New-Item -ItemType Directory -Path .worktrees\feat-xxx\json -Force
Copy-Item json\*.json .worktrees\feat-xxx\json\ -Force
# 复制 data/ (测 API 时用)
New-Item -ItemType Directory -Path .worktrees\feat-xxx\data -Force
Copy-Item data\rewarddb.db .worktrees\feat-xxx\data\rewarddb.db
```

**Worktree 内启动 server** (跟主仓 38080 端口不冲突):
```powershell
cd .worktrees\feat-xxx
python -c "from database import init_db; init_db()"   # 第一次跑, 后面不用
Start-Process python -ArgumentList "-m uvicorn main:app --port 8001 --log-level info" `
  -WorkingDirectory "$PWD" -RedirectStandardOutput "$env:TEMP\uvicorn_xxx.log" `
  -RedirectStandardError "$env:TEMP\uvicorn_xxx.err.log" -NoNewWindow
```

**Port 管理**:
- 主仓: 38080
- Worktree 测试: 38081-38088 (互不冲突, 同时跑多个 worktree)

**清理** (PR merge 后):
```powershell
# 1. 停 server
Get-NetTCPConnection -LocalPort 8001 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
# 2. 删 worktree
git worktree remove .worktrees/feat-xxx
# 3. 删 branch
git branch -d feat-xxx
```

### 3.2 Commit (中文 message)

**格式**: `type(scope): 中文一句话描述 — 可选细节`

**PowerShell + Git 中文 message 陷阱** (memory 里有):

| 症状 | 原因 | 解决 |
|---|---|---|
| `git commit -m "中文"` 多行触发 line-continuation | PowerShell 把 `\n` 当命令续行 | 用 `git commit -F file` |
| `git commit -F-` 收到 ?? | PowerShell pipe 把 UTF-8 当 GBK 解码 | 用 `Path.write_bytes(content.encode("utf-8"))` 写文件再 `-F file` |
| Write tool 写文件带 UTF-8 BOM | PowerShell `Set-Content` 默认 BOM | Python `Path.write_bytes` 无 BOM |
| stdout 显示 ??? | PowerShell 控制台 GBK | 验证 message 不要看 stdout, 看 git object |

**唯一稳的路** (Python script):
```python
import subprocess
from pathlib import Path
msg_path = Path(r"C:\Users\rainc\AppData\Local\Temp\commit_msg.txt")
msg_path.write_bytes(msg.encode("utf-8"))   # 无 BOM
subprocess.run(["git", "commit", "-F", str(msg_path)], cwd=WT)
```

**验证 message 真的写进了 commit object**:
```python
import zlib
sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=WT, capture_output=True, text=True).stdout.strip()
obj = WT / ".git" / "objects" / sha[:2] / sha[2:]
raw = zlib.decompress(obj.read_bytes())
# raw 格式: "tree xxx\nparent xxx\nauthor xxx\ncommitter xxx\n\nMESSAGE"
# 看 raw.split(b"\n\n", 1)[-1] 才是 message
```

### 3.3 Push + PR

**GitHub push 经常 connection reset** (memory 里有), 多次 retry + sleep 30s。

**gh pr create 多行 body** — 用 `--body-file` 不是 `--body` (空格会被当 unknown arg):
```powershell
gh pr create --base main --head feat-xxx `
  --title "fix(scope): 中文 title" `
  --body-file C:\Users\rainc\AppData\Local\Temp\pr_body.md
```

**Merge**:
```powershell
gh pr merge <num> --squash --delete-branch
# 删本地 branch 失败 (因为 worktree 还在) → 忽略, worktree 删后 branch 自然没了
git pull origin main  # main fast-forward
```

### 3.4 重启主仓 38080 server

PR merge 后必须重启主仓 38080 server 加载新代码:
```powershell
# 1. 停 38080
Get-NetTCPConnection -LocalPort 38080 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
Start-Sleep -Seconds 2
# 2. 启 38080
cd D:\Projects\Reward\RewardAgentAnalysis
Start-Process python -ArgumentList "-m uvicorn main:app --port 38080 --log-level info" `
  -WorkingDirectory "$PWD" -RedirectStandardOutput "$env:TEMP\uvicorn_main.log" `
  -RedirectStandardError "$env:TEMP\uvicorn_main.err.log" -NoNewWindow
Start-Sleep -Seconds 5
# 3. 验证
python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:38080/api/members', timeout=5).read()[:200])"
```

---

## 4. 测试工作流

### 4.1 pytest (PR 跑完必须 100% PASS, 除已知 fixture 问题)

```powershell
cd .worktrees/feat-xxx
python -m pytest tests/ -v
```

**已知问题** (跟代码逻辑无关, 别浪费时间 debug):
- `tests/test_write_to_disk.py` 9 个 ERROR — 依赖 gitignored 的 `json/Tree_empty_5_3.json` fixture
  - fixture 状态可能是空 5 叉 root, 测试期望 "init 5 个 L1 avail"
  - **跟新 PR 无关, 跳过**

### 4.2 Playwright 端到端 (改 static/index.html 必须跑)

**坑 (PR #23 教训)**: pytest 65/65 PASS + 后端 e2e 都没用, 改 `static/index.html` 删大段代码时残留 `*/` 语法错误 → JS parser 报 `Unexpected token '*'` → 整个 inline script 终止 → `showWelcome` 不执行 → welcome 屏 hidden 没被 remove。playwright 才能 catch 这个问题。

**Playwright 路径** (Node 25, chromium 1.61.0):
```
C:\Users\rainc\AppData\Roaming\npm\node_modules\playwright
```

**Playwright 验证脚本模板**:
```javascript
const { chromium } = require('C:\\Users\\rainc\\AppData\\Roaming\\npm\\node_modules\\playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
  await page.goto('http://127.0.0.1:8001/', { waitUntil: 'networkidle' });
  // 检查 welcome visible
  const welcomeVisible = await page.evaluate(() => {
    const el = document.getElementById('welcomeScreen');
    return el && el.offsetParent !== null ? 'visible' : 'hidden';
  });
  console.log('welcome:', welcomeVisible);
  // 点 welcome card 触发 quickMembers
  await page.evaluate(() => {
    const card = document.querySelector('.welcome-card[data-action="members"]');
    if (card) card.click();
  });
  await page.waitForTimeout(1500);
  // 检查 modal table
  const data = await page.evaluate(() => {
    const tables = document.querySelectorAll('.quick-modal-body table');
    if (!tables.length) return { found: false };
    const table = tables[0];
    return {
      headers: Array.from(table.querySelectorAll('thead th')).map(th => th.textContent.trim()),
      rowCount: table.querySelectorAll('tbody tr').length,
    };
  });
  console.log('table:', JSON.stringify(data));
  console.log('JS errors:', errs.length === 0 ? 'NONE' : errs.join('\n'));
  await page.screenshot({ path: 'C:\\Users\\rainc\\AppData\\Local\\Temp\\verify.png' });
  await browser.close();
})().catch(e => { console.error('FATAL:', e); process.exit(1); });
```

### 4.3 node --check 早期 catch syntax error

```powershell
node --check D:\Projects\Reward\RewardAgentAnalysis\static\index.html   # 不行, index.html 不是 .js
# 但可以提取 inline script 用 node --check, 或者直接靠 playwright
```

---

## 5. 代码踩过的坑 (从 PR #22-#28 总结)

### 5.1 渲染层跟算法层判定要保持一致 (PR #25 教训)

**根因**: PR #14 引入的 `_compute_effective_active_from_json` (main.py 渲染层) 用 `real_count > 0` 判定 line 满。PR #18 改成 `max_depth >= 9` 但渲染层没跟着改 → line 1+2 各 1 真实空子就升 eff=4 (跟业务规则不符)。

**修复**:
```python
FULL_LAYERS = 9  # 跟 skill_5_lib.py 一致

def _max_depth_in_subtree(node_dict):
    children = node_dict.get("children") or []
    if not children: return 0
    return 1 + max(_max_depth_in_subtree(c) for c in children)

def _is_line_filled(parent, line_id):
    for c in (parent.get("children") or []):
        if c.get("available") is True or c.get("avail") is True: continue
        try: lid = int(c.get("parentLineId") or 0)
        except: lid = 0
        if lid == line_id and _max_depth_in_subtree(c) >= FULL_LAYERS:
            return True
    return False
```

**Rule**: 任何业务规则 (line 满、eff、什么算"挂入"等), 渲染层跟算法层判定函数必须一致。
修改算法层时检查渲染层, 改渲染层时检查算法层。

### 5.2 API 字段名跟前端渲染字段名要对齐 (PR #26 教训)

**根因**: 后端 `api_members_list()` (PR #9) 返回 `member_dist_id/member_name/current_pv_balance`, 但 `quickMembers` 渲染用 `m.uid/m.name/m.pv/m.distId` (旧字段名) → 表格 9 行全显示 "-"。

**Rule**: 改 API 返回字段名时, 同步检查所有引用方 (前端/测试/其它 API), 用 grep 全局搜旧字段名。

### 5.3 改 static/index.html 必须 playwright 验证 (PR #24 教训)

见 §4.2。

### 5.4 删大段代码小心残留注释符号 (PR #24 教训)

**症状**: 删 `toggleCompactChildren` 函数时残留了多余 `*/` 闭合符号 + 空 `/** */` 块, JS parser 报 `Unexpected token '*'`, 整个 inline script 终止, welcome 屏 hidden 没被 remove。

**Rule**: 删函数 / CSS / 大段代码时, 用 grep 搜残留:
```powershell
Select-String -Path static\index.html -Pattern "^\s*\*/|^\s*/\*\*\s*\*/" 
```

### 5.5 写盘后给新成员 fill 5 个 avail placeholder (PR #19 教训)

**根因**: `commit_preview` 之前只构造 `children=[]`, 同 batch 内 step N+1 的 parent_dist_id=PREVIEW-N 找不到对应 avail 节点 (因为父是新加的 real, 没 avail 子)。

**修复**: `_replace_avail_with_real` 时 fill 5 个 avail placeholder children, 让同 batch step N+1 能挂入。

### 5.6 算法 stateless 遍历 (PR #22 教训)

**根因**: `find_next_slot_bitrev` 之前按 "step counter" 累加, 但 `commit_preview` 调一次是 stateless (不写盘), batch(1) 永远 step=0, 累积 tree 下 i 已经不是 0。

**修复**: 算法彻底 stateless, 遍历所有 (level, i) 按 base-N 严格按位反转顺序, 跳过 (父满 / col 已被占), 找第一个可挂入的 slot。

**Rule**: 涉及多 batch 累积 state 的算法, 必须能 stateless 兼容 (preview-only mode 是默认)。

### 5.7 `_preview_dist_id_map` (PR #19 教训)

PREVIEW-N → N-7XXXXXX 映射, 同 batch 内 step 共享。`api_skill_5_3_commit_preview` 维护这个 map, commit 阶段展开。

### 5.8 commit_preview 写盘是 optional, preview-only 是默认 (PR #8)

不写盘的 preview 用来预览, 写盘才是真挂入。

### 5.9 root 也要在 members 表 (PR #28)

`tools/init_root_member.py` 幂等 migration, 已存在跳过, 不存在 INSERT root 行 (distId=N5637590.1, name='王常军', parent=NULL, line=0)。

### 5.10 `import main` 陷阱 (debug 时)

Python `import main` 按 `sys.path` 顺序找, 默认优先主仓 `D:\Projects\Reward\RewardAgentAnalysis\main.py`。Worktree debug 时必须 `sys.path.insert(0, worktree_path)` 否则加载主仓代码。

Server 端用 uvicorn 跑的是 worktree 自己的 main.py (cd 到 worktree 后启动), 不会撞这个。

### 5.11 SQLite DB 路径 (data/rewarddb.db)

`data/rewarddb.db` 跟 `data/.gitkeep` 是 gitignored。Worktree 必须从主仓复制 (新 schema 时跑 `python -c "from database import init_db; init_db()"` 初始化)。

### 5.12 network: GitHub push 经常 connection reset

多次 retry + sleep 30s。`git ls-remote origin <branch>` 走 SSH/HTTPS 直接问 Git, 不走 API, 最准。

`https://api.github.com/repos/...` 公开匿名请求返回 404 (其实是 rate limit, GitHub 用 404 假装)。

### 5.13 PowerShell stdout GBK 问题

Python script 顶部加 `sys.stdout.reconfigure(encoding="utf-8")` 解决 (写文件用 `Path.write_bytes(content.encode("utf-8"))` + 验证 message 时不要 print, 看 git object)。

### 5.14 worktree .git objects 路径 (PR #44 教训)

worktree 的 `.git` 是 **file** (不是 directory), 内容是 `gitdir: <path>`, 指向 worktree-specific git dir (`主仓/.git/worktrees/<name>`)。这个 dir 里**不含** objects, 真正的 objects 在 `commondir` 文件指向的主仓 `.git/objects`。

**正确查 commit object 路径**:
```python
import os
from pathlib import Path
git_file = Path('.git').read_text().strip()  # "gitdir: D:/.../.git/worktrees/feat-xxx"
git_dir = Path(os.path.normpath(git_file.split(': ', 1)[1]))
commondir_rel = (git_dir / 'commondir').read_text().strip()  # "..\..\..\.."
commondir = (git_dir / commondir_rel).resolve()
obj_path = commondir / 'objects' / sha[:2] / sha[2:]
```

**Rule**: 任何"从 worktree 查 git object"的操作都用 `commondir` 路径, 不要直接 `Path('.git/objects/...')`。

### 5.15 PowerShell `python -c` 不要带 `{` `}` (PR #44 教训)

PowerShell 把 `{` `}` 当 shell 字符 (parse error 或当成 code block), inline `python -c` 写 f-string / dict / 集合字面量会炸。

**Rule**: 任何稍微复杂的 Python 代码, 写文件用 `Path.write_bytes(content.encode("utf-8"))` 然后 `python file.py`, 不要 `python -c "..."`。

### 5.16 CSS 字段验证: 历史注释 vs 实际 HTML 用法 (PR #44 教训)

删除/重构 CSS class 时, 验证 "class 已废弃" 不能用 `if 'class-name' in file: error`, 因为**注释里提到历史 class 名**也是合理 (e.g. "PR #41/42 用了 tv-role-row, PR #44 移到 line 1")。

**正确查 CSS 是否还有用**:
- HTML class: `re.search(r'class="tv-role-row|<div\s+class="tv-role-row|tv-role-row">', text)`
- CSS 规则: `re.search(r'\.tv-role-row\s*\{', text)` (只查 `{` 开头, 不查注释里 `tv-role-row` 字面量)

**Rule**: 删除/重构 class 时, 验证"实际 HTML/CSS 用法"才报错, 注释/历史文档里提到不算。

### 5.17 JS 函数看错参数: opts vs 第 1 参数 (PR #46 教训)

callback / helper 函数重构时, 容易把"原 opts 字段"当默认值留着, 但 caller 实际把数据放在第 1 参数里。

**根因 (PR #46)**: `quickMountAndCommit(members, modal, opts = {})` 内部用 `opts.members[idx].role` 拿角色。
  - `quickAddMember` 调 `quickMountAndCommit([{name,pv,role}], modal)` — role 在第 1 参数 members
  - `opts` 默认 `{}` → `opts.members` undefined → 永远兜底 `'消费股东'` → 角色选择失效

**Rule**: callback/helper 函数, 改字段来源时 (e.g. opts.members → members), 验证所有 caller 调用点 (3 个: quickAddMember / quickBatchAdd / /add slash command) 都对应改对。`opts.xxx` 是约定的"可选 context" — 改这个约定, 必查所有 caller。

### 5.18 distId 格式改 `N5637590.X` 后 `_member_to_uid` 必须同步改 (PR #50 教训)

**根因**: `_build_node5_tree_from_db` 用 `_member_to_uid(m)` 把 `member_dist_id` 转成 `Node5.uid` (int)。
  - 旧实现: `lstrip("N").split(".")[0]` → 对 `"N5637590.1"` 解析成 `5637590` (丢 .X)
  - 所有 `N5637590.X` 节点 uid 都是 `5637590`, **跟 root 同 uid** → 算法 BFS `_bfs_find_nth_parent` 索引错乱
  - 4 成员 batch 全部挂同一槽位 (e.g. root L1) → commit_preview 报 "挂入点 #3 跟 #1 同 batch 同一槽位"

**修复**: 解析按格式分桶:
  ```python
  if did.startswith("N5637590."):
      return 5637590 * 100_000_000 + int(did.split(".", 1)[1])  # 唯一大整数
  if did.startswith("N-7"):
      return -int(did[3:])  # 旧格式, 跟 root 区分 (负数)
  ```

**Rule**: 改 distId 格式 (eg N-7XXXXXX → N5637590.X) 时, **必查所有用 distId 解析 uid 的地方**:
  - `_build_node5_tree_from_db._member_to_uid` (算法层)
  - `_compute_max_synthetic_dist_id_from_db` regex (start_rank 计算)
  - commit_preview 分配新 distId 逻辑
  - test setUp 清数据时 `like()` 模式
  - test 解析 distId 尾号的 `split("-")` / `split(".")` 都要更新

### 5.19 commit_preview 起点必须跟 preview start_rank 同号 (PR #50 教训)

**根因**: preview 算 `start_rank = _compute_max_synthetic_dist_id_from_db`, 给 `PREVIEW-N = step + start_rank + 1`。
  - commit_preview 旧实现: 用同样的 `_compute_max_synthetic_dist_id_from_db` 算 `max_dist`, 给 `N5637590.X = max_dist + i + 1`
  - preview 跟 commit 各自用 DB.max 算, 写盘后 DB.max 增加, **下次 preview start_rank 同步增长**
  - 结果: distId 尾号 +2 跳号 (.3, .5, .7) 而非 +1 连续 (.2, .3, .4)

**修复**: commit_preview **直接用 history 里的 PREVIEW-N 编号** 作为 N5637590.N:
  ```python
  if h.member_dist_id.startswith("PREVIEW-"):
      _n = int(h.member_dist_id[8:])  # 2, 3, 4, ...
      new_dist_id = f"N5637590.{_n}"  # 跟 preview 同号
  ```
  - preview 跟 commit 用同一 N 号计数器, 写盘后 DB.max 增加, 下次 preview start_rank 同步 +1
  - 多次循环: 严格 +1 连续 (.2, .3, .4, .5)

**Rule**: preview 是 stateless 计算, commit 是 stateful 写盘。**两者用同一编号计数器**才能保证 distId 连续且 unique。
  - 旧 PR #39 时代 preview 跟 commit 都用 DB.max, 是因为 commit 之前 preview 不写盘, 两者读同一 DB 状态
  - 改 distId 格式 / 改算法后, 必须验证 preview.start_rank == commit.next_dist_id

### 5.20 测试 setUp 已清 root 时, 测试内别再二次清 (PR #50 教训)

**根因**: `test_commit_batch_nested_mount_writes_all` (PR #45 加) 内手动 `db.query(Member).filter(Member.member_dist_id.like("N5637590.%")).delete()`
  - setUp 已经清空 N-7* + N5637590.* + seed root
  - 测试内二次清 = 把 root 也删了 → preview fallback 给虚拟 root distId `N5637590.1`
  - commit_preview 找不到 root → 400 "在 DB 中找不到父成员"
  - 但这个错误跟用户反馈的 "parent=N5637590.1 L1 找不到" **完全一致** → 排查时一度以为是 commit_preview bug

**修复**: setUp 已经是单数据源, 测试内不再二次清。如果一定要清, 用 `Member.member_dist_id != "N5637590.1"` 排除 root。

**Rule**: setUp 已经设了"干净 + seed 根"的状态, **测试内不要再 reset**。要 reset 时精确排除 seed 的 row (e.g. `Member.member_dist_id != ROOT_DIST_ID`)。

### 5.21 本期 PV 徽章跟 period.status 联动 (PR #54 v2 教训)

**根因**: PR #51 加 "本期 PV" 徽章, PR #54 v1 加 "剩余 PV" 徽章,设计成"两个独立字段并排显示"。
但 PR #54 v1 没考虑一个关键点: **本期 PV 徽章的语义只在 period.status=open 时有效**。

- 业务规则: "本期 X PV" 表示 "本期新注入多少 PV" — 业务语义只对**未结算期**有意义
- 结算后 (period.status=settled): 本期 PV 已经**全部落账**到 carry / commission
  - 一部分配对消耗 (→ commission 给父节点)
  - 一部分 carry 余额 (→ current_pv_balance)
  - 这些数据已经反映在 "剩余 PV" 徽章上了
  - 这时再显示 "本期 500 PV" 是**重复且语义混乱**的 — 用户感觉是"已结算的还显示"

**用户反馈 (2026-07-17)**:
> "点击结算本周后, 张a 的'本期500PV'这个位置应该变成显示'剩余200PV' (500-300), 张b 变成'剩余0'"

**修复 (v2 互斥)**: 同一节点同一位置, 本期 vs 剩余 二选一
  - `period.status = open`: 显示 "本期 X PV" (绿)
    + 跨期 carry > 0 时**同时**显示 "剩余 Y PV" (黄) — 两个语义不冲突
  - `period.status = settled`: **隐藏** "本期 PV" 徽章
    + 跨期 carry > 0 时显示 "剩余 Y PV" (黄)
  - 不存在 (新期, 没在 commission_periods): 默认 status=open
  - 0 都不显示 (沿用 PR #54 v1 规则)

**实现**:
1. `_build_tree_from_db` 查 `commission_periods WHERE id=current_period`, 注入 `currentPeriodStatus` 到每个节点
2. `_tree_render_node` 加条件 `currentPeriodStatus == "open"` 才渲染本期 PV 徽章
3. 测试 setUp 加 `db.query(CommissionPeriod).delete()` (之前没清, 残留行污染)

**Rule**: 任何"按期聚合"的字段 (本期 PV、本期 commission、本周统计), 渲染时**必须看 period.status**。
  - period.status=settled 的字段, 业务上已经从"活动态"变成"历史态"
  - 历史态数据要不就改用不同字段 (e.g. "已结算"标签), 要不直接隐藏
  - **不能**默认"按 DB 聚合"就显示 — 业务语义跟 period 状态强相关

### 5.22 业务周 (Sun-Fri) + 补录窗口 (PR #55 教训)

**根因 (PR #55 业务规则变更)**: 之前周期定义是 ISO 周 (Mon-Sun, 7 天), settle 之后永久 settled 没有补录窗口。
用户 (2026-07-20) 拍板新业务规则:
  - 正常周期: Sun 00:00 → Fri 23:59:59.999 (6 天)
  - 补录窗口: Sat 00:00 → Mon 23:59:59.999 (3 天, "下班前" = Mon 23:59)
  - 补录 commission: 只能补基本, 对等链已冻结

**踩坑 1: 业务 W 编号跟 ISO W 编号不对齐**
  - 业务 W29 范围 (2026-07-12 Sun ~ 2026-07-17 Fri) ≠ ISO W29 (2026-07-13 Mon ~ 2026-07-19 Sun)
  - 业务 W29 跨 ISO W28 (Sun) + ISO W29 (Mon-Fri)
  - 业务 W 编号沿用 ISO W 编号 (数字保持), 但范围是 Sun-Fri
  - 例: ISO W30 (Mon 2026-07-20 ~ Sun 2026-07-26) → 业务 W30 (Sun 2026-07-19 ~ Fri 2026-07-24)
  - **不要假设业务 W 跟 ISO W 范围一致** — migrate 函数跟 get_current_period_id 实现要分开

**踩坑 2: get_supplement_range 算 Sat 错位 (Sun + 5 = Fri, 应该是 + 6 = Sat)**
  - 第一次实现: `sat_dt = Sun + 5 days` → Sat 算成 Fri (错)
  - 实际: `sat_dt = Sun + 6 days` (因为 Sun=0, Mon=1, ..., Sat=6, Sun+6 = Sat)
  - 验证: W29 范围 7-12~7-17, 补录应该是 7-18~7-20, 不是 7-17~7-19
  - 修复后: supplement_until_ts 算到 Mon 23:59:59.999, 跟业务规则 "下班前" 对齐

**踩坑 3: 业务周期 ID 跨日切换要按 (weekday + 1) % 7 算**
  - 旧实现用 if-elif 分支: Sun / Sat / Mon / Tue-Fri, 4 个分支
  - Sat 分支用 `today - 1` 算 (错, Sat - 1 = Fri 不是 Sun)
  - 正确公式: `start = today - timedelta(days=(weekday + 1) % 7)`
    - Sun (6): (6+1)%7 = 0 → today (今天就是 Sun)
    - Mon (0): (0+1)%7 = 1 → today - 1 (昨天是 Sun)
    - Sat (5): (5+1)%7 = 6 → today - 6 (上周日)
  - 公式统一, 不容易出 bug

**踩坑 4: period.status 跟 phase 是两个维度**
  - `status`: 业务状态 (open / settled / closed), 跟 settle 操作绑定
  - `phase`: 时间阶段 (open / supplement / closed), 跟当前时间绑定
  - 业务逻辑:
    - 补录按钮显示条件: `phase=supplement` AND `status=settled` AND `can_supp=true`
    - 已结算灰态: `phase=closed` OR `status in (settled, closed)` (除了 supplement 期)
  - 补录 API 验证: `status='settled'` AND `now_ts < supplement_until_ts`
  - 主 settle API 验证: `status NOT IN ('settled', 'closed')`

**踩坑 5: 补录只算 own_commission, 跳过 pairing_bonus**
  - 业务规则: 补录期间对等链已冻结, 不能再分润
  - settle_period(..., supplement_only=True) 跳过 `_apply_pairing_bonus`
  - `_write_settle_result` 也跳过 `ancestor_share_by_dist` 累加
  - 测试设计: 至少 2 个 child 才能触发配对 (P vs L, 单 child pair=0 commission=0)

**踩坑 6: 周期 ID 解析要严格, 不要 silent 兼容旧格式**
  - `_parse_period_id` 直接拒 "2026-W29" 旧格式
  - API 收到旧格式会 422 (Pydantic validation) 或 ValueError
  - migration 脚本负责一次性转换, 之后 strict
  - 业务规则: 业务 ID 严格 "YYYY-MM-DD_Www" 格式, 数字保持 ISO W

**踩坑 7: migration 收集旧 period_id 要包括 members 表**
  - 第一次 migration 只从 pv_ledger 收集旧 ID, 漏掉 members.created_period_id / last_period_id
  - 测试 fixture 直接 hardcode period_id='2026-W28' 给某些 member, ledger 里没这个 period
  - 修复: 收集来源扩到 pv_ledger + members.created_period_id + members.last_period_id
  - re-run 验证: migration 第二次跑 periods_migrated=0, 旧 ID 残留 [OK] 无

**Rule**: 业务规则变更 (周期定义/范围/状态) 时, 必查所有 "按期聚合" 的字段 + 所有 hardcode period_id 的代码位置 (包括测试 fixture)。migration 工具要覆盖所有出现旧 ID 的表。

### 5.23 批量重置测试数据 (PR #56 教训)

**根因 (PR #56 业务需求)**: 用户 (2026-07-20) 反馈 "节点加太多了很难算清楚, 帮我增加一个批量删除功能"。
测试期间反复加成员试算法, 节点爆满, 需要一个"一键回到初始状态"的功能。

**踩坑 1: 删除顺序要按 FK 引用顺序, 否则约束冲突**
  - pv_ledger 有 FK 引用 members (ON DELETE CASCADE, SQLite 强制)
  - 业务上保留 root 不删, 所以不能直接靠 CASCADE
  - 正确顺序:
    1. 先全清 pv_ledger (不依赖 members)
    2. 再删 members WHERE id != root_id (root 保留)
    3. 最后清 commission_periods (无 FK 引用 members)
  - 反过来删: commission_periods → members → pv_ledger 会卡在 "删 root 时 root 还有 ledger 引用"

**踩坑 2: root 必须保留, 但字段要重置**
  - 业务: 重置 = "回到 DB 刚建好状态", 包括 root 干净 (carry=0, commission=0)
  - 旧实现只删非 root, root 字段不变 → 测试 999 commission 还在
  - 修复: 删非 root 前先 `root.current_pv_balance = 0; root.total_commission = 0; root.last_period_id = None`
  - root 字段中 `created_period_id` 保留 (历史信息, 不重置)

**踩坑 3: 极端情况 — root 也不在 DB**
  - 旧代码: 如果 root 不存在 (DB 异常), 全删后没有 root
  - 修复: 检测 root_preserved, 缺失时自动 INSERT 一行 (idempotent, 跟 tools/init_root_member.py 一致)
  - 测试 `test_reset_rebuilds_root_if_missing` 覆盖

**踩坑 4: confirm 参数防误点 (PR-A 教训延伸)**
  - 业务: 重置是不可逆操作, API 必须 confirm=true 才执行
  - UI: 二次确认 (浏览器 `confirm()` 弹窗, 列出将删/将保留的项)
  - 测试: confirm=false 返回 400, 数据未变
  - Rule: 任何 destructive API 都默认 confirm=false, 防止误点

**踩坑 5: 测试 fixture 不能让根节点缺 (跟 PR #20 教训一致)**
  - `setUp` 已经 seed root, 测试内不再二次清 (PR #20 规则)
  - 如果测试需要测 "root 缺失" 场景, 在测试内显式 `db.query(Member).filter(Member.member_dist_id == "N5637590.1").delete()`
  - 避免 setUp 跟测试函数状态错位

**Rule**: 批量 destructive API 设计原则:
  1. 默认 confirm=false (防误点)
  2. UI 二次确认 (列出影响范围)
  3. 删除顺序按 FK 引用 (避免约束冲突)
  4. 保护核心数据 (root 不删, 字段重置)
  5. 返回详细 stats (UI 展示用户做了啥)

### 5.24 批量添加表格化 (PR #57 教训)

**根因 (PR #57 业务需求)**: 用户 (2026-07-21) 反馈 "这里需要增加一个角色选择, 是消费股东, 还是初级合伙人等"。
旧批量添加用 textarea 输 `张三 500\n张四 600`, 不能选角色; 选角色要么单加 (慢), 要么提前给默认角色 (不灵活)。

**设计取舍**:
- 方案 1 (textarea 扩展): 2 分 — 跟用户心智不匹配, 角色解析逻辑复杂
- 方案 2 (顶部默认角色): 3 分 — 部分成员用默认, 部分单独指定, 反而更乱
- **方案 3 (表格化, 全部用表格输入): 5 分 ⭐** — 每行独立选, 清晰直观
- 方案 4 (双模式): 1 分 — 复杂度爆炸, 用户认知负担重

**踩坑 1: 不用"本批默认角色"工具栏**
  - 用户原话: "我倾向于方案3。但不需要'本批默认角色'。全部用表格输入"
  - 工具栏的"本批默认角色"看似省事, 实际让用户**2 个心智模型**:
    - "我只填姓名/PV, 角色用默认"
    - "我填 3 行, 第 1 行改下拉"
  - 统一"全部用表格输入" → 1 个心智模型, 反而更简单
  - 4 列 (姓名/PV/角色/删除) 是最小完整单位, 不需要"本批"这个中间状态

**踩坑 2: CSS 8pt grid 步进**
  - ui-design skill 要求 padding/margin 步进 (2/4/8/12/16/24px)
  - 旧实现 `.role-batch-table td { padding: 5px 4px; }` → 5px 不是 2 倍数, 测试失败
  - 修复: `padding: 4px 4px;` (4 是 2 倍数, 视觉上跟 5px 几乎无差)
  - **Rule**: 表格/表单间距 2 倍数步进 (允许 2/4/6/8/10/12/16/24px), border-radius 可以 5/6px (视觉细节, 严格度低)

**踩坑 3: 测试查"无 .value.trim()"误伤**
  - 旧测试 `assertNotIn(".value.trim()", body)` 误伤
  - body 里 `_countValidRows` 等地方用 `.value.trim()` 读 row-name 的值是合理的
  - 修复: 改用更精确的 regex 查"旧 textarea 模式":
    - `assertNotRegex(body, r"const\s+text\s*=.*\.value", ...)` — 旧 "const text = ... .value" textarea 模式
    - `assertNotIn("parseBatchInput(", body)` — 旧 parseBatchInput 函数
  - **Rule**: 测试查"无 X"时, X 应该是**特异性**的旧模式, 不应该是**通用**API (e.g. `.value.trim()` 是通用 API, 不能禁)

**踩坑 4: 严格空行校验 vs 宽松跳过**
  - 旧实现: 空行直接跳过 (`if (!name && !pvRaw) return;` 静默)
  - 用户 (测试场景) 期望: 姓名空 / PV 非数字 → **红框 + 报错** (因为是误输入, 不是"不想填")
  - 修复: 空行跳过; 但**有部分输入**(姓名空 / PV 非数字) → 报红框 + 错误, 阻止提交
  - 业务: 用户填了一半想保存, 漏了某个字段 → 系统告诉他哪个字段漏了 (而不是静默丢)

**踩坑 5: 角色下拉沿用现有 `role-dropdown` 样式**
  - 单加 `quickAddMember` 已经用了 `role-dropdown` 样式 (PR #42)
  - 批量加也用同一样式 → 视觉一致, 不增加新 CSS
  - 角色下拉里加圆点色块 (data-bg/data-fg) → 跟单加一致, 角色颜色 = 名片 role 颜色
  - **Rule**: 新 UI 组件沿用现有样式, 不重复发明

**踩坑 6: Tab 跳列用浏览器默认, 不劫持**
  - 旧实现: 自己监听 Tab 键, 切到下一个 input
  - 问题: 自己维护焦点循环容易出 bug (跳过头, 跳到非 input 元素)
  - 修复: 用浏览器默认 Tab 行为 (input 元素自动 focus 下一个), 不劫持
  - **Rule**: 浏览器默认行为能用就用, 不重写 (避免引入新 bug)

**踩坑 7: 提交按钮文字实时显示有效行数**
  - 业务: 用户填了 3 行但只 2 行有完整输入 → 按钮显示 "批量挂入并写盘 (2 位)"
  - 实现: `tbody.addEventListener('input', ...)` → 触发 `_refreshSubmitLabel()` → 更新 `submitBtn.textContent`
  - 避免: 用户提交时才发现"诶, 怎么只加了 2 个"
  - **Rule**: 任何"按 N 个 X 提交"的 UI, 提交按钮文字应该实时显示 N, 反馈用户当前状态

**Rule**: 批量添加 UI 设计原则:
  1. **表格化代替 textarea** — 每行结构化, 字段可独立校验
  2. **不用"本批默认"中间状态** — 全部用表格输入, 心智模型统一
  3. **每行独立下拉/校验/删除** — 避免"全局默认 + 局部覆盖"复杂度
  4. **严格校验 + 红框反馈** — 错的地方高亮, 阻止提交
  5. **提交按钮实时显示有效行数** — 用户随时知道会提交几个
  6. **键盘友好** — Tab 跳列 / Enter 加行/提交
  7. **沿用现有样式** — `role-dropdown` 跟单加一致, 视觉统一

### 5.25 父节点 commission preview (PR #58 教训)

**根因 (PR #58 业务需求)**: 用户 (2026-07-21) 反馈 "本期金额出现后, 应该同时模拟算出基本佣金, 对等佣金等值, 显示在父节点上。目前王常军的名片上没有显示。"

**踩坑 1: 旧 commission 用 `pv` (剩余) 而不是 `periodPv` (本期)**
  - 旧实现: `_tv_sub_pvs` 用 `children[].pv` (跨期 carry, 本期未 settle 时 = 0)
  - 业务: 本期未 settle 时 pv=0 → commission=0 → 徽章不显示
  - 用户反馈: "王常军的名片上没有显示"
  - 修复: 用 `children[].periodPv` (本期新增 PV) 算 ownBasic, 同时累加 7 层 pairBonus
  - **Rule**: 任何"按期聚合"的字段 (commission / 配对奖 / 总值), 实时 preview 必须用**本期 PV** (`periodPv`), 不是跨期 carry (`pv`)

**踩坑 2: 7 层对等需要前序遍历, 不是后序**
  - 业务: 父节点的 pairBonus = 7 层对等, 每个子孙节点的 ownBasic × ratio 累加
  - 旧实现: 用后序遍历, 但 7 层对等是**每个节点的 ownBasic** 分给祖先, 不是 commissionPreview
  - 修复: 前序遍历, ancestor_nodes 传 [父, 祖父, ..., 7代祖先]
    - 对每个 ancestor, `ancestor.commissionPreview += node.ownBasic × ratio[depth]`
  - **Rule**: 7 层对等是**节点 own** 分给祖先, 不是节点的 commissionPreview (own+pair) 分给祖先

**踩坑 3: 视觉分级 — 紫色区分"模拟"和"实际"**
  - 业务: 4 个 commission/数值相关徽章 — 本期 PV (绿), 剩余 PV (黄), 累计 $ (金), 本期可拿 (本期 commission 模拟)
  - 设计: 用**紫色 #6D28D9** 区分"模拟", 暗示"未来/预测"
  - 不用紫色 → 跟"累计 $" 金色混淆, 用户分不清"现在能拿"和"历史拿了"
  - **Rule**: 业务数值的**模拟 vs 实际**必须视觉区分 (颜色/边框/前缀), 用户一眼能分辨

**踩坑 4: 紫色 CSS 间距严格 2 倍数 (8pt grid)**
  - 业务: 紫色徽章 `padding: 1px 6px` 看起来跟旧金色一样, 视觉一致
  - 8pt grid 测试: 1px 不是 2 倍数, 失败
  - 修复: `padding: 2px 6px` (视觉几乎无差, 2 倍数合规)
  - **Rule**: 任何新加 CSS 必须走 8pt grid (2/4/6/8/12/16/24px), 不要凭感觉写 1px/3px/5px
  - 旧 `.tv-commission` (金色, 1px) 保留是历史遗留, 新加的 `.tv-commission-preview` 必须严格

**踩坑 5: settled 期徽章必须隐藏**
  - 业务: settled 期 PV 已落账到 carry / commission, 业务上不再是"活动态"
  - 旧实现: period.status=settled 时 commissionPreview 字段还是算出来, 但徽章不显示
  - 修复: 渲染时检查 `currentPeriodStatus == "open"`, 不显示徽章
  - **Rule**: 任何"按期聚合"的模拟字段, 渲染时**必须看 period.status** — settled 期算"历史态", 不应该再显示 preview
  - 跟 PR #54 v2 教训一致: 本期 PV vs 剩余 PV 互斥, settled 期隐藏本期 PV

**踩坑 6: tooltip 必须分解 own + pair, 不能只给总值**
  - 业务: "基本佣金, 对等佣金等值" — 用户想看到 own 和 pair 各自值, 不只是总和
  - 旧实现 (没有): 只显示 commission 单值
  - 修复: tooltip 写 `own basic: ¥X + 7层对等 pair: ¥Y = ¥Z\n基于本期 periodPv 模拟, 跟 settle_period 规则一致`
  - **Rule**: 任何"组合值"徽章 (own+pair / 本期+累计 / 当前+预测), tooltip 一定要分解, 让用户看到组成

**Rule**: commission preview 设计原则:
  1. **用 periodPv 算, 不是 pv** — 本期视角, 实时模拟
  2. **7 层对等用前序遍历** — 节点 ownBasic 分给祖先
  3. **紫色区分"模拟"** — 跟"实际累计" 视觉分级
  4. **CSS 严格 8pt grid** — 间距 2 倍数步进
  5. **settled 期隐藏徽章** — 跟"本期 PV"互斥 (PR #54 v2 一致)
  6. **tooltip 分解 own + pair** — 让用户看到组成, 不只是总值
  7. **跟 settle_period 规则一致** — 复用 `PAIRING_BONUS_RATIOS` / `PAIRING_BONUS_MAX_DEPTH`

### 5.26 PV 输入框自由输入 (PR #59 教训)

**根因 (PR #59 业务需求)**: 用户 (2026-07-21) 反馈 "PV 值每次增加或者减少都是以 100 的整数倍。如果要输入小于 100 的数字, 可以自己输入。"

旧实现 5 个 PV input 用 `type="number" min="1" step="1"`, 浏览器 spinner 跳 100 倍数, 用户体验差。

**踩坑 1: `<input type="number">` spinner 行为不可控**
  - 业务: 浏览器 number input 的 spinner (上下箭头) 在某些场景跳 100 倍数, 跟 `step` 属性不一致
  - 实际: 即使 `min="1" step="1"`, 某些浏览器 / 操作系统 / 输入法下 spinner 行为跳大数
  - 修复: 改 `type="text"`, 彻底去掉 spinner, 自由输入任意正整数
  - **Rule**: 数字输入框 (业务上需要任意正整数) 不要用 `type="number"`, 用 `type="text" inputmode="numeric" pattern="[0-9]+"`, 自由 + 移动端数字键盘

**踩坑 2: 移动端数字键盘 vs 自由输入**
  - 业务: 改 `type="text"` 后, 移动端不再自动弹数字键盘
  - 修复: 加 `inputmode="numeric"`, 移动端仍是数字键盘, 桌面端无副作用
  - **Rule**: 数字输入 `type="text"` 时, 必加 `inputmode="numeric"` (兼容移动端)

**踩坑 3: HTML5 验证不能少**
  - 业务: `type="text"` 没了浏览器内置的 min/max 验证
  - 修复: 加 `pattern="[0-9]+"` (HTML5 验证整数), 表单提交时浏览器会校验
  - JS 仍 `parseInt` + `isNaN` 校验 (PR #57 已有)
  - **Rule**: 数字 text input 必加 `pattern="[0-9]+"` (HTML5 验证) + JS parseInt 校验 (双保险)

**踩坑 4: 5 个 input 位置要全找到**
  - 业务: 5 个 PV input 在不同 modal / form 里, 改一个忘一个
  - 列表 (避免漏改):
    1. `id="skillPvInput"` (skill modal)
    2. `name="pv"` (tvCompactForm, value=1000 default)
    3. `id="qaPv"` (单加成员)
    4. `class="row-input row-pv"` (批量添加 row, 用户截图)
    5. `class="batch-pv"` (skill 批量)
  - **Rule**: 改 PV input 前用 grep 全搜 `type="number"`, 列清单, 5 个全改, 测试全验

**踩坑 5: CSS `input[type="number"]` 选择器保留**
  - 业务: 2 处 CSS 用 `input[type="number"]` 选择器 (`.quick-modal-body` / `#skillModal`)
  - 修复: 保留 CSS 选择器, 兼容未来可能用 `type="number"` 的 input
  - 业务: text input 也匹配不上, 无副作用
  - **Rule**: 改 input type 不动 CSS 选择器 (兼容未来), 测试用具体类型断言

**Rule**: PV 数字输入设计原则:
  1. **用 `type="text" inputmode="numeric"`** — 自由输入, 移动端数字键盘
  2. **加 `pattern="[0-9]+"`** — HTML5 验证整数
  3. **JS `parseInt` + `isNaN` 校验** — 业务层兜底
  4. **5 个 input 全改** — grep 搜 `type="number"`, 列清单, 不漏改
  5. **CSS 兼容** — 保留 `input[type="number"]` 选择器, 不影响现有样式
  6. **Playwright 验证 < 100 数字能输入** — e.g. z9 PV=1 提交成功
  7. **PR #60 (增强)**: 自定义 +/- 按钮 (跳 100), 跟 native number spinner 视觉一致
     - `.pv-stepper` wrapper: input + 2 按钮 (上下叠, 右侧内嵌)
     - 按钮 click: 读 input 当前值 ± 100, 触发 input 事件
     - < 0 clamp (业务: PV >= 0)
     - MutationObserver 监听新 stepper (e.g. quickBatchAdd 加新行)

### 5.27 批量添加页面 CSS scope + 设计 (PR #61 教训)

**根因 (PR #61 业务需求)**: 用户 (2026-07-21) 反馈 "可以把这个页面再设计一下" /ui-design。
实际: PR #60 加 +/- spinner 按钮, 但 CSS 用 `.tree-view` scope, modal/form 内不生效 (按钮堆在 input 下方)。

**踩坑 1: CSS scope `.tree-view` 前缀限制**
  - 业务: `.pv-stepper` 写在 `.tree-view` scope 下, 只在 tree-view 容器内生效
  - 实际: 批量添加 modal 在 `.quick-modal-body` 内, form 在 `.tv-compact-modal-form` 内, skill modal 在 `#skillModal` 内 — **都不在 `.tree-view` 内**
  - 浏览器 fallback 到 `position: static`, +/- 按钮堆在 input 下方
  - 修复: 去掉 `.tree-view` 前缀, 通用 `.pv-stepper` (modal/form/skill 都生效)
  - **Rule**: 任何"通用 UI 组件" CSS 不要带容器 scope (e.g. `.tree-view`), 写在最高层 (裸 `.pv-stepper`)

**踩坑 2: focus 状态视觉反馈**
  - 业务: 键盘用户 tab 到 input 时, 应该看到清晰的 focus 边框 (accessibility)
  - 旧实现: input 默认 focus 用浏览器原生 outline, 跟主色 #5AA4AE 不一致
  - 修复: 自定义 focus state, 边框 #5AA4AE + box-shadow 0 0 0 2px (rgba 半透明)
  - **Rule**: 任何 input focus 都应该用主色 (跟品牌一致), 加 box-shadow 视觉强化 (不只是边框颜色)

**踩坑 3: hover 状态不能跟 focus 冲突**
  - 业务: hover 边框 #B5C9CE (略深) 提示可交互, 但 focus 时不应该叠加
  - 修复: `hover:not(:focus)` — 只有当 input 没 focus 时, hover 才生效
  - **Rule**: hover 状态用 `:not(:focus)` 排除, 避免 focus 时叠加 hover 效果

**踩坑 4: focus-visible vs focus**
  - 业务: 鼠标点击不应该显示 focus outline (用户没要 focus), 但键盘 tab 应该
  - 修复: 用 `:focus-visible` 而不是 `:focus`, 浏览器自动判断 (鼠标 vs 键盘)
  - **Rule**: 按钮 (尤其是 icon button) 用 `:focus-visible`, 不要用 `:focus`, 避免鼠标点击后留下 outline

**踩坑 5: 严格 8pt grid 不能"差不多"**
  - 业务: PR #57 8pt grid 原则: 2/4/6/8/12/16/24
  - 旧 CSS: `padding: 1px 6px` 1px 不是 2 倍数
  - 修复: 1px 仅用于绝对定位边距 (top: 1px, right: 1px), 视觉上几乎无差, 但严格度低
  - **Rule**: 表格/表单 padding/margin 严格 2 倍数 (PR #57 教训); 绝对定位 1px 边距 OK

**踩坑 6: disabled 状态视觉**
  - 业务: 0 行时提交按钮应该 disabled, 但视觉上要明确 (不要透明到看不见)
  - 修复: `opacity: 0.5` (半透明可见) + `cursor: not-allowed` (鼠标提示)
  - **Rule**: disabled 元素保持可见 (opacity 弱化), 加上 cursor 提示, 不要 display: none (用户会困惑)

**Rule**: 批量添加 UI 设计原则 (Apple/Google/Stripe 风格):
  1. **CSS 通用, 不要带容器 scope** — 写在最高层, 适用所有 modal/form/tree
  2. **focus 状态主色 + box-shadow** — 视觉反馈明显, 跟品牌一致
  3. **hover:not(:focus) 排除 focus** — 避免状态叠加
  4. **focus-visible 代替 focus** — 键盘 accessibility
  5. **8pt grid 严格** — 2/4/6/8/12/16/24px (1px 仅绝对定位)
  6. **disabled 保持可见** — opacity 0.5 + cursor not-allowed
  7. **transition 0.12s** — hover/focus 平滑 (不要太长, 显得迟钝)

### 5.28 +/- 位置 + 宋代配色 (PR #62 教训)

**根因 (PR #62 业务需求)**: 用户 (2026-07-21) 反馈 "+ 号应该在上, - 号在下" + 提供宋代配色 5 色。

**踩坑 1: + / - 位置 user feedback**
  - 业务: native number spinner 是 + 在上, - 在下 (主流 UI 库一致)
  - 旧实现: minus 在上, plus 在下 (反了)
  - 修复: 互换 top/bottom 位置 (+ top: 1px, - bottom: 1px)
  - **Rule**: spinner 按钮位置跟 native 一致 (+ 上 - 下), 跟用户预期一致

**踩坑 2: 配色 token 体系**
  - 业务: 用户提供宋代 5 色 token, 需要全栈应用 (input 边框, +/- 按钮, 提交, 提示)
  - 旧配色: 灰色系 (#D1D5DB, #E5E7EB, #9CA3AF, #6B7280, #F3F4F6) — 跟主色 #5AA4AE 不和谐
  - 新配色: 宋代 5 色 (天水碧/月白/墨灰/缃色/青白) — 跟主色和谐, 视觉水墨风
  - **Rule**: 设计 token 配色要跟主色和谐 (同色系或补色), 避免灰色"死板"感

**踩坑 3: 配色 token 替换范围要全**
  - 业务: 替换 CSS 时要覆盖所有相关位置, 不能只换一处
  - 业务: 批量添加页面有 5+ CSS 块 (input, +, -, 提示, 加行, 提交, 取消, row-del), 每个都要换
  - **Rule**: 配色替换前先 grep 全搜, 列清单, 5+ 位置全换, 测试全验

**踩坑 4: input 边框用浅色 (月白) 而非灰 (D1D5DB)**
  - 业务: 旧 input 边框 #D1D5DB (Tailwind gray-300) 跟主色 #5AA4AE 不和谐
  - 修复: 用 #D6ECF0 (月白) 跟主色同色系, 视觉柔和
  - **Rule**: 边框色跟主色同色系, 不要用通用灰色, 视觉上"主色家族"感

**踩坑 5: +/- bg 用白底 (跟 input 融合)**
  - 业务: 旧 +/- bg #F9FAFB (灰白) 跟 input bg #FFFFFF 有色差, 视觉分离
  - 修复: 用 #FFFFFF (白底) 跟 input 融合, +/- 像"input 的扩展"
  - **Rule**: spinner 按钮 bg 跟 input bg 一致, 视觉上是 input 的一部分 (不是独立元素)

**踩坑 6: hover/active 反馈用月白/青白 层级**
  - 业务: 旧 hover #E5E7EB (灰) → active #D1D5DB (深灰), 灰色系反馈"死板"
  - 修复: hover #D6ECF0 (月白, 浅色) → active #C0EBD7 (青白, 深色), 4 层级视觉:
    1. 默认: 白底
    2. hover: 月白 (#D6ECF0)
    3. active: 青白 (#C0EBD7)
    4. focus: 主色 outline (#5AA4AE)
  - **Rule**: 状态反馈用同色系层级 (浅→中→深→主), 不要用通用灰色

**踩坑 7: 警示色 (红) 跨业务统一**
  - 业务: 错误状态用红 (#EF4444) 是跨业务统一约定 (e.g. invalid, delete hover)
  - 修复: 红保留, 不改宋代配色 (宋代配色是主视觉, 红是警示)
  - **Rule**: error 状态用跨业务统一颜色 (红), 不用主色 (避免混淆"主色 = 错误")

**Rule**: 配色 token 体系原则:
  1. **+ 上 - 下 (跟 native 一致)** — spinner 按钮位置
  2. **5 色 token (主+浅+辅+点+深)** — 视觉层级丰富
  3. **配色跟主色同色系** — 不要用通用灰色
  4. **input 边框用浅色 (月白)** — 跟主色和谐
  5. **spinner bg 跟 input 融合** — 视觉上一体
  6. **状态反馈 4 层级** (默认/hover/active/focus) — 用同色系
  7. **error 跨业务统一 (红)** — 不用主色

### 5.29 UAT 清理 + 打包 + 客户文档 (PR #63 教训)

**根因 (PR #63 业务需求)**: 用户 (2026-07-21) 拍板: "清理一下这个文件夹下的文件, 包括不需要的函数也可以删除. 计划打包发布给客户做UAT. 另外写一份提供给客户的使用文档."

**踩坑 1: LLM 路由 default "deepseek" 触发 line 495 raise ValueError hard fail**
  - 业务: 客户 UAT 只测 commission, 不配 LLM key, server 应该能正常启
  - 旧实现: `LLM_PROVIDERS` 默认 "deepseek" → `Settings.__init__` line 495 `raise ValueError("❌ Provider 'deepseek' 配置不完整")`
  - 修复: 默认 `LLM_PROVIDERS=""` + line 486-487 改成 `logging.warning("⚠️ LLM_PROVIDERS 未配置, chat 端点不可用")`
  - 业务侧 (commission / 树视图 / 期间结算) 零影响, chat 端点 503
  - **Rule**: 任何"业务侧跟 X 无关但 server 启不来"的代码, 都要 graceful skip. 客户/用户**不会**为了用 Y 而去配 X

**踩坑 2: 启动脚本 hardcode 路径**
  - 业务: 客户下载 UAT 包放到任意目录, 双击 start_uvicorn.bat 启动
  - 旧: `start_uvicorn.bat` line 2 `cd /d D:\Projects\Reward\RewardAgentAnalysis` — hardcode 用户的本地路径
  - 旧: `tools/start_server.ps1` line 3 `Set-Location "D:\Projects\Reward\RewardAgentAnalysis"` — 同上
  - 修复:
    - .bat: `cd /d "%~dp0"` (脚本所在目录)
    - .ps1: `Set-Location "$PSScriptRoot\.."` (脚本所在 tools/ 的父目录)
  - **Rule**: 启动脚本**永远不要 hardcode 路径**, 用脚本所在目录作为 anchor

**踩坑 3: README 内容跟实际业务脱节**
  - 业务: 主线已从 Stage 3 multi-skill 引擎迁到 commission 系统, README 还在讲过时的 chat/embedding/RAG
  - 旧: README 20KB, 60% 内容跟当前业务无关
  - 修复: 改写 6.5KB, 明确主线是 commission 系统, LLM 路由标注 optional
  - **Rule**: README 是项目的"门面", 跟实际业务脱节比"没有 README"还糟糕. 每改业务主线, README 必同步

**踩坑 4: 客户文档不能只写 .md**
  - 业务: 客户 UAT 不一定有 Markdown 编辑器, 但一定有浏览器
  - 解决: 写 .md (源, 维护方便) + 自动转 .html (单文件, 浏览器直接看)
  - HTML 加宋代配色 (跟项目一致) + 🖨️ 打印按钮 (客户能打印/导出 PDF)
  - 用 Python `markdown` 库转 (依赖已在 requirements.txt 里的 transitive 依赖? 不, 实际是装在 venv 里的)
  - 实际: 我直接 `import markdown` 用, 跑通了, 不在 requirements.txt 声明
  - **Rule**: 给客户的文档**至少 2 种格式**: 源 (md) + 渲染 (html/pdf), 客户用啥都能看

**踩坑 5: 打包脚本 PowerShell GBK 兜底**
  - 业务: `tools/build_uat_zip.py` 跑在 PowerShell, emoji (📦 ✅ 🗑️) 触发 UnicodeEncodeError
  - 解决: 顶部加 `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")` (跟 §5.13 同款)
  - 或者干脆用 ASCII (我选了后者, 输出更兼容)
  - **Rule**: 任何 Python script 可能在 PowerShell 跑, 都要 GBK 兜底 OR 用 ASCII 输出

**踩坑 6: Python `python -c` 多层引号嵌套炸**
  - 业务: 写 md_to_html.py 想用 `python -c "..."` 一次性跑, 里面有 HTML 模板嵌套引号
  - PowerShell 解析器: `"<button class=\"print-btn\""` 直接报 ParserError
  - 解决: 写文件 `md_to_html.py` + `python md_to_html.py` (跟 §5.15 同款)
  - **Rule**: 任何稍微复杂的 Python 代码, 写文件跑, 不要 `python -c "..."`

**踩坑 7: 打包排除清单要列全**
  - 业务: 客户 UAT 包越小越好, 但不能漏掉核心代码
  - 排除 (15+):
    - tests/ (19 个, 270KB, 客户不要)
    - .git/ (git 历史, 几十 MB)
    - .worktrees/ .pytest_cache/ __pycache__/ .claude/ (开发残留)
    - data/ (旧 db, 客户首次启动自动建)
    - uvi*.log uvicorn*.log (启动日志)
    - .env .env.MiniMax (私人 key)
    - _commit_pr14.py (PR #14 临时脚本)
  - 包含: 4 个 .py + requirements + start_uvicorn.bat + .env.example + skills/ + static/ + tools/ + json/ + README + CUSTOMER_GUIDE × 2 + AGENTS + LICENSE + .gitignore
  - **Rule**: 打包前 grep 全搜 "无用文件候选" (历史脚本, 临时文件, 私人配置), 列清单, 不漏删

**Rule**: UAT 客户包设计原则:
  1. **业务优先** — LLM 这种跟业务无关的代码 graceful skip, 客户不配也能跑
  2. **零 hardcode** — 启动脚本用脚本所在目录 anchor, 跨用户/跨路径通用
  3. **README 跟业务同步** — 业务主线变了 README 必改写, 客户第一时间看的
  4. **客户文档 .md + .html** — 源 + 渲染, 客户用啥都能看
  5. **打包排除列清单** — tests/ .git/ 私人配置 必排除, 核心代码不能漏
  6. **PowerShell 兜底** — emoji 改 ASCII, sys.stdout reconfigure
  7. **python -c 不用** — 写文件跑, 避免引号嵌套
  8. **UAT 包自检** — 跑 258 测试 + Playwright 冒烟, 客户拿到就能用

### 5.32 子区 PV 递归累加 bug (PR #66 教训)

**根因 (用户截图反馈, 2026-07-23)**: 加 4 member A/B/C/D, 树 root → A(L1) + B(L2), A → C(L1), B → D(L1), PV 1500/1000/1500/1000. 期望 root own = 300 PV (配对 2000 × 15%), 实际算出 150 PV (只 1 层).

**根本 bug**: `_build_settle_tree` line 270 `sorted_members[:5]` 把所有非 root member 当 root children, **完全忽略 `parent_dist_id` 树形关系**. 树形扁平化, 父节点 1 区/2 区 算不出 A 子区 (= A own + C own), 只能拿到 root 的 5 个直接 children, 看不到 3 层深.

**PR #58 旧实现**: `_settle_node` `return max_pv` 只看 1 层 (直接子 max). 父节点配对时少算子孙 PV.
**PR #66 修复**: `return own + sum(c_pv_total)` 递归累加 own + 整棵子树 PV.

**用户业务规则 (PR #66 拍板)**:
1. 节点 own 跟 5 子区中 P (max) 配对消耗: `own_pair = MIN(own, P)`
2. 5 子区 P/L 配对消耗: `sub_pair = MIN(P - own_pair, L_sum)`
3. 节点 commission = `(own_pair + sub_pair) × 15%` (T5 测试兼容: own 配对也算 commission)
4. own 剩 → 节点 carry, P 剩 → P 子区根 carry, L 剩 → L 子区根 carry (按比例)
5. 子区总 PV (return 第二值) = own + sum(子节点 c_pv_total) 递归累加

**踩坑 1: `_build_settle_tree` 不能把非 root member 全当 root children**
- 旧 (PR #53): `for i, m in enumerate(sorted_members[:5])` — 树形扁平化
- 新 (PR #66): 递归按 `parent_dist_id` 构造真 5 叉树
  - 找 root (parent_dist_id 空 + slot_line_id 0)
  - 递归构造每个 member 的 5 个子槽位 (按 slot_line_id 1-5 排序)
  - 缺槽位补 None, `_settle_node` 跳过
- **业务测试通过 ≠ 算法层正确** — PR #58 业务测试 (扁平树) 100% 通过, 但 3 层深树算错
- 实际业务场景: 9 层深树常用, 子孙 PV 累加是关键

**踩坑 2: `_settle_node` return 值必须递归累加**
- 旧 (PR #58): `return max_pv` — 父节点配对时少算子孙 PV
- 新 (PR #66): `return own + sum(c_pv_total for child)` — 递归累加 own + 整棵子树 PV
- 父节点用这个 return 当 sub_pvs 输入, 决定 P vs L 配对结果
- **业务**: 5 叉树深度 9 层, 子孙 PV 必须累加到父节点视角, 否则 3 层以上全错

**踩坑 3: 节点 own 跟 P 配对消耗 (own-P)**
- 业务: 节点 own 是 L, 5 子区中 max 是 P, MIN(own, P) = own_pair
- own 消耗 own_pair, P 消耗 own_pair
- own 剩 → 节点 carry, P 剩 → P 子区根 carry
- 例: A own=1500, P=C=1500, own_pair=1500, A own 剩=0, C 子区剩=0 → A carry=0+1000 (来自根)=1000 ✓
- 业务验证: 用户截图 A 拿 1000 carry (来自根的 P 子区剩 1000 写给 A)

**踩坑 4: 节点 commission = (own_pair + sub_pair) × 15%**
- T5 测试期望: L2 own=100, P=100 (L3), L=100 (L4) → own_pair=100, sub_pair=0, L2 commission = 100×15% = **15** ✓
- ABCD 测试: A own=1500, P=1500 (C), L=0 → own_pair=1500, sub_pair=0, A commission = 1500×15% = 225 (carry 验的是 A=1000 ✓)
- 两种配对都给节点 commission, 业务规则统一

**踩坑 5: carry 归属**
- own 剩 → 节点自己 carry (写 `carry_out_by_dist[node.member_dist_id]`)
- P 剩 → P 子区根 carry (子节点, 写 `carry_out_by_dist[c.member_dist_id]`)
- L 剩 → L 子区根 carry (按比例, 写 `carry_out_by_dist[c.member_dist_id]`)
- 实现: `_settle_node` 统一写 carry (避免叶子/父节点双重累加)
- 叶子节点没子区, `return 0.0, node.pv`, own 留给父节点配对消耗
- **业务**: carry 跟成员走 (PR 业务规则 §2.3), 跟槽位无关

**Rule**: 改算法或树形构造必查:
1. `_build_settle_tree` 按 `parent_dist_id` 递归构造真 5 叉树
2. `_settle_node` return 第二值递归累加 (own + sum(子节点 c_pv_total))
3. own-P 配对消耗 (own 是 L, P 是 P)
4. 节点 commission = (own_pair + sub_pair) × 15%
5. carry 归属 (own → 节点, P/L → 子节点)
6. 业务测试 100% 通过 ≠ 算法层正确 — 3 层深树要单独测 (test_pr66_settle_3_level_deep_tree)

### 5.33 渲染层 commission preview 跟算法层不一致 (PR #67 教训)

**根因 (用户截图反馈, 2026-07-24)**: PR #66 修了算法层 `_settle_node` 用递归累加 (`return own + sum(c_pv_total)`), 但**前端 commission preview 徽章** (`main.py _build_tree_from_db._build`) **还在用 PR #58 旧逻辑** (`children[].periodPv` 只看 1 层), 算少一半.

**ABCD 4 member 树 (用户截图)**: root → A(L1) + B(L2), A → C, B → D, PV 1500/1000/1500/1000
- 用户期望 root own = 300 (1区=3000, 2区=2000, 配对 2000 × 15%)
- 实际显示 root own = 150 (PR #58 bug: max 1500+0+0+0=1500, sum_rest=1000, pair=1000, commission=150)

**踩坑 1: 改算法层时漏改渲染层**
- PR #66 改 `skills/pair_commission.py._settle_node`, 业务测试通过
- 但**前端 commission preview 徽章** (`main.py._build_tree_from_db`) 还在用 PR #58 旧逻辑
- 两个层算法不一致, 前端算少一半
- 修复 (PR #67): 渲染层加 `subtreePv` 字段 (= own + sum(子节点 subtreePv), 递归累加)
- 渲染层 `ownBasic` 算 P/L 配对用 `children[].subtreePv` 不是 `children[].periodPv`

**踩坑 2: 节点 commission = (own_pair + sub_pair) × 15%**
- T5 兼容: L2 own=100, P=100 (L3), L=100 (L4) → own_pair=100, sub_pair=0, commission=15
- ABCD root: own=0, P=3000, L=2000 → own_pair=0, sub_pair=2000, commission=300
- ABCD A: own=1500, P=1500 (C 子区递归), L=0 → own_pair=1500, sub_pair=0, commission=225
- 两种配对都给节点 commission, 业务规则统一 (跟算法层 PR #66 一致)

**踩坑 3: PR merge manual edit 必须 commit**
- PR #65 merge 时, 手动加 `_build_settle_tree` 函数体 `if dry_run:` 临时清 carry, 但**漏了给函数签名加 `dry_run=False` 参数**
- 主仓 working tree 有 manual edit (没 commit), worktree 跟主仓有差异
- PR #67 commit 把这个修复 + commission preview 递归子区 PV 一起合并
- **Rule**: merge 时手动改的代码必须 commit 进 merge commit, 不能留 working tree dirty

**Rule**: 改算法层时, 渲染层必须同步对齐:
1. 算法层 `_settle_node` 算 commission 用递归子区 PV
2. 渲染层 `_build_tree_from_db` 算 ownBasic 也必须用递归子区 PV
3. commission = (own_pair + sub_pair) × 15% (跟算法层完全一致)
4. PR merge 时 manual edit 必须 commit (不要留 dirty working tree)

### 5.30 settle 模态字段名错 (PR #64 教训)

**根因 (用户截图反馈, 2026-07-23)**: "结算本周佣金" 模态 5 个 member 全显示 $0.00, 但后端 DB 已正确写入 (王常军 own=¥75, period.status=settled).

**根因分析**:
- 后端 `api_period_settle` (PR #53 改的) 返回新字段名: `own_commission` / `ancestor_share` / `total_commission` / `member_dist_id`
- 前端 `renderSettleResult` (PR #51 写的) 用旧字段名: `m.commission` / `m.pairing` / `m.total` / `m.uid`
- 字段全部 fallback 到 0 / '-', 5 个 member 全 $0.00

**坑 1: 前端字段名是"猜"的, 没跟 API schema 对齐**
  - 旧实现: `m.commission ?? m.basic ?? 0` — 字段名是**推测**的, 不是从 API schema 拿
  - 实际 API: `m.own_commission` (没 `commission` / `basic` 字段)
  - 修复: 优先新字段名, 兜底旧字段名 (向后兼容)
  - **Rule**: 前端用 API 字段时, **必须从 API 代码看实际返回的 key**, 不要凭印象写. 可以直接 grep `"key":` 看 main.py 序列化 dict

**坑 2: PR #53 改 API 字段名, 跟前端字段对齐的测试没跑**
  - 旧流程: PR #53 只跑了 pytest 业务逻辑 + API 端点测试, 没跑 Playwright 验证前端 modal 渲染
  - 实际: 业务逻辑 (settle_period 算法) 跟前端渲染 (renderSettleResult) 是**两个独立链路**
  - 业务侧测试 100% PASS, 前端显示仍然全 0
  - 修复: 改 API 字段名时, **必须** Playwright 验证前端 modal / 表格实际渲染
  - **Rule**: 改 API 字段名, 跑 3 件事:
    1. pytest 业务逻辑 (看 DB / 算法)
    2. 直接 curl API 看 JSON (确认返回结构)
    3. Playwright 验证前端 modal 渲染 (确认显示正确)

**坑 3: uid 字段渲染逻辑也错**
  - 旧实现: `m.uid || m.member_uid || '-'`
  - 实际 API: 返回 `member_dist_id`, 没 `uid` / `member_uid` 字段
  - 显示 '—' 是 fallback, 不是真实数据
  - 修复: 优先 `m.member_dist_id` (前端 UID 列就是显示 distId)
  - **Rule**: 前端"ID 字段"找不到时, **先确认 API 是否返回了 ID 字段**, 不要直接 fallback 到 '-'

**Rule**: API ↔ 前端字段对齐原则:
  1. **从 API 端看字段名** — grep main.py 序列化 dict, 不要凭印象
  2. **改 API 字段名** — 必跑 Playwright 验证前端渲染 (业务测试通过 ≠ 前端显示对)
  3. **前端兼容兜底** — 优先新字段, 兜底旧字段 (兼容老 API 调用方)
  4. **uid / id 字段** — API 没返回时, 先确认 schema, 不要直接 fallback
  5. **测试覆盖** — 测试前端渲染函数 (regex 检查字段名) + Playwright 端到端

---

## 6. 文件结构

```
D:\Projects\Reward\RewardAgentAnalysis\
├── main.py                          # FastAPI app + API endpoints + 渲染层
├── models.py                        # SQLAlchemy ORM (Member, PVLedger, CommissionPeriod)
├── repository.py                    # DB CRUD (MemberRepository, PVLedgerRepository)
├── database.py                      # SessionLocal + get_db + init_db
├── skills/
│   ├── skill_5_lib.py               # Node5 + 算法层 (effective_max_active_lines 等)
│   ├── skill_5_3.py                 # 5 叉树 9 层算法 (find_next_slot_bitrev)
│   ├── skill_5_helpers.py
│   ├── pair_commission.py           # 周结算 (settle_period)
│   ├── period.py                    # 业务周 + ISO 周工具
│   └── skill_5_3_README.md          # skill 5_3 算法文档 (X 坐标公式 + bit_reverse)
├── static/
│   └── index.html                   # UI (前端, 改完必须 playwright 验证)
├── tests/
│   ├── test_api_members_list.py     # PR #27
│   ├── test_root_member.py          # PR #28
│   ├── test_active_lines.py         # PR #18/22
│   ├── test_strict_bitrev.py        # PR #18/21
│   ├── test_locked_xcoord.py        # PR #25
│   ├── test_pair_commission.py
│   ├── test_settle_e2e.py
│   └── test_write_to_disk.py        # 9 ERROR (gitignored fixture, 跳过)
├── tools/
│   ├── init_root_member.py          # PR #28 幂等 migration (root 行)
│   ├── migrate_add_role.py          # PR #41 幂等 migration (role 列)
│   ├── migrate_pr55_period_id.py    # PR #55 幂等 migration (业务周 ID 格式)
│   ├── start_server.ps1             # PowerShell 后台启动 (跨路径通用)
│   └── build_uat_zip.py             # PR #63 打包 UAT 客户包
├── data/
│   ├── .gitkeep
│   └── rewarddb.db                  # SQLite (gitignored, 首次启动自动建)
├── json/                            # Tree_empty_5_3.json / dense_demo.json (gitignored)
├── outputs/                         # 打包输出目录 (gitignored, 保留 .gitkeep)
├── CUSTOMER_GUIDE.md                # PR #63 客户使用文档 (Markdown 源)
├── CUSTOMER_GUIDE.html              # PR #63 客户使用文档 (HTML 单文件, 宋代配色)
├── start_uvicorn.bat                # Windows 一键启动 (跨路径通用)
├── .env.example                     # LLM key 模板 (optional, 业务不依赖)
├── AGENTS.md                        # 本文件 (开发 agent 指南)
└── README.md                        # 项目门面 (技术开发用)
```

---

## 7. API endpoints (核心)

| Method | Path | 用途 |
|---|---|---|
| GET | `/api/members` | 列出所有成员 (PR #27 加 4 字段: parent_dist_id, slot_line_id, last_period_remaining_pv, last_period_deducted_pv) |
| GET | `/api/tree/render` | 树视图 (PR #23 加 slot_view 字段, "active"/"all") |
| POST | `/api/skill_5_3/preview` | 算法预览 (无写盘) |
| POST | `/api/skill_5_3/commit_preview` | 写盘 (PR #19 用 _preview_dist_id_map) |
| GET | `/api/period/list` | 历史周期 |
| GET | `/api/period/{id}/summary` | 周期详情 |
| POST | `/api/period/{id}/settle` | 周结算 |

---

## 8. 常用命令速查

```powershell
# 跑测试
cd .worktrees\feat-xxx; python -m pytest tests/ -v

# 看 server log
Get-Content "$env:TEMP\uvicorn_xxx.err.log" -Tail 30

# 拉数据
python -c "import urllib.request, json; print(json.dumps(json.loads(urllib.request.urlopen('http://127.0.0.1:38080/api/members', timeout=5).read()), ensure_ascii=False, indent=2))" > peek.json

# 看 SQLite
python -c "import sqlite3; c=sqlite3.connect(r'D:\Projects\Reward\RewardAgentAnalysis\data\rewarddb.db'); print(list(c.execute('SELECT * FROM members').fetchall()))"

# 验证 commit message (中文)
python -c "
import zlib, subprocess
sha = subprocess.run(['git','rev-parse','HEAD'], capture_output=True, text=True).stdout.strip()
import pathlib
obj = pathlib.Path('.git/objects') / sha[:2] / sha[2:]
raw = zlib.decompress(obj.read_bytes())
print(raw.split(b'\n\n', 1)[-1].decode('utf-8'))
"
```

---

### 5.34 翻案 PR #66 own-P 配对 + carry 双计 (PR #68 教训, 2026-07-27)

**根因 (用户截图, 2026-07-27)**: A 节点显示 "本期可拿 ¥150", 用户说 "A 本期应该拿不到佣金, 因为他的 2 区还没有挂任何新成员". C 在 A 的 4 子区 (line 4), 2 子区空, 5 子区 P=1500 (C), L=0, pair=0, commission 应为 0.

**PR #66 旧算法 (own-P 配对消耗) 错在哪**:
- `own_pair = MIN(own, P)` 让 own 跟 P 配对, own 算 commission
- 业务验证: A (own=1500, 5 子区 C=1500) 旧算法 own_pair=1500, commission=150 — **错!**
- 用户业务术语 "1 区/2 区" = 父节点 5 子区递归累加 (own 跟 commission 配对无关, own 是节点独立 ledger PV)
- "1 区/2 区" 不是节点 own + 5 子区 (老 officev2 风格), PR #66 理解错了

**PR #68 新算法 (own 不参与 commission 配对)**:
- 节点 own PV **直接 carry, 不参与 commission 配对**
- 5 子区 P/L 配对: `P = max(5 子区 c_pv_total 递归累加)`, `L = sum(其他 4)`
- `pair = MIN(P, L)`, `commission = pair × 15%`
- own 100% carry 给节点 (不参与配对)

**踩坑 1: 算法层改时渲染层必须同步对齐 (PR #67 教训延续, PR #68 再犯)**
- PR #68 改算法层 `_settle_node` (own 不参与), 渲染层 `main.py._build` 还在用 PR #66 公式 `ownBasic = (own_pair + sub_pair) × 0.15`
- 同步翻案: `ownBasic = sub_pair × 0.15` (only 5 子区 P/L 配对, own 不算)
- **Rule**: 改 commission 公式时, 渲染层 `ownBasic` 跟 commission preview 公式必须**同时**改, 不分 PR

**踩坑 2: carry 双计 (own + p_remain 累加导致 double count)**
- 业务: 父节点 p_remain (P 子区剩) 写到子节点 carry, 跟子节点自己 own carry 累加
- 问题: 当子节点是叶子 (own = 父 p_remain 数值上相同), 累加 = 双计
- 例: t1 (1 member + root) own=500, root p_remain=500, additive 给 1000, 期望 500
- 例: ABCD C own=1500, A p_remain=1500, additive 给 3000, 期望 1500
- **修复**: own carry 只对**非叶子**写, 叶子 own 由父 p_remain 覆盖 (不重复写)
- 算法: own carry write 移到 leaf early return **之后**
- **Rule**: 父写 subarea remain + 节点写 own carry, 叶子 own 不写 (避免双计)

**踩坑 3: 业务规则反复推翻, "1 区/2 区" 语义不同 PR 含义不同**
- PR #66 业务术语: "1 区/2 区" = 父节点 own + 5 子区 (老 officev2 风格)
- PR #68 业务术语: "1 区/2 区" = 父节点 5 子区递归累加 (own 跟 commission 配对无关)
- 用户 2026-07-23 第一次截图说 "root own 应该 300 PV" — 翻案后 PR #66 给出 300 PV
- 用户 2026-07-27 第二次截图说 "A own 应该 0" — 翻案后 PR #68 给出 0 (A 5 子区 P=1500 L=0 pair=0)
- 两次截图描述的 "1 区/2 区" 含义不同, 业务规则反复推翻
- **Rule**: 业务截图要反复确认, "1 区/2 区" 在 commit 前跟用户确认
  - 是父节点 own + 5 子区 (老 officev2)?
  - 还是父节点 5 子区递归累加 (PR #68)?
  - own 跟 commission 配对有关吗?

**踩坑 4: 测试用 dynamic period (`get_current_period_id()`), 不用 hardcode 日期**
- 业务周 (Sun-Fri) 跨日切换公式: `start = today - timedelta(days=(weekday + 1) % 7)` (PR #55)
- 测试 hardcode "2026-07-19_W30" 跟 `get_current_period_id()` 不一致, 测试跟实际业务周期 drift
- 修复: 测试用 `get_current_period_id()` 动态算 period
- **Rule**: 任何 settle / period 相关测试用 `get_current_period_id()`, 不用 hardcode 日期字符串

**踩坑 5: business rule 反向推算要谨慎 (commit 时从用户截图反推, 易推错)**
- PR #66 业务规则 (own-P 配对) 是 commit 时从用户 2026-07-23 截图反推的, 用户没明说
- 用户 2026-07-27 又反馈"应该翻案", 证明 PR #66 推算错了
- 业务术语 "1 区/2 区" 在用户心里 vs 在我代码里, 含义可能不同
- **Rule**: commit 时反推的 business rule 在 PR description 标记"反推, 待用户二次确认"
  - 用户二次确认 (新截图 / 新问题) 后, 才能确定规则不变
  - 用户任何截图反馈, 都要重新核对 PR 描述的 business rule, 不要假定"PR 拍板了, 规则不变"

**Rule**: 改算法层时必查:
1. 算法层 `_settle_node` 改 commission 公式 (own 是否参与配对)
2. 渲染层 `ownBasic` / `commissionPreview` 跟 commission 公式**完全一致** (PR #67 + PR #68 共同教训)
3. carry 算法: own carry 只非叶子写, 父 p_remain 永远 ADD 模式 (避免双计)
4. 业务术语"1 区/2 区"在 commit 前跟用户确认, 不假定
5. 测试用 `get_current_period_id()` 不用 hardcode 日期

### 5.35 下单管理 + 库存联动 (PR #70 教训, 2026-07-27)

**根因 (PR #70 业务需求)**: 用户 2026-07-27 截图反馈 "增加一个下单管理按钮, 里面是一张表, 显示了目前的库存和这次准备下单的数量, 单价, 客户在增加购买的数量的时候, 也相应减少库存的数量, 并且同时计算出各项金额". 业务规则拍板: (1) 需求↑则库存按差量减少; (2) 显式「保存」按钮 (不自动存).

**踩坑 1: 新表 + 幂等 seed 必须在 GET 端点, 不在 startup hook**
- 业务: 客户首次打开 modal 时, 8 个 sample 产品要自动显示 (如果表是空的)
- 旧实现 (假设): 在 startup `@app.on_event("startup")` 加 seed
  - 问题: 客户 DB 已经有表 (e.g. UAT 客户跑了一段时间), startup seed 会重复插入 → unique 约束炸
  - 修复: `_ensure_order_items_seeded` 跑在 GET 端点开头, 检查 `count() > 0` 跳过
- **Rule**: 任何 "插入 sample 数据" 的逻辑都要幂等 + 在调用点 (e.g. GET 端点), 不在 startup

**踩坑 2: 单品差额 / 总金额 / 合计 必须前端实时算, 不能存 DB**
- 业务: 单品差额 (库存 - 需求) 跟 总金额 (套组 × 套组价格) 跟 合计 都是派生数据
- 旧实现 (假设): 存 DB, 每次更新需求时 trigger 算
  - 问题: 4 个字段 (需求/库存/套组/套组价格) 改一个就要触发 3 个派生字段, schema 复杂
  - 修复: 派生字段**不存 DB**, 每次 GET 在 server 实时算, 前端 input 事件再实时算
- **Rule**: 派生数据 (单字段可推算的) 不存 DB, server 实时算 + 前端实时算. 存 DB 的字段是"原始数据 + 用户手动改的状态"

**踩坑 3: 联动 (需求↑库存↓) 只能前端做, 后端不做**
- 业务: 客户改 required_qty, 库存自动按差量减少 (`stock_new = stock_orig - (req_new - req_orig)`)
- 旧实现 (假设): 后端 PATCH 时联动算
  - 问题: 后端联动后, 客户如果只 PATCH required_qty, 库存会被后端"擅自"改, 业务不可控
  - 修复: 后端只是 store, 联动只在前端 input 事件做. 测试 `test_business_rule_keep_db_invariant` 验证: 后端只发 required_qty, 库存不变
- **Rule**: 联动逻辑 (e.g. A 改 → B 自动改) 只能前端做. 后端职责是 store + 校验 + 实时算派生字段. 联动 = 业务规则, 在前端
- **联动公式用 orig 不用 current**: `_origMap[id] = {required_qty, current_stock, ...}` 缓存打开 modal 时的 server 值. 用户改 1 次或多次, 库存都按 orig 算, 避免累计计算错误

**踩坑 4: 显式「保存」按钮要 dirty 跟踪 + 二次确认**
- 业务: 改完手动点保存, 关 modal 二次确认 (有未保存修改时)
- 旧实现 (假设): auto-save (input 事件就 PATCH)
  - 问题: 客户改一半 (e.g. 改错数字), 没机会回退, API 流量也大
  - 修复: dirty 集合 `_dirtyIds` 跟踪改过的行, .modified CSS 标记, "保存" 按钮显示 dirty 行数
- 二次确认: 「取消」/「刷新」/「关闭」按钮, 如果 `_dirtyIds.size > 0`, confirm("有 N 行未保存, 继续?")
- **Rule**: 任何"批量改 + 显式保存"的 UI 必须: (1) 改的行有 .modified 视觉标记; (2) 保存按钮显示 dirty 行数; (3) 离开 modal 二次确认

**踩坑 5: Pydantic schema 拒绝额外字段防"误改 key"**
- 业务: 品名 (name) / 单位 (unit) 是 key, 不允许改
- 旧实现 (假设): 接收 `OrderItemUpdate` 4 字段 (id + required_qty + current_stock + package_count + package_price), 如果前端多发 `name`, 怎么处理?
- 修复: Pydantic v2 默认 `extra="ignore"`, 额外字段被静默忽略, 但测试 `test_bulk_update_only_4_fields_allowed` 验证 name 没被改
- 如果想更严: `class Config: extra = "forbid"` → 422, 但当前 OrderItemUpdate 没显式 extra=, 所以是 ignore
- **Rule**: key 字段 (e.g. name) 默认不暴露在 update schema, 即使前端误发也不会改 DB. 测试验证关键 key 不被改

**踩坑 6: Playwright 验证前端 modal (PR #24 教训延续, PR #70 再用)**
- 业务: 改 `static/index.html` 加 `openOrderMgmtModal()`, 必须 Playwright 验证
- 实际: 8 行 + 合计 35162 + 联动 (18→25 库存 17→10) + 改回 25→18 库存 10→17 + 保存 PATCH 成功 + DB 恢复 + 0 JS errors, 全过
- **Rule**: 改 `static/index.html` 加新 modal/函数, 必 Playwright 验证 4 件: (1) 弹 modal (2) 表格/控件渲染 (3) 联动逻辑 (4) 保存/submit, 0 JS errors
- 跟 PR #24 教训一致: 删大段代码残留 `*/` 报 syntax error → 整个 inline script 终止 → modal 不弹, 只能 Playwright catch

**Rule**: 下单管理 (含未来业务扩展) 设计原则:
1. **新表幂等 seed** — `_ensure_xxx_seeded` 在 GET 端点, 不在 startup, count() > 0 跳过
2. **派生数据不存 DB** — server 实时算 + 前端实时算, DB 只存"原始数据 + 用户状态"
3. **联动只前端** — 后端 store + 校验, 联动 = 业务规则, 在前端
4. **显式保存 + dirty 跟踪** — .modified CSS 标记, 保存按钮显示 dirty 行数, 离开 modal 二次确认
5. **Pydantic schema 防误改** — key 字段 (e.g. name) 不暴露, 测试验证
6. **Playwright 验证** — 改 static/index.html 必跑 e2e: 弹/渲染/联动/保存 + 0 JS errors
7. **CSS 8pt grid 严格** — 2/4/6/8/12/16/24px (跟 PR #61 一致), 颜色跟主色和谐 (跟 PR #62 一致)

---

## 9. 不要做的事

- ❌ 在主仓 `D:\Projects\Reward\RewardAgentAnalysis\` 直接改代码
- ❌ 改 `static/index.html` 不跑 playwright 验证
- ❌ 改算法层业务规则不检查渲染层
- ❌ 改 API 字段名不 grep 引用方
- ❌ 删大段代码不 grep 残留注释符号
- ❌ 用 `git commit -m "中文"` 多行 message
- ❌ 用 `gh pr create --body "多行 内容"` (空格 unknown arg, 用 --body-file)
- ❌ 启动 server 用 `cd && python -m uvicorn ...` (cwd 跟 Start-Process 不一致, 用 -WorkingDirectory)
- ❌ 用 `Remove-Item` 删文件 (用 `mavis-trash`)
- ❌ 用 `rm -rf` (没有这命令, PowerShell)
- ❌ 用 `git status; git log --oneline -5` 在 PowerShell (PowerShell 不是 bash, 用 `;` 串行或分两条)
- ❌ worktree 不复制 data/ 就跑测试 (新 schema 时 init_db)
- ❌ PowerShell `python -c "..."` 带 `{` `}` (f-string/dict/集合字面量) — 写文件跑 (§5.15)
- ❌ worktree 验证 commit object 走 `Path('.git/objects/...')` — 用 commondir 路径 (§5.14)
- ❌ 删 CSS class 验证 "已废弃" 用 `if 'name' in text` — 注释里提到不算, 查 `re.search(实际用法)` (§5.16)
- ❌ 改 callback 函数 `opts.xxx` 字段来源不 grep 所有 caller (PR #46 坑, 看错参数) (§5.17)
- ❌ 改 distId 格式不改 `_member_to_uid` / `_compute_max_synthetic_dist_id_from_db` / commit_preview 分配逻辑 (§5.18)
- ❌ preview 跟 commit 用不同编号计数器 (会导致 distId +2 跳号) (§5.19)
- ❌ setUp 已 seed root, 测试内再二次清 (会把 root 也删了, 触发找不到父) (§5.20)
- ❌ 新表的 sample data seed 放在 startup hook (不幂等, 客户 UAT 跑一段时间就 unique 约束炸) — 放 GET 端点幂等 check (§5.35)
- ❌ 联动逻辑 (A 改 → B 自动改) 放后端 PATCH (会让客户失去"我到底改了啥"的控制感) — 联动只能前端做 (§5.35)
- ❌ 派生数据 (单字段可推算的) 存 DB (4 字段改一个要 trigger 3 个派生字段, schema 复杂) — server 实时算 + 前端实时算 (§5.35)

---

## 10. 已知问题 (跟代码逻辑无关, 暂时不修)

- `tests/test_write_to_disk.py` 9 ERROR — 依赖 gitignored `json/Tree_empty_5_3.json` fixture
- GitHub push 经常 connection reset — 重试即可
- 38080 server 偶尔 Stop-Process 失败 (Idle PID 0) — 忽略, 端口 TimeWait 后会释放
- SQLite Windows 文件锁 — worktree 跟主仓同时跑 server 可能撞, 一般 port 区分就好

---

## 11. 测试不要污染 live DB (2026-07-27 PR #68 教训)

**问题**: 测试 setUp 跟 fixture 直接打到 live DB, 跑完留下 N-7* + parent="N-PARENT" 测试垃圾数据, root 被删了
- 业务影响: 批量添加 / 任何算法都找不到 root, 报 "挂入点 #3 跟 #1 同 batch 同一槽位 (N5637590.1 L1)"
- 根因: `tests/test_settle_e2e.py._add_member` 用 `parent_dist_id="N-PARENT"` 假父, setUp `db.query(...).delete()` 直接清 live DB
- 修复: 已清理 live DB + re-seed root (`python tools/init_root_member.py`)

**Rule**:
- **测试必须在 worktree 里跑** + **worktree 复制 data/ 从主仓**:
  ```powershell
  git worktree add -b feat-xxx .worktrees/feat-xxx main
  New-Item -ItemType Directory -Path .worktrees\feat-xxx\data -Force
  Copy-Item data\rewarddb.db .worktrees\feat-xxx\data\rewarddb.db
  ```
- 不复制 data/ → pytest 跑 `tests/test_settle_e2e.py` 会清 live DB, 删掉 root + 写入 N-7 fixture
- 如果已经污染: `python tools/init_root_member.py` 幂等重新 seed root
- `database.py` 用 `os.path.dirname(__file__)+"/data"` (绝对路径), worktree 跑测试自动用 `.worktrees/feat-xxx/data/`, 不污染主仓

**测试基础设施 TODO** (后续大改):
- `tests/test_settle_e2e.py` setUp 应该用 `REWARDDB_DB_URL=:memory:` 或 tmpfile DB, 不打 live DB
- 当前是历史遗留, 改起来 risk 较大, 暂用 worktree 隔离

---

## 12. UAT 打包规则 (2026-07-27 用户拍板)

- **改完代码不主动重打 `outputs/RewardAgentAnalysis-UAT-v0.1.zip`**
- 等用户说"打包" / "重打" / "rebuild" 才跑 `python tools/build_uat_zip.py`
- 业务原因: 用户可能连续改多个 PR, 一次打最终包, 避免中间过程白打包
- 跑完 PR 工作流 (commit + push + PR + merge) 后**不**自动跑 build_uat_zip.py
- 主动跑的例外: 用户明确指示要打包 (e.g. "打 UAT 包" / "出客户包")
- 当前 UAT 包状态: `outputs/RewardAgentAnalysis-UAT-v0.1.zip` (323KB, 含 PR #68 修复)

---

> 维护人: Justin Li (YuLi517)
> 最后更新: 2026-07-27 (PR #70 下单管理 — §2.12 业务规则 + 8 个 sample 活性辅酶/辅酶奥米加/钙镁健骨/葡萄籽/超级水果素/健儿素/田园果蔬饮/日夜纤 合计 ¥35162 + 需求↑则库存按差量减少 (前端联动, 公式 stock_new = stock_orig - (req_new - req_orig)) + 显式「保存」按钮 + §5.35 7 个新踩坑教训)

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes_tool` or `query_graph_tool` instead of Grep
- **Understanding impact**: `get_impact_radius_tool` instead of manually tracing imports
- **Code review**: `detect_changes_tool` + `get_review_context_tool` instead of reading entire files
- **Finding relationships**: `query_graph_tool` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview_tool` + `list_communities_tool`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes_tool` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context_tool` | Need source snippets for review — token-efficient |
| `get_impact_radius_tool` | Understanding blast radius of a change |
| `get_affected_flows_tool` | Finding which execution paths are impacted |
| `query_graph_tool` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes_tool` | Finding functions/classes by name or keyword |
| `get_architecture_overview_tool` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes_tool` for code review.
3. Use `get_affected_flows_tool` to understand impact.
4. Use `query_graph_tool` pattern="tests_for" to check coverage.
