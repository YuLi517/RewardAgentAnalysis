# RewardAgentAnalysis —— 5 叉树网体 commission 系统

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688)](https://fastapi.tiangolo.com)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.x-orange)](https://sqlalchemy.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> **业务系统** (网体 5 叉树 9 层 member/commission 结算平台 + 原版网体可视化)
>
> 业务侧只跑 commission + 原版网体两条主线 (commission 系统 + 原版网体 vertical 布局 + minimap).
> 历史 Stage 2/3 残留的 LLM 路由 (`/chat` `/sessions` `/v1/models`) 仍保留代码但**完全 optional** —
> 不配 LLM key 业务正常跑, chat 端点返回 503.

---

## ⚡ 30 秒快速开始

### 业务侧 (commission 系统 + 原版网体, 客户 UAT 用这个)

```bash
# 1. 装依赖
pip install -r requirements.txt

# 2. 启动 (Windows 双击 start_uvicorn.bat 也行)
python main.py
# 首次启动自动创建 data/rewarddb.db

# 3. 导入原版网体数据 (PR #17, 一次性)
python tools/migrate_original_tree.py --yes
# 客户首次部署或换 JSON 数据集时跑 (幂等, 多次跑安全)

# 4. 浏览器
# http://localhost:38080            # 5 叉树 commission 系统
# http://localhost:38080/original-tree  # 原版网体 (303 节点 12 层, vertical 布局 + minimap)
```

### 启用 LLM 路由 (optional)

```bash
# 复制模板
cp .env.example .env
# 编辑 .env 填入 LLM key (deepseek / qwen / MiniMax 任选 ≥1 家)
# LLM_PROVIDERS=deepseek
# DEEPSEEK_API_KEY=sk-...
```

> chat 端点 (`/chat` `/sessions` `/v1/models`) 需 LLM key 才能用, **commission 系统不需要**.

---

## 🏗️ 业务架构

| 层 | 模块 | 说明 |
|---|---|---|
| **数据层** | `database.py` + `models.py` + `repository.py` | SQLAlchemy 2.x ORM + SQLite 持久化 (5 张业务表) |
| **API 层** | `main.py` | FastAPI 路由 + 树视图渲染 + 期间结算 + 原版网体数据接口 |
| **算法层** | `skills/` | 5 叉树按位反转 + 7 层对等 commission + 业务周 (Sun-Fri) + 补录窗口 |
| **UI 层** | `static/index.html` + `static/original_tree.html` | 5 叉树 commission UI (宋代配色) + 原版网体 vertical 布局 + 右侧 30% minimap |
| **工具层** | `tools/` | migration 脚本 (init_root_member / migrate_add_role / migrate_pr55_period_id / **migrate_original_tree**) |

### 核心业务规则

**commission 系统 (5 叉树 9 层)**:
- **5 叉树 9 层**: root 默认 eff=2, line 1+2 各满 9 层 → eff=4, line 1-4 都满 → eff=5
- **commission rate**: 15% × MIN(MAX 子区 PV, SUM 其余 4) [基本佣金]
- **7 层对等**: `[0.15, 0.10, 0.05×5]` 分给 1/2/3/4/5/6/7 代祖先
- **业务周 Sun-Fri** + **补录窗口 Sat-Mon** (业务 W 编号沿用 ISO W 数字)
- **期间状态**: `open` (Sun-Fri) → `settled` (主结算后) → `closed` (Tue 起, 补录截止)
- **补录 commission**: 只能补基本 (own × 15%), 跳过 7 层对等 (对等链已冻结)

**原版网体可视化 (PR #13/14/15/16)**:
- **数据源**: `json/original_tree.json` → SQLite `original_tree_nodes` 表 (PR #15)
- **303 节点 12 层深** + 业务 4 色 (ULTIMATE/ELITE/BUSINESS/MEMBER)
- **Root 节点算 L0** (PR #16, 业务规则: 顶层 depth=0 = L0, 不用 JSON `level` 字段)
- **vertical 布局** (PR #14): root 在顶, 4 L1 父水平排开, 子孙竖排向下
- **右侧 30% minimap** (PR #13): 一眼看全树 + 蓝框同步 + click → 主视图 pan/select

完整业务规则见 [AGENTS.md §2](AGENTS.md) (开发 agent 指南, 含 32 个踩坑教训).

---

## 📦 关键 API

| Method | Path | 用途 |
|---|---|---|
| GET | `/api/members` | 列所有成员 (含 PV/commission/角色) |
| GET | `/api/tree/render` | 5 叉树视图 HTML |
| POST | `/api/skill_5_3/commit_preview` | 算法预览 + 写盘 |
| GET | `/api/period/list` | 历史业务周 |
| POST | `/api/period/{id}/settle` | 主结算 / 补录 (`?supplement_only=true`) |
| POST | `/api/admin/reset_test_data?confirm=true` | 一键重置测试数据 |
| GET | `/api/original_tree/data` | 原版网体数据 (DB 读, 303 节点 12 层) |
| GET | `/original-tree` | 原版网体可视化页面 (vertical 布局 + minimap) |

完整 OpenAPI: <http://localhost:38080/docs>

---

## 🚀 启动方式

| 平台 | 方式 | 命令 |
|---|---|---|
| Windows | 双击 | `start_uvicorn.bat` |
| Windows | 后台 | `powershell tools/start_server.ps1` |
| macOS/Linux | 前台 | `python main.py` |
| macOS/Linux | 后台 | `nohup python main.py > uvicorn.out 2> uvicorn.err &` |

启动参数:
- `--host 0.0.0.0` (默认, 监听所有网卡, 局域网可访问)
- `--port 38080` (默认)
- `--reload` (开发模式, 改代码自动重启)

---

## 🧪 测试

```bash
# 全部测试 (258+ PASS)
python -m pytest tests/ -v

# 跑某个 PR
python -m pytest tests/test_pr62_song_color_scheme.py -v
```

---

## 📂 项目结构

```
RewardAgentAnalysis/
├── main.py                          # FastAPI app + API endpoints + 渲染层
├── models.py                        # SQLAlchemy ORM (Member, PVLedger, CommissionPeriod, OrderItem, OriginalTreeNode)
├── repository.py                    # DB CRUD
├── database.py                      # SessionLocal + get_db + init_db
├── requirements.txt
├── start_uvicorn.bat                # Windows 一键启动
├── .env.example                     # LLM key 模板 (optional)
├── AGENTS.md                        # 开发 agent 指南 (业务规则 + 32 个踩坑教训)
├── static/
│   ├── index.html                   # 5 叉树 commission UI (单文件)
│   ├── original_tree.html           # 原版网体可视化 (vertical + minimap, PR #13/14)
│   └── original_tree_minimap.css    # minimap 样式 (PR #13)
├── skills/                          # 算法核心
│   ├── skill_5_lib.py               # Node5 + 5 叉树基础库
│   ├── skill_5_3.py                 # 5 叉按位反转 BFS
│   ├── skill_5_helpers.py           # 共享 helper
│   ├── pair_commission.py           # 7 层对等 commission 结算
│   ├── period.py                    # 业务周 + ISO 周工具
│   └── skill_5_3_README.md          # skill 算法文档
├── tools/                           # migration + 启动脚本
│   ├── init_root_member.py          # PR #28 root 行
│   ├── migrate_add_role.py          # PR #41 role 列
│   ├── migrate_pr55_period_id.py    # PR #55 业务周 ID 格式
│   ├── migrate_original_tree.py     # PR #17 原版网体 JSON 迁 DB (interactive CLI)
│   └── start_server.ps1
├── tests/                           # 19 个 test_*.py (258+ cases)
├── data/
│   └── rewarddb.db                  # SQLite (gitignored, 首次启动自动建)
└── json/
    └── original_tree.json           # 原版网体数据源 (gitignored, 303 节点 12 层)
```

---

## 📋 数据库

- **SQLite** (默认 `data/rewarddb.db`, gitignored)
- **5 张业务表**:
  - `members` — 5 叉树 commission 成员
  - `pv_ledger` — 业务 PV 流水
  - `commission_periods` — 业务周期 (Sun-Fri + 补录窗口)
  - `order_items` — 下单管理 (PR #70)
  - `original_tree_nodes` — 原版网体节点 (PR #15, 303 节点 12 层, 顶层 parent_id = NULL)

- migration 工具幂等, 可多次跑:
  ```bash
  python tools/init_root_member.py         # PR #28 root 行
  python tools/migrate_add_role.py         # PR #41 role 列
  python tools/migrate_pr55_period_id.py   # PR #55 业务周 ID 格式
  python tools/migrate_original_tree.py    # PR #17 原版网体 JSON 迁 DB (interactive)
  ```

切 PostgreSQL: `pip install psycopg2-binary` + 改 `DB_URL=postgresql://...`.

---

## 📦 数据迁移 (PR #17)

### 业务场景

- 客户首次部署, 需要导入原版网体数据 (303 节点 12 层)
- 客户换了 JSON 数据集, 需要重新导入
- 测试时需要重置整个 DB (业务 + 原版网体)

### 用法

```bash
# Interactive 模式 (默认, 询问清空范围)
python tools/migrate_original_tree.py
```

输出菜单:
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

### CLI 选项

| 选项 | 行为 |
|---|---|
| (无) | Interactive 模式, 询问清空范围 |
| `--yes`, `-y` | 自动 yes, 全清 5 张业务表 (推荐 UAT 客户, 跳过询问) |
| `--net` | 只清原版网体, 其他业务表保留 (跳过询问) |
| `--db-path <path>` | 自定义 DB 路径, 默认 `data/rewarddb.db` |
| `--json-path <path>` | 自定义 JSON 路径, 默认 `json/original_tree.json` |
| `--help`, `-h` | 显示帮助 |

### 例子

```bash
# Interactive — 选 1 全清
python tools/migrate_original_tree.py
请输入选项 [1/2/3]: 1

# 自动全清 (推荐 UAT 客户)
python tools/migrate_original_tree.py --yes

# 只清原版网体 (业务表保留)
python tools/migrate_original_tree.py --net

# 自定义路径
python tools/migrate_original_tree.py --db-path D:/data/foo.db --json-path D:/data/tree.json
```

### 行为

1. **建表** (幂等): `original_tree_nodes` 25 列 + `idx_original_tree_parent` 索引
2. **清空**: 根据 scope 清空 1 张或 5 张业务表
3. **导入**: 递归 BFS 读 `json/original_tree.json`, 顶层 `parent_id = NULL` (用户拍板 "最上面的 Root 节点算 L0")
4. **验证**: 输出节点数 / depth 分布 / businessLevel 分布 / FK 完整性

### 字段值映射 (DB bool ↔ JSON 字符串)

| JSON | DB |
|---|---|
| `"YES"` / `"NO"` | `True` / `False` (`gold`, `iix`, `visibility`, `available`) |
| `"T"` / `"F"` | `True` / `False` (`has_subscription`, `is_qualified`) |
| 数字 (`level`, `maxLines`, `pv`, `org_pv` 等) | 转 `str` 保持跟原 JSON 一致 |

### 幂等性

- 多次跑安全: `CREATE TABLE IF NOT EXISTS` + `DELETE FROM` + 重新 INSERT
- 重新导入相同 JSON: 节点数 / 字段值完全一致
- 重新导入不同 JSON: 整树替换 (顶层 root 变化不影响, `parent_id = NULL` 永远只有一个)

### 客户文档 (CUSTOMER_GUIDE.md 也要更新)

CUSTOMER_GUIDE.md §"数据管理" 加这个章节, 让客户知道:
- 首次部署跑 `python tools/migrate_original_tree.py --yes`
- 换 JSON 数据集: 替换 `json/original_tree.json` + 重跑 migration
- 业务表清空重置: 跑 `--yes` 选项 (全清 5 张表)

---

## 🤝 贡献

- 主分支: `main`
- 改动走 **worktree** (AGENTS.md §3.1), 不在主仓直接改
- 提交 message 中文, 用 `Path.write_bytes(encode("utf-8"))` + `git commit -F file` (§3.2)
- PR 跑完测试 100% PASS + Playwright 端到端验证 (改 `static/index.html` 必须跑)

---

## 📄 文档

| 文档 | 读者 | 内容 |
|---|---|---|
| [README.md](README.md) (本文件) | 技术 / 开发 | 项目架构 + 启动 + API + 测试 + 数据迁移 |
| [CUSTOMER_GUIDE.md](CUSTOMER_GUIDE.md) | 客户 / UAT | 业务使用流程 + 业务规则 + FAQ |
| [AGENTS.md](AGENTS.md) | 开发 agent | 业务规则 + 32 个踩坑教训 + worktree/PR/test 流程 |

---

> 维护人: Justin Li (YuLi517)
> 最后更新: 2026-08-05 (PR #13/14 minimap+vertical + PR #15 DB 升级 + PR #16 L0 标号 + PR #17 数据迁移 interactive CLI)
