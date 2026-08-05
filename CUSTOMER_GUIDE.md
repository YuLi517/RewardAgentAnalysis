# RewardAgentAnalysis 客户使用指南

> 5 叉树网体 commission 系统
>
> **版本**: UAT v0.1 (2026-07-21)
> **适用客户**: 业务方 UAT 测试团队

---

## 📖 目录

1. [产品简介](#1-产品简介)
2. [5 分钟上手](#2-5-分钟上手)
3. [核心功能](#3-核心功能)
4. [业务规则速查](#4-业务规则速查)
5. [角色说明](#5-角色说明)
6. [常见操作 FAQ](#6-常见操作-faq)
7. [数据备份与恢复](#7-数据备份与恢复)
   - [7.4 原版网体数据迁移 (PR #17)](#74-原版网体数据迁移-pr-17)
8. [故障排查](#8-故障排查)
9. [反馈渠道](#9-反馈渠道)

---

## 1. 产品简介

### 1.1 这是什么

RewardAgentAnalysis 是一个**网体 member/commission 管理系统**, 用 5 叉树组织会员层级, 自动按周结算 commission (佣金).

| 关键概念 | 含义 |
|---|---|
| **5 叉树** | 每个 member 最多有 5 个直接下级 (line 1-5) |
| **9 层** | 树的最深深度 9 层 (line 1+2 默认开, 满 9 层解锁 line 3+4, 都满再开 5) |
| **commission** | 15% × MIN(MAX 子区 PV, SUM 其余 4) [基本] + 7 层对等 `[0.15, 0.10, 0.05×5]` |
| **PV** | 个人业绩值, 周结算时消费累积成 commission |
| **业务周** | Sun 00:00 → Fri 23:59 (6 天) + Sat-Mon 补录窗口 (3 天) |

### 1.2 谁在用

- **业务方** (UAT 客户): 录入新 member, 录入 PV, 触发周结算, 查 commission
- **运营/管理者**: 看 commission preview, 看历史结算记录, 重置测试数据

### 1.3 浏览器访问

启动后访问 <http://localhost:28080>, 看到**欢迎屏** + 4 个功能卡片 (成员/树视图/批量/管理).

---

## 2. 5 分钟上手

### 2.1 启动 (Windows)

1. 双击 `start_uvicorn.bat`
2. 等 3-5 秒, 看到 `Uvicorn running on http://0.0.0.0:28080` 就 OK
3. 浏览器打开 <http://localhost:28080>

> 提示: 首次启动会自动建 `data/rewarddb.db` (SQLite 数据库), 不用手工建.

### 2.2 启动 (macOS / Linux)

```bash
cd RewardAgentAnalysis
pip install -r requirements.txt
python main.py
# 浏览器打开 http://localhost:28080
```

### 2.3 验证启动

打开 <http://localhost:28080>, 应该看到:
- 欢迎屏 (大标题 "RewardAgentAnalysis")
- 4 个功能卡片
- 顶部状态栏: 当前业务周 + 状态 (open/settled)

如果看到 "Internal Server Error" 或白屏, 看 [§8 故障排查](#8-故障排查).

### 2.4 重置测试数据

业务方 UAT 反复试算法时, 节点加多了想"回到初始状态":
- 点工具栏右上角 **🗑️ 重置** 按钮
- 二次确认 (浏览器弹窗)
- 几秒后回到 "只有 root" 的初始状态

> ⚠️ 重置会删除所有非 root member + 所有 PV 流水 + 所有结算期. **不可恢复**.

### 2.5 首次部署：导入原版网体数据 (PR #17)

启动 server 后, 数据库是空的 (只有 schema, 没有原版网体节点). 访问 `http://localhost:28080/original-tree` 会看到 "API 数据空" 错误.

**首次部署必跑 1 步**:

```bash
# Windows
python tools/migrate_original_tree.py --yes

# macOS / Linux
python3 tools/migrate_original_tree.py --yes
```

跑完会显示 "303 节点 12 层" + 业务字段分布, 刷新浏览器即可看到原版网体.

> `--yes` 表示自动全清 5 张业务表 (原版网体 + 5 叉树 commission + 下单), 首次部署用这个最干净.
> 想交互式选清空范围? 跑 `python tools/migrate_original_tree.py` (不带参数) 看菜单. 详见 [§7.4 原版网体数据迁移](#74-原版网体数据迁移-pr-17).

---

## 3. 核心功能

### 3.1 树视图 (主功能)

**入口**: 欢迎屏 → "🌳 树视图" 卡片 (或工具栏按钮)

**展示**:
- 5 叉树可视化, root (王常军 N5637590.1) 居中
- 9 层深度, 满员/未挂入用颜色区分
- 每个 node (member) 是一张**名片**, 显示:
  - 姓名 + distId
  - 角色徽章 (7 角色 + 颜色)
  - **本期 PV** (绿): 本周新增 PV (settled 后自动隐藏)
  - **剩余 PV** (黄): 跨期累积的 PV
  - **累计 $** (金): 历史 settle 后的总 commission
  - **本期可拿** (紫): 本期 PV 出现后, 父节点实时算出的预计 commission (仅在 open 期显示)
  - L1-L5 标识 (5 叉树第几条线)
  - "🔒" 锁: line > 当前 eff (不可挂入)

**操作**:
- **点击 node**: 展开/折叠子节点
- **拖动 canvas**: 按住 canvas 空白处拖动, 平移视图
- **滚轮**: 缩放

### 3.2 批量添加 member

**入口**: 工具栏 **➕ 批量添加** 按钮

**用法**:
- 默认 3 行, 表格化输入 (姓名 / PV / 角色 / 删除)
- Tab 跳列, Enter 加行, 最后一行 Enter 提交
- 严格校验: 姓名空 / PV 非数字 → 红框 + 阻止提交
- 提交按钮实时显示有效行数: `批量挂入并写盘 (3 位)`

**角色下拉** (7 个):
- 消费股东 (默认)
- 预备合伙人
- 合伙人员工
- 初级管理合伙人
- 中级管理合伙人
- 高级管理合伙人
- Inactive

> **小技巧**: 一次加 5 个, 看 commission preview 紫色徽章实时变化.

### 3.3 单加 member

**入口**: 工具栏 **➕ 单加** 按钮

适合临时单加一个, 走完批量流程 (输入姓名 + PV + 角色 + 提交).

### 3.4 期间结算 (主结算)

**入口**: 工具栏 **💰 结算本周** 按钮 (金色)

**何时可点**:
- 当前业务周状态 = `open` (Sun-Fri 期间)
- 按钮可点

**点了之后**:
- 算本期所有 member 的 basic commission (own + 7 层对等)
- 落账到 `members.total_commission`
- 期 PV 处理:
  - 一部分被配对消耗 (→ commission)
  - 一部分 carry 余额 (→ `current_pv_balance`, 显示在"剩余 PV"黄徽章)
- 期间状态: `open` → `settled`

### 3.5 补录 commission (Sat-Mon 补录窗口)

**入口**: 工具栏 **📝 补录** 按钮 (蓝紫色, **只在 Sat-Mon** 显示)

**业务规则**:
- 业务周 (Sun-Fri) 结束后, Sat 00:00 → Mon 23:59 是**补录窗口** (3 天)
- 补录**只能补基本 commission** (own × 15%)
- **跳过 7 层对等** (对等链已冻结, 不能再分润)
- Mon 23:59 之后, 期间状态 → `closed`, 不能再补

**适用场景**:
- 周五漏录一个 member 的 PV
- 想让某个 member 在历史已 settled 的周里"补一笔" commission

### 3.6 批量重置测试数据

**入口**: 工具栏 **🗑️ 重置** 按钮 (警示红)

**二次确认** (防误点):
- 浏览器弹窗列出会删/会留的项
- 确认后执行

**保留**:
- root (王常军 N5637590.1), 字段重置 (carry=0, commission=0, last_period=NULL)

**删除**:
- 所有非 root member
- 全部 PV 流水
- 全部结算期 (然后重建当前期)

### 3.7 commission 实时预览 (本期可拿)

**业务规则**:
- 当子节点本期 PV 出现后, **父节点**实时显示能拿的 commission
- 计算公式跟 `settle_period` 完全一致:
  - own basic = MIN(MAX 子区 PV, SUM 其余 4) × 15%
  - pair bonus = 7 层对等 `[0.15, 0.10, 0.05×5]`
- 紫色徽章 "本期可拿 ¥X.XX", 仅在 `open` 期显示
- tooltip 分解: `own basic: ¥X + 7层对等 pair: ¥Y = ¥Z`
- settled 期自动隐藏 (已落账, 不算 preview)

**示例**:
- root 有 2 个子, z1=500, z2=300
- MIN(500, 300) = 300, basic = 300 × 15% = ¥45
- root 名片显示 "本期可拿 ¥45.00"

---

## 4. 业务规则速查

### 4.1 树结构

- **5 叉树**: 每个 member 最多 5 个直接下级
- **9 层深度**: 树最深 9 层 (不算 root)
- **default eff = 2**: root 默认只能往 line 1 + line 2 挂人
- **line 1+2 都满 9 层** → eff = 4 (line 3+4 解锁)
- **line 1-4 都满 9 层** → eff = 5 (line 5 解锁)
- "line 满" = 该 line 父节点下有 9 层子孙 (不含 line 自己)

### 4.2 业务周 (PR #55)

| 时间窗口 | 期间状态 | 可操作 |
|---|---|---|
| **Sun 00:00 - Fri 23:59:59.999** (6 天) | `open` | 挂 member / 主结算 |
| **Sat 00:00 - Mon 23:59:59.999** (3 天) | `settled` (期已主结算) | **只能补录基本 commission** |
| **Tue 00:00 起** | `closed` | 不能再补 |

**业务 W 编号**: 沿用 ISO W 数字, 但范围是 Sun-Fri.
- 例: 业务 W29 = 2026-07-12 (Sun) ~ 2026-07-17 (Fri)
- 跟 ISO W29 (Mon-Sun) 不一样

### 4.3 commission 计算

**基本佣金** (own):
- 每个父节点: `MIN(MAX 子区 PV, SUM 其余 4 个子区 PV) × 15%`
- 例: 子区 PV = [500, 300, 200, 100, 0], MAX=500, SUM 其余=600, MIN(500, 600)=500, basic = 500 × 15% = ¥75

**7 层对等配对 commission** (pair bonus):
- 每个子孙节点的 own basic × ratio 分给 1/2/3/4/5/6/7 代祖先
- ratios = `[0.15, 0.10, 0.05, 0.05, 0.05, 0.05, 0.05]`
- 总和 = 0.5 (一半 own 给祖先, 一半留自己)

**carry (剩余 PV)**:
- 配对 commission 消耗 PV 的一部分
- 剩余的 PV 累积到 `current_pv_balance`, 显示在"剩余 PV"黄徽章
- 跨期 carry (下一期可继续配对)

### 4.4 member 编码

- **格式**: `N5637590.X` (X = DB id 序号, root=1, 其他 +1 连续)
- 例: 王常军 `N5637590.1`, z1 `N5637590.2`, z2 `N5637590.3`

### 4.5 数据约束

- **PV**: 正整数 (1, 50, 99, 100, 任意整数), 业务上没上限
- **姓名**: 必填, 任意非空字符串
- **角色**: 7 选 1, 默认"消费股东"

---

## 5. 角色说明

| 角色 | 颜色 | 业务含义 | 适用场景 |
|---|---|---|---|
| **消费股东** | 浅蓝 #BFDBFE | 普通消费型股东 | 入门 member, 默认角色 |
| **预备合伙人** | 浅绿 #BBF7D0 | 候选合伙人 | 有意向转合伙人的 member |
| **合伙人员工** | 浅紫 #DDD6FE | 合伙人体系下的员工 | 合伙人带的下属 |
| **初级管理合伙人** | 浅橙 #FED7AA | 初级管理岗 | 团队规模 5-10 人 |
| **中级管理合伙人** | 浅粉 #FBCFE8 | 中级管理岗 | 团队规模 10-30 人 |
| **高级管理合伙人** | 浅红 #FECACA | 高级管理岗 | 团队规模 30+ 人 |
| **Inactive** | 浅灰 #E5E7EB | 不活跃 member | 暂时离场 / 历史 member |

**作用**:
- 名片 role 徽章颜色对照
- 业务上仅做标识, **不影响 commission 计算** (commission 只看 PV + 树结构)

---

## 6. 常见操作 FAQ

### Q1: 怎么加一个 member?

**单加**: 工具栏 → **➕ 单加** → 输入姓名 + PV + 选角色 → 提交
**批量**: 工具栏 → **➕ 批量添加** → 表格输入多行 → 提交

### Q2: PV 可以输入小数吗?

不可以, PV 必须是**正整数** (1, 50, 99, 100, 任意整数). 输入小数会报红框.

### Q3: 怎么快速调整 PV 值?

每个 PV 输入框右侧有 **+/-** 按钮 (跳 100), 跟 native number spinner 一致:
- **+** 在上, **-** 在下 (PR #62 跟 native 一致)
- 点一下加/减 100
- 也可直接输入任意整数 (PR #59 自由输入)

### Q4: 怎么看历史 commission?

点工具栏右上角 **📜 期间列表** 按钮, 列出所有历史业务周.
点某个期, 看 summary (本期所有 member 的 commission + 配对明细).

### Q5: 怎么改 member 的 PV?

当前版本 (v0.1) 不支持改历史 PV. 如需修改, 重置该 member 后重新录入.

### Q6: 怎么删一个 member?

当前版本不支持单删. 用 **🗑️ 重置** 一键回到初始状态, 然后重新加需要的 member.
(单删功能在排期, 见 §9 反馈渠道)

### Q7: 为什么我加了 member, 但 commission preview 紫色徽章不显示?

可能原因:
1. **当前期间已 settled**: 紫色徽章只在 `open` 期显示. 检查工具栏当前期间状态.
2. **PV 为 0 或太小**: 0 commission 不显示徽章.
3. **父节点超过 7 层**: 7 层对等只到 7 代祖先, 8 代以上不参与.

### Q8: 怎么知道本周是 open 还是 settled?

工具栏右上角显示当前业务周 + 状态 (open/settled/closed):
- **open**: 绿色, 可挂 member, 可主结算
- **settled**: 黄色, 已主结算, 可补录 (Sat-Mon)
- **closed**: 灰色, 补录截止

### Q9: commission 计算的 "MAX 子区 PV" 怎么理解?

5 叉树每个父节点有 5 个子区 (line 1-5), 每个子区 PV = 该子区所有子孙 PV 之和.
- 例: 子区 PV = [500, 300, 200, 100, 0]
- MAX = 500 (line 1), SUM 其余 4 = 300+200+100+0 = 600
- MIN(500, 600) = 500
- basic = 500 × 15% = ¥75

### Q10: 为什么 7 层对等不算 deepseek 那种 AI commission?

这是按 7 代祖先链静态分润, 不是 AI 模型打分. 设计原则:
- **前 2 代** 拿大头 (15%, 10%)
- **3-7 代** 均分 5% × 5
- 总和 50%, 50% 留给 own (自身消耗 PV)

### Q11: 数据存在哪?

SQLite 文件 `data/rewarddb.db`. 整个数据库一个文件, 备份 = 复制这个文件.

### Q12: 能不能多个人同时用?

当前 v0.1 是单机版, SQLite 文件锁. 多窗口同时操作可能撞锁 (后台有兜底).
正式版 (v0.2+) 计划支持多用户 + 权限.

### Q13: 我能导出 commission 明细吗?

工具栏 **📥 导出** 按钮 (后续 PR 加) — 导出 CSV.
当前可用 API: `GET /api/period/{id}/summary` 拿 JSON 原始数据.

### Q14: 怎么从测试数据切到正式数据?

正式部署建议:
1. **保留 root**: root distId 不能变
2. **清空测试 member**: 点 🗑️ 重置
3. **改 root 字段**: 通过 `data/rewarddb.db` 直接改, 或后续管理界面
4. **重置期间**: 重置会自动重建当前期

### Q15: 我看到 "Line 1+2 都满 9 层" 但 L3 还是锁的, 为什么?

"满 9 层" = 该 line 父节点下有 9 层子孙 (不含 line 自己).
- 例: root.line1 父节点 = root (depth 0), 子孙 = line1.depth 1-9 → 满
- 但要 line1 + line2 **都**满才解锁 line3+4
- 重新点 🔄 刷新按钮, 看看状态

### Q16: "本期 PV" 绿徽章 跟 "剩余 PV" 黄徽章 区别?

| 徽章 | 颜色 | 含义 | 何时显示 |
|---|---|---|---|
| **本期 PV** | 绿 | 本周新增 PV | `open` 期, > 0 时 |
| **剩余 PV** | 黄 | 跨期累积 PV (carry) | 任意期, > 0 时 |
| **累计 $** | 金 | 历史 settle 后的总 commission | 任意期, > 0 时 |
| **本期可拿** | 紫 | 本期 PV 模拟算的 commission | `open` 期, > 0 时 |

settled 期绿/紫徽章**自动隐藏** (已落账, 不算 preview).

---

## 7. 数据备份与恢复

### 7.1 备份 (3 种方式)

**方式 1: 复制 db 文件** (最简单)
```bash
# 停 server
# 复制 data/rewarddb.db 到备份目录
cp data/rewarddb.db backup/rewarddb_2026-07-21.db
# 启 server
```

**方式 2: 导出 JSON** (跨平台)
```bash
# 浏览器打开
http://localhost:28080/api/admin/tables/members
http://localhost:28080/api/admin/tables/pv_ledger
http://localhost:28080/api/admin/tables/commission_periods
# 另存为 JSON 文件
```

**方式 3: 工具栏导出** (后续 PR)

### 7.2 恢复

```bash
# 停 server
# 覆盖 db 文件
cp backup/rewarddb_2026-07-21.db data/rewarddb.db
# 启 server (会自动跑 migration)
```

### 7.3 自动备份建议

每周 (Fri settle 之后) 手动复制 `data/rewarddb.db` 到:
- 网盘 (OneDrive / Google Drive / 阿里云盘)
- 另一台机器
- 邮件附件给自己

正式版 (v0.2+) 计划加 cron 自动备份.

### 7.4 原版网体数据迁移 (PR #17)

`tools/migrate_original_tree.py` 是原版网体 (303 节点 12 层深) 数据迁移工具, 把 `json/original_tree.json` 导入到 SQLite `original_tree_nodes` 表.

**首次部署**: 详见 [§2.5 首次部署](#25-首次部署导入原版网体数据-pr-17), 跑 `--yes` 一次性导入.

**后续运维**: 当你需要换 JSON 数据集, 或者想"全部清空重新开始", 用这个工具.

#### 7.4.1 什么时候用?

| 场景 | 推荐命令 |
|---|---|
| **首次部署** (数据库是空的) | `python tools/migrate_original_tree.py --yes` |
| **换 JSON 数据集** (新数据要替换整树) | 替换 `json/original_tree.json`, 然后跑 `--yes` |
| **原版网体数据有误** (想重置) | `--net` (只清原版网体, 业务表保留) 或 `--yes` (全清) |
| **测试期间反复折腾, 想一键回初始** | `--yes` 全清 (包括 commission 业务数据) |
| **不确定, 想看清楚再决定** | `python tools/migrate_original_tree.py` (无参数, interactive 菜单) |

#### 7.4.2 Interactive 模式 (推荐新用户)

不带任何参数, 显示菜单让你选:

```bash
python tools/migrate_original_tree.py
```

输出:
```
============================================================
即将导入原版网体 JSON 到 DB. 请选择清空范围:
============================================================

  [1] 全清 — 5 张业务表都清空 (推荐 UAT 客户)
      original_tree_nodes + members + pv_ledger
      + commission_periods + order_items

  [2] 只清原版网体 — 不动其他业务表
      (members / pv_ledger / commission_periods / order_items 保留)

  [3] 取消 — 退出不执行

请输入选项 [1/2/3]:
```

输入 `1` / `2` / `3` 后回车, 工具自动执行 (打印详细进度 + 验证 stats).

**适用**: 不熟悉 CLI 的客户 / 不确定清空范围时 / 想看看当前 DB 状态再决定.

#### 7.4.3 CLI 模式 (熟悉后推荐)

| 命令 | 行为 |
|---|---|
| `python tools/migrate_original_tree.py --yes` | **自动全清 5 张业务表** (跳过询问, 推荐 UAT 客户) |
| `python tools/migrate_original_tree.py --net` | **只清原版网体**, 其他业务表保留 (跳过询问) |
| `python tools/migrate_original_tree.py --db-path <path>` | 自定义 DB 路径 (默认 `data/rewarddb.db`) |
| `python tools/migrate_original_tree.py --json-path <path>` | 自定义 JSON 路径 (默认 `json/original_tree.json`) |
| `python tools/migrate_original_tree.py --help` | 显示完整帮助 |

**例子**:

```bash
# 全自动 (UAT 客户推荐, 跳过询问)
python tools/migrate_original_tree.py --yes

# 只想清原版网体, 业务数据保留
python tools/migrate_original_tree.py --net

# 换数据集: 替换 json/original_tree.json 后跑 --yes
# (Windows)
copy new_tree.json json\original_tree.json
python tools/migrate_original_tree.py --yes

# 备份/迁移到另一台机器: 自定义路径
python tools/migrate_original_tree.py --db-path D:\backup\rewarddb.db --json-path D:\new_data\tree.json
```

#### 7.4.4 清空范围怎么选?

| 业务表 | 全清 (`--yes` / 选 1) | 只清原版网体 (`--net` / 选 2) |
|---|:---:|:---:|
| `original_tree_nodes` (原版网体) | ✓ 清 | ✓ 清 |
| `members` (5 叉树 commission 成员) | ✓ 清 | ✗ 保留 |
| `pv_ledger` (业务 PV 流水) | ✓ 清 | ✗ 保留 |
| `commission_periods` (业务周期) | ✓ 清 | ✗ 保留 |
| `order_items` (下单管理) | ✓ 清 | ✗ 保留 |

**选 1 (全清) 适用**:
- 首次部署
- 换数据集 (整树替换)
- 全部数据要重置 (测试折腾后回初始)

**选 2 (只清原版网体) 适用**:
- 原版网体数据错了, 但业务数据 (members / pv_ledger) 还想保留
- 多个 net-tree 切换展示, 但 commission 业务数据不变

**选 3 (取消) 适用**:
- 误启动, 不想执行
- 临时查 DB 状态, 不想动数据

#### 7.4.5 工具会做什么 (4 步)

不管 `--yes` / `--net` / interactive, 工具都执行这 4 步:

1. **建表 + 索引** (幂等, 表已存在跳过)
   - `original_tree_nodes` 25 列 (字段对齐 JSON 节点)
   - `idx_original_tree_parent` 索引 (parent_id 查询性能)
2. **清空** — 根据清空范围 DELETE 1 张或 5 张表
3. **导入** — 递归 BFS 读 JSON, 顶层 `parent_id = NULL` (业务: "最上面的 Root 节点算 L0")
4. **验证** — 输出:
   - 节点总数
   - depth 分布 (depth 0=root, depth 1=L1 父, ...)
   - businessLevel 分布 (ULTIMATE/ELITE/BUSINESS/MEMBER)
   - 顶层 root 节点 (distId + name + level)
   - FK 完整性 (parent_id 必须存在)

示例输出:
```
[1/5] 当前 DB 状态
  original_tree_nodes          303 行  -- 原版网体节点
  members                       24 行  -- 5 叉树 commission 成员
  pv_ledger                     23 行  -- 业务 PV 流水
  commission_periods             1 行  -- 业务周期
  order_items                    8 行  -- 下单管理

清空范围: 全清 (5 张业务表)

[2/5] 建表 + 索引
  original_tree_nodes 字段数: 25

[3/5] 清空表
  DELETE FROM original_tree_nodes: 303 行
  DELETE FROM members: 24 行
  DELETE FROM pv_ledger: 23 行
  DELETE FROM commission_periods: 1 行
  DELETE FROM order_items: 8 行

[4/5] 导入 JSON
  插入: 303 行
  max depth: 12 (13 层 = 0..12)
  businessLevel 分布: {'ULTIMATE': 232, 'ELITE': 2, 'BUSINESS': 20, 'MEMBER': 47, '(NULL)': 2}
  顶层 root: dist_id=A8066781.1, name=万陵洋, level=1, business_level=ULTIMATE

[5/5] 验证
  总节点: 303
  顶层 (parent_id IS NULL): 1
  有父: 302
  FK 失效 (parent_id 不在表内): 0

migration 完成
```

#### 7.4.6 常见问题

**Q: 跑完发现数据不对, 能撤销吗?**
A: 不能. 工具是 DELETE + INSERT, 清空就是真清空. **跑之前先备份 `data/rewarddb.db`** (复制一份到别处). 想撤回就 `cp backup/rewarddb.db data/rewarddb.db` 覆盖回去.

**Q: 多次跑 `--yes` 安全吗?**
A: 安全, 幂等. 每次跑都是先清空后插入, 节点数 / 字段值完全一致. JSON 文件不变, 跑多少次结果都一样.

**Q: 我换了 JSON 文件, 但跑完原版网体没变化?**
A: 检查:
1. JSON 文件是否真的替换了 (`ls -la json/original_tree.json` 看修改时间)
2. JSON 文件结构是否正确 (顶层是 dict, 包含 `children` 数组, 每节点有 `distId` 字段)
3. 跑完看输出, 节点数 / depth 分布 / 顶层 root distId 是否跟新 JSON 一致

**Q: 工具报 "DB 不存在" 错误?**
A: `data/rewarddb.db` 还没创建. 先跑 `python main.py` 启动 server (会自动建 db), 停掉 server, 再跑 migration.

**Q: 工具报 "JSON 不存在" 错误?**
A: `json/original_tree.json` 缺失. UAT 包默认带这个文件. 如果缺失, 找开发者要, 或参考 [README.md §数据迁移](../README.md#-数据迁移-pr-17).

**Q: 跑完浏览器还显示旧数据?**
A: 浏览器缓存, 强制刷新 `Ctrl+Shift+R` (Windows) / `Cmd+Shift+R` (macOS).

**Q: 我只清原版网体, 但 commission 业务数据还在, 会不会有 FK 问题?**
A: 不会. `original_tree_nodes` 表跟其他业务表**没有 FK 关联** (各自独立), 清空互不影响. commission 业务跑自己的 5 叉树, 原版网体跑自己的 12 层, 数据完全隔离.

#### 7.4.7 数据安全

- **跑 migration 前**, 建议备份当前 `data/rewarddb.db`:
  ```bash
  cp data/rewarddb.db data/rewarddb_backup_$(date +%Y%m%d_%H%M%S).db
  ```
- **跑 migration 后**, 看到 "FK 失效 > 0" 警告 = JSON 数据有孤儿节点 (parentId 引用不存在的父), 检查 JSON 文件
- **业务侧不能动 `json/original_tree.json` 之外的事**: 改 JSON 跑 migration 只会更新原版网体, 不影响 commission 业务

#### 7.4.8 客户使用流程汇总

**首次部署 (一次性)**:
```bash
# 1. 装依赖
pip install -r requirements.txt

# 2. 启动 server (建 db)
python main.py
# Ctrl+C 停掉

# 3. 导入原版网体
python tools/migrate_original_tree.py --yes

# 4. 重启 server
python main.py

# 5. 浏览器访问
# http://localhost:28080            # 5 叉树 commission
# http://localhost:28080/original-tree  # 原版网体
```

**换数据集**:
```bash
# 1. 替换 JSON
cp /path/to/new_tree.json json/original_tree.json

# 2. 重跑 migration
python tools/migrate_original_tree.py --yes

# 3. 浏览器 Ctrl+Shift+R 强制刷新
```

**重置原版网体 (业务数据保留)**:
```bash
python tools/migrate_original_tree.py --net
# Interactive 模式选 2
```

**全清重置 (回到初始状态)**:
```bash
python tools/migrate_original_tree.py --yes
# Interactive 模式选 1
# 注意: 会清掉所有 5 叉树 commission 数据
```

---

## 8. 故障排查

### 8.1 启动失败: "Address already in use"

**原因**: 28080 端口被占用
**解决**:
```bash
# 找出占用进程
netstat -ano | findstr :28080    # Windows
lsof -i :28080                    # macOS/Linux

# 停掉, 或换端口启动
python main.py --port 8001
```

### 8.2 启动失败: "No module named 'fastapi'"

**原因**: 依赖没装
**解决**:
```bash
pip install -r requirements.txt
```

### 8.3 浏览器白屏 / "Internal Server Error"

**排查**:
1. 看 server 控制台日志 (uvicorn.err.log 或 start_uvicorn.bat 窗口)
2. 看 `data/rewarddb.db` 文件锁 (是否多个 server 进程在跑)
3. 浏览器 DevTools → Network → 找 5xx 响应 → 看 Response body

### 8.4 数据看起来不对

**常见**:
- **"PV 算少了"**: 检查 carry (剩余 PV) — settle 后 PV 一部分消耗配对, 一部分 carry
- **"commission 不对"**: 确认期间状态 (open/settled/closed), 补录 commission 只算 own 不算 pair
- **"成员没出现"**: 检查 line 是否解锁 (L3+ 需要 L1+L2 都满 9 层)

**重置**: 点 **🗑️ 重置** 回到初始状态, 重新试.

### 8.5 数据库锁 "database is locked"

**原因**: 多 server 进程 / 多浏览器同时操作
**解决**:
1. 关掉所有 server 进程
2. 关掉多余浏览器窗口
3. 重新启动一个 server

### 8.6 想要 chat 功能 (/chat /sessions)

**当前**: chat 端点需 LLM key, **默认未启用**
**启用**:
1. `cp .env.example .env`
2. 编辑 .env, 填入 LLM key:
   ```
   LLM_PROVIDERS=deepseek
   DEEPSEEK_API_KEY=sk-...
   DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
   DEEPSEEK_MODEL=deepseek-chat
   ```
3. 重启 server
4. 浏览器访问 /chat 端点

> UAT 阶段不推荐启用 chat, 业务方只测 commission 系统.

---

## 9. 反馈渠道

### 9.1 Bug 报告

发现 bug, 请记录:
1. **现象**: 看到了什么 (截图 + 操作步骤)
2. **预期**: 应该是什么
3. **环境**: 操作系统 / 浏览器 / 启动方式
4. **日志**: `uvicorn.err.log` 内容 (如有)
5. **数据状态**: 哪几个 member, 哪个期间, 什么操作

发给: **Justin Li** (raincoatliyu@163.com / 134-6636-7329)

### 9.2 功能建议

记录:
1. **场景**: 什么业务场景下需要
2. **方案**: 期望怎么实现
3. **优先级**: 紧急 / 重要 / 一般

发给: 同上.

### 9.3 紧急联系

业务关键 bug (commission 算错 / 数据丢失 / 系统挂了):
- **电话**: 134-6636-7329
- **微信**: raincoatliyu
- **邮件**: raincoatliyu@163.com

---

## 📌 附录

### A. 快捷键 (UI)

| 键 | 作用 |
|---|---|
| **Tab** | 跳到下一个 input (在批量添加表格里跳列) |
| **Enter** | 在批量添加最后一行 = 提交, 其他行 = 加新行 |
| **Esc** | 关闭 modal |
| **Ctrl + R** | 刷新树视图 |

### B. 浏览器兼容

| 浏览器 | 版本 | 支持 |
|---|---|---|
| Chrome | ≥ 100 | ✅ 推荐 |
| Edge | ≥ 100 | ✅ 推荐 |
| Firefox | ≥ 100 | ✅ |
| Safari | ≥ 15 | ✅ |
| IE | 任意 | ❌ 不支持 |

### C. 默认配置

- **Server**: `0.0.0.0:28080`
- **DB**: `data/rewarddb.db` (SQLite, gitignored)
- **期间**: 业务周 Sun-Fri (PR #55)
- **角色**: 7 个 (PR #42)
- **commission rate**: 15% (own)
- **配对 ratio**: `[0.15, 0.10, 0.05×5]` (1-7 代)
- **5 叉树 9 层**: root eff=2, 满层解锁 4, 再满 5

### D. 客户文档版本

| 版本 | 日期 | 改动 |
|---|---|---|
| UAT v0.1 | 2026-07-21 | 初版 (PR #63 配套) |

---

> 维护: Justin Li (YuLi517)
> 反馈: raincoatliyu@163.com / 134-6636-7329
