"""
RewardAgentAnalysis —— 会话持久化 + 历史回放
================================================


实现目标（来自 Implementation Plan 阶段 2 子任务 2A+2B）:
    ✅ 1. SQLite 持久化（SQLAlchemy 2.x ORM）
    ✅ 2. sessions + messages 两张表，含 reasoning / tokens / provider / latency 等元数据
    ✅ 3. 对话历史翻页（GET /sessions?page=1&page_size=20）
    ✅ 4. 对话历史关键词搜索（GET /sessions?q=keyword，命中 title 或消息内容）
    ✅ 5. 加载历史会话（GET /sessions/{sid}/messages）—— 完整 reasoning + tokens
    ✅ 6. 继承 stage1 全部能力：多 Provider 路由 + SSE 流式 + 熔断器 + Token 计量
    ✅ 7. 重启不丢数据（DB 文件落地 data/rewarddb.db）

不在 Stage 2 范围（明确不做）:
    ❌ 多租户隔离（Stage 2D）
    ❌ RAG / 知识库（Stage 2C 后续 — ★ 2026-07-12 已彻底下线,见 commit history）
    ❌ Milvus / 向量库（10 万级再做）
    ❌ Skills / MCP（阶段 3）
    ❌ 鉴权 / 登录

技术栈:
    - Python 3.10+
    - FastAPI
    - SQLAlchemy 2.x ORM
    - SQLite（默认） / PostgreSQL（换 URL 即可）
    - OpenAI Python SDK（兼容 DeepSeek / Qwen / Moonshot / GPT）
    - Pydantic v2
    - uvicorn

与 stage1 的差异:
    + 数据层：内存 → SQLite（重启不丢）
    + 历史回放：仅当前会话 → 全部会话可查可搜可翻页
    + 元数据：仅消息内容 → + reasoning + tokens + provider + latency

启动:
    1. pip install -r requirements.txt
    2. cp .env.example .env && 编辑填 API Key
    3. python main.py
    4. 浏览器 http://localhost:38080
"""

import os
import sys
import json
import time
import uuid
import hashlib
import logging
from enum import Enum
from collections import deque
from threading import Lock
from contextlib import asynccontextmanager
from typing import Optional, List, Generator, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime  # ★ 2026-07-05 v3: skill_5_3 写盘时记录 _preview_state.updated_at

from fastapi import FastAPI, HTTPException, Depends, Query
# ★ 2026-07-12: UploadFile / File / Form 不再需要(Stage 2C /documents/upload 端点下线)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from openai import OpenAI, APIError, APIConnectionError, RateLimitError, APITimeoutError, AuthenticationError, BadRequestError
from sqlalchemy.orm import Session as DbSession

from database import get_db, init_db, SessionLocal
from repository import SessionRepository
# ★ 2026-07-12: DocumentRepository / ChunkRepository 整段下线(RAG 知识库)
# from embedding import EmbeddingClient, load_embedding_config_from_env  -- 同步下线
# from rag import chunk_text, cosine_search, build_rag_prompt, parse_embedding  -- 同步下线
# from document_parser import parse_document, is_supported_file, supported_extensions  -- 同步下线


# ============================================================
# 树文件指纹 + 悲观锁(TreeLock)
# ============================================================
# 设计动机(用户 2026-07-01 反馈):
#   chatCommitSingle / chatCommitBatch 之前是"重算后再写盘",会导致:
#   预览算的位置 P1 → 用户确认 → commit 时重算,可能因为别人改过/锁竞争变成 P2
#   实际写到了 P2,但 UI 上说挂到 P1 → 业务正确性 bug
#
# 解决: 悲观锁 + 指纹
#   - 预览时(预计算)就 try acquire 锁(覆盖"用户凝视卡片"那段不确定时间)
#   - 拿锁后把 lock_id 挂在卡片 data 属性上
#   - commit 时把 lock_id 带回来;服务端 validate(锁未过期 + 盘上指纹未变)
#   - 锁 10 分钟 TTL,过期自动失效;前端卡片可主动 cancel 释放
#   - 423: 锁被占 → 前端 toast 提示等解锁
#   - 409: 锁失效(过期/盘被改)→ 前端让用户重新预览
#
# 已知限制: in-memory 单进程锁,服务重启即丢;并发预览会被 423 挡住。
# 后续如上多 worker,可改用 Redis / 文件锁。
#
# 多文件锁(2026-07-03 改造):
#   原本所有 skill 共享一个 Tree 文件 + 一把全局锁 → 5 叉 / 4 叉 / 3 叉切换时互相阻塞。
#   现在每个 skill_id 走自己的 json/json/Tree_Nary.json + 独立的 _TreeLock 实例,互不干扰。

# 各 skill 对应本地 demo Tree 文件路径(本地数据,不入仓,见 .gitignore)
# ★ 2026-07-15: skill_2 已下线,只剩 skill_5_3 (5 叉按位反转)
#   - skill_5_3 走空 5 叉根(Tree_empty_5_3.json),支持 preview + 写盘 (PR #8)
#   - skill_2 / skill_5_1 / skill_5_2 相关代码 + Tree_2ary.json 都已删除
TREE_PATHS: Dict[str, str] = {
    "skill_5_3": os.path.join(os.path.dirname(os.path.abspath(__file__)), "json", "Tree_empty_5_3.json"),
    # ★ v1.0.7 2026-08-08: 新增 ternary (3 叉) 支持, 跟 binary/four_way 算法对齐 (PR #18/22)
    "skill_3": os.path.join(os.path.dirname(os.path.abspath(__file__)), "json", "Tree_empty_3.json"),
    # ★ v1.0.8 2026-08-08: 新增 quaternary (4 叉) 支持, 跟 ternary 一致
    "skill_4": os.path.join(os.path.dirname(os.path.abspath(__file__)), "json", "Tree_empty_4.json"),
}
# /api/tree/render 不带 skill 时默认 fallback
# ★ 2026-07-14 v8: 默认 skill_5_3 (5 叉演示树) — 业务主线
DEFAULT_TREE_SKILL = "skill_5_3"
# 兼容旧 TREE_PATH 引用(单文件路径) — 实际不再用,所有调用改走 TREE_PATHS[skill_id]
TREE_PATH = TREE_PATHS[DEFAULT_TREE_SKILL]  # DEPRECATED,保留以防外部脚本误读


# ============================================================
# ★ 2026-07-16 PR #41/42: 角色常量 (7 种, DB 存全名 label)
#   - 业务: 加入时人工选, 后续 /role 改
#   - key = label (中文/英文全名, 跟 DB members.role 字段值完全一致)
#   - bg / fg: 颜色 (色相分散, 一眼能区分)
#   - 默认: '消费股东' (最普通角色, DB 列 default)
#   - DB schema: members.role VARCHAR(64) NOT NULL DEFAULT '消费股东'
#   - 改 PR #42: 用 label 当 key, 跟 DB 字段值 1:1 (之前 PR #41 用 enum key, UI 显示 short)
# ============================================================
MEMBER_ROLES: Dict[str, Dict[str, str]] = {
    "消费股东": {
        "bg": "#BFDBFE",  # 浅蓝
        "fg": "#1E3A8A",  # 深蓝
    },
    "预备合伙人": {
        "bg": "#BBF7D0",  # 浅绿
        "fg": "#14532D",  # 深绿
    },
    "合伙人员工": {
        "bg": "#DDD6FE",  # 浅紫
        "fg": "#4C1D95",  # 深紫
    },
    "初级管理合伙人": {
        "bg": "#FED7AA",  # 浅橙
        "fg": "#9A3412",  # 深橙
    },
    "中级管理合伙人": {
        "bg": "#FBCFE8",  # 浅粉
        "fg": "#9D174D",  # 深粉
    },
    "高级管理合伙人": {
        "bg": "#FECACA",  # 浅红
        "fg": "#991B1B",  # 深红
    },
    "Inactive": {
        "bg": "#E5E7EB",  # 浅灰
        "fg": "#6B7280",  # 深灰
    },
}
DEFAULT_ROLE = "消费股东"
VALID_ROLES = set(MEMBER_ROLES.keys())


# ★ 2026-08-06 PR #75: 业务档位 (business_level) — 4 档位独立列
#   用户拍板 (2026-08-06 截图): 成员加入时 4 档位选择
#     - 激活: 200 PV / 15% 培育金 / 2 团队 (跟 PR #71 teamBonus 4 档 tier 1 对应)
#     - 商务: 500 PV / 20% 培育金 / 3 团队 (跟 PR #71 tier 2 对应)
#     - 精英: 1000 PV / 25% 培育金 / 4 团队 (跟 PR #71 tier 3 对应)
#     - 至尊: 1500 PV / 30% 培育金 / 5 团队 (跟 PR #71 tier 4 对应)
#   业务定位:
#     - 跟 role 字段独立 (role 7 个 + business_level 4 档, 2 套并存)
#     - 业务字段 (PV / max_lines) 跟 business_level 字段独立 (用户自己填)
#     - 黄金身份 默认 ✓ (跟 role 跟 business_level 都无关, PR #74 拍板)
#   颜色 (跟截图一致):
#     - 激活: 紫色 (浅紫 #DDD6FE / 深紫 #4C1D95)
#     - 商务: 蓝色 (浅蓝 #BFDBFE / 深蓝 #1E3A8A)
#     - 精英: 橙色 (浅橙 #FED7AA / 深橙 #9A3412)
#     - 至尊: 深绿 (浅绿 #BBF7D0 / 深绿 #14532D) — 跟原 预备合伙人 颜色一致 (复用)
MEMBER_BUSINESS_LEVELS: Dict[str, Dict[str, str]] = {
    "激活": {
        "bg": "#DDD6FE",  # 浅紫
        "fg": "#4C1D95",  # 深紫
        "tier_pv": 200,    # 对应 PR #71 teamBonus 15% 档
    },
    "商务": {
        "bg": "#BFDBFE",  # 浅蓝
        "fg": "#1E3A8A",  # 深蓝
        "tier_pv": 500,    # 对应 PR #71 teamBonus 20% 档
    },
    "精英": {
        "bg": "#FED7AA",  # 浅橙
        "fg": "#9A3412",  # 深橙
        "tier_pv": 1000,   # 对应 PR #71 teamBonus 25% 档
    },
    "至尊": {
        "bg": "#BBF7D0",  # 浅绿
        "fg": "#14532D",  # 深绿
        "tier_pv": 1500,   # 对应 PR #71 teamBonus 30% 档
    },
}
DEFAULT_BUSINESS_LEVEL = "激活"
VALID_BUSINESS_LEVELS = set(MEMBER_BUSINESS_LEVELS.keys())


def _normalize_business_level(value: Optional[str]) -> str:
    """★ 2026-08-06 PR #75: 规范化 business_level 值: 空/None/未知 → '激活' (默认)

    跟 _normalize_role 平行函数, 4 档位独立列
    """
    if not value or value not in VALID_BUSINESS_LEVELS:
        return DEFAULT_BUSINESS_LEVEL
    return value


def _normalize_role(value: Optional[str]) -> str:
    """规范化 role 值: 空/None/未知 → '消费股东' (默认)

    PR #42: key 就是 label, 校验直接 in VALID_ROLES
    """
    if not value or value not in VALID_ROLES:
        return DEFAULT_ROLE
    return value


def _tree_fingerprint(raw: dict) -> str:
    """对树算一个稳定指纹 —— 用于乐观锁比对

    规范化:
        - 递归按 (parentLineId, uid) 排序 children
          (jsTree 实际 children 列表顺序 ≠ 业务 parentLineId 顺序,直接 json.dumps 会被顺序干扰)
        - 用 sort_keys=True 输出 JSON
        - 排除运行时注入的非业务字段(available/rank —— commit 写盘时这些也会被清掉)
        - ★ 强制 int 转换: jsTree 导出的 parentLineId/uid 有的是 int 有的是 str,
          排序时直接比会抛 "'<' not supported between instances of 'int' and 'str'"
    """
    def _to_int(v, default=0):
        if v is None or v == "":
            return default
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    def _norm(node):
        if not isinstance(node, dict):
            return node
        keep = {k: _norm(v) for k, v in node.items()
                if k not in ("children", "available", "rank")}
        kids = node.get("children") or []
        keep["children"] = sorted(
            [_norm(c) for c in kids],
            key=lambda c: (_to_int(c.get("parentLineId")), _to_int(c.get("uid")))
        )
        return keep
    canonical = json.dumps(_norm(raw), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class _TreeLock:
    """单个 Tree JSON 文件的悲观锁 —— in-memory 单进程版

    acquire()   → 成功: (True, lock_id, current_fp); 失败/被占: (False, None, None)
    validate()  → 成功: (True, current_fp); 失败: (False, current_fp_or_None)
                  失败时**已经自动失效锁**,下次 acquire 可拿到
    release()   → True/False 是否成功释放

    TTL 默认 10 分钟(用户拍板),覆盖"用户盯着卡片 → 决定 → 点确认"完整流程
    """
    def __init__(self, tree_path: str, ttl_seconds: int = 600):
        self._path = tree_path
        self._ttl = ttl_seconds
        self._holder: Optional[str] = None
        self._fp: Optional[str] = None
        self._acquired_at: float = 0.0

    def acquire(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """尝试拿锁

        返回:
            (True, lock_id, current_fp)  成功
            (False, None, None)           失败 —— 锁被他人持有(真锁竞争,非内部错误)
            ★ 内部错误(读盘/算指纹失败) → 抛异常,让上层 500
              避免被前端误读为"锁被占"显示 423
        """
        # 1. 过期检测: 持有者超时 → 强制释放
        if self._holder and (time.time() - self._acquired_at) > self._ttl:
            log.warning(f"🔓 TreeLock: lock_id={self._holder[:8]} 已过期(>{self._ttl}s),强制释放")
            self._holder = None
        # 2. 已被他人持有
        if self._holder:
            return False, None, None
        # 3. 读盘算当前指纹
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                cur_fp = _tree_fingerprint(json.load(f))
        except FileNotFoundError:
            log.error(f"🔓 TreeLock: Tree 文件不存在: {self._path}")
            # 文件不存在不是锁竞争,是配置问题 → 抛
            raise HTTPException(500, f"Tree 文件不存在: {self._path}")
        # 其他异常让其自然向上抛(FastAPI 兜底 500)
        # 4. 拿锁
        self._holder = str(uuid.uuid4())
        self._fp = cur_fp
        self._acquired_at = time.time()
        return True, self._holder, cur_fp

    def validate(self, lock_id: str) -> Tuple[bool, Optional[str]]:
        """返回 (ok, current_fp). 不 ok 时已经自动失效锁,下次 acquire 不会卡。"""
        if not self._holder or self._holder != lock_id:
            return False, None  # 已被释放/接管
        if (time.time() - self._acquired_at) > self._ttl:
            log.warning(f"🔓 TreeLock: lock_id={lock_id[:8]} validate 时已过期(>{self._ttl}s)")
            self._holder = None
            return False, None
        # 重新读盘确认盘上指纹还是锁时那个 —— 防止有人绕开 API 直接改文件
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                cur_fp = _tree_fingerprint(json.load(f))
        except Exception as e:
            log.error(f"🔓 TreeLock: validate 时读盘失败: {e},锁失效")
            self._holder = None
            return False, None
        if cur_fp != self._fp:
            log.warning(
                f"🔓 TreeLock: 盘上指纹变了(人手改了文件? lock_id={lock_id[:8]} "
                f"old={self._fp[:8]} new={cur_fp[:8]})锁失效"
            )
            self._holder = None
            return False, cur_fp
        return True, cur_fp

    def release(self, lock_id: str) -> bool:
        if self._holder == lock_id:
            log.info(f"🔓 TreeLock: lock_id={lock_id[:8]} 主动释放")
            self._holder = None
            self._fp = None
            return True
        return False

    def force_release(self) -> Optional[str]:
        """强制释放当前锁(无论谁持的)—— 管理员级,用于救"孤儿锁"
        返回被释放的 lock_id,如果没有锁则返回 None
        """
        if not self._holder:
            return None
        released_id = self._holder
        log.warning(
            f"🔓 TreeLock: 强制释放 lock_id={released_id[:8]} (force_release)"
        )
        self._holder = None
        self._fp = None
        return released_id

    def status(self) -> dict:
        """前端 status 查询用(目前未挂端点,保留用于调试)"""
        return {
            "held": bool(self._holder),
            "lock_id": (self._holder or "")[:8] if self._holder else None,
            "acquired_at": self._acquired_at if self._holder else None,
            "ttl_seconds": self._ttl,
            "fingerprint_prefix": (self._fp or "")[:8] if self._fp else None,
        }


# ============================================================
# 按 skill_id 索引的锁字典 —— 不同 skill 走不同 json + 独立锁,互不干扰
# ============================================================
_tree_locks: Dict[str, _TreeLock] = {}


def _get_tree_lock(skill_id: str) -> _TreeLock:
    """按 skill_id 懒初始化锁实例

    skill_id 不在 TREE_PATHS 里 → 400(当前支持 skill_5_3)
    """
    if skill_id not in TREE_PATHS:
        raise HTTPException(
            400,
            f"skill_id={skill_id!r} 没有对应 Tree JSON 路径(只支持 skill_5_3)",
        )
    if skill_id not in _tree_locks:
        _tree_locks[skill_id] = _TreeLock(TREE_PATHS[skill_id], ttl_seconds=600)
        log.info(f"🔓 TreeLock: 懒初始化 skill_id={skill_id} → {TREE_PATHS[skill_id]}")
    return _tree_locks[skill_id]


# ============================================================
# ============================================================
# ★ 2026-07-15 PR #14: 回归 PR #4 自动提升业务规则
#   - 业务侧拍板: 1-2 区满员后自动开 3-4 区, 3-4 区满后开 line 5
#   - 之前 PR #6 引入的"手动解锁"已撤销
#   - 算法实现见 _compute_effective_active_from_json() (跟 skills/skill_5_lib.py
#     Node5.effective_max_active_lines() 逻辑一致, 适配 JSON dict 输入)
# ============================================================


def _compute_effective_active_from_json(parent: Dict[str, Any], max_lines: int = 5, max_active_lines: int = 2) -> int:
    """根据 parent 节点 JSON dict 的 children 状态, 算 effective_max_active_lines

    业务规则 (PR #18 + 用户 2026-07-15 拍板):
        - 默认 eff = 2 (L1+L2 激活, line 3+ 锁)
        - L1+L2 都「line 满」(line 父下面 max_depth >= 9) → eff 升到 4 (L3+L4 同时开)
        - L1-L4 都「line 满」→ eff 升到 5 (L5 单独开)
        - 上限 max_lines (5 叉 → 5)

    算法跟 skills/skill_5_lib.py Node5.effective_max_active_lines() 完全一致,
    但这里输入是 JSON dict (parent 节点从 json 读), 不是 Node5 内存树对象。

    每个节点独立判定 (递归): root 看张1/张2, 张1 看自己子 1+2, 张2 看自己子 1+2。
    整树按相同规则从 root 递归到 L_n, 任意节点都遵循"自己 1+2 满 → 开 3+4"。

    ★ 2026-07-16 PR #25: 修 bug
      之前 (PR #14 c29f68a 引入): line 满 = line 至少 1 个真实成员
        (real_count_per_line.get(line_id, 0) > 0)
      实际 (PR #18 业务规则): line 满 = line 父下面 max_depth >= 9
        (5 叉 9 层 = depth 1..9, 不含 line 自己)
      两个实现不一致 → 渲染层 line 1+2 各挂 1 真实成员就升 eff=4 (跟业务规则不符)
      user 反馈: "我增加成员后, 王常军的 3 区和 4 区自动激活了. 规则是要等 1 区和 2 区的 9 层都排满了, 再激活"
    """
    FULL_LAYERS = 9  # 跟 skill_5_lib.py Node5.effective_max_active_lines() 一致

    def _max_depth_in_subtree(node_dict: Dict[str, Any]) -> int:
        """递归算 node 下面 (不含自己) 的子孙深度
        - node 没子 → 0
        - node 有 1 层子 → 1
        - node 有 N 层子孙 → N
        跟 skill_5_lib.Node5._max_depth_in_subtree() 行为一致
        """
        children = node_dict.get("children") or []
        if not children:
            return 0
        return 1 + max(_max_depth_in_subtree(c) for c in children)

    def _is_line_filled(line_id: int) -> bool:
        """line 满 = line 父下面 max_depth >= 9
        遍历 parent.children, 找 line_id 对应的真实成员 (avail=False), 算它的 max_depth
        """
        for c in (parent.get("children") or []):
            if c.get("available") is True or c.get("avail") is True:
                continue  # 跳过 avail 占位
            try:
                lid = int(c.get("parentLineId") or 0)
            except (TypeError, ValueError):
                lid = 0
            if lid == line_id and _max_depth_in_subtree(c) >= FULL_LAYERS:
                return True
        return False

    effective = max_active_lines  # 默认 (caller 传, 2 渐进解锁 / 4 root 显式)
    if _is_line_filled(1) and _is_line_filled(2):
        effective = 4
        if _is_line_filled(3) and _is_line_filled(4):
            effective = 5
    # 上限: max_lines (5 叉 → 最大 5)
    return min(effective, max_lines)


def _force_release_all_tree_locks() -> List[str]:
    """force_release 所有 skill 的锁(管理员级救场)

    返回被释放的 lock_id 列表。无锁返回 []。
    """
    released = []
    for sid, lock in _tree_locks.items():
        rid = lock.force_release()
        if rid:
            log.warning(f"🔓 TreeLock: force_release skill_id={sid} → lock_id={rid[:8]}")
            released.append(rid)
    return released


def _release_tree_lock_by_id(lock_id: str) -> Optional[str]:
    """在所有 _tree_locks 里找 lock_id 匹配的并释放

    返回释放成功的 skill_id;未匹配返回 None。
    """
    for sid, lock in _tree_locks.items():
        if lock.release(lock_id):
            return sid
    return None


# 注:不再保留 module-level tree_lock alias
# 历史代码里 `tree_lock = _get_tree_lock(DEFAULT_TREE_SKILL)` 的位置早于 `log = logging.getLogger(...)` 定义,
# 会触发 NameError。新代码一律按需调用 `_get_tree_lock(skill_id)`。

# 将 skills/ 加入 sys.path（用于加载 skill_5_3 等本地技能模块）
# 缺失时优雅降级 —— Skill 相关 endpoint 会返回 503，不影响主服务启动
_SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")
if _SKILLS_DIR not in sys.path:
    sys.path.insert(0, _SKILLS_DIR)

# ============================================================
# Skills 注册 — 只剩 skill_5_3 (5 叉按位反转, 业务主线)
# ★ 2026-07-15: skill_2 / skill_5_1 / skill_5_2 全部下线
#   - skill_5_3: 5 叉, 用 skill_5_3.simulate_addition_bitrev,按「base-5 digit reversal (按位反转)」挂入
#   - skill_5_lib: 内部基础库,只供 skill_5_3 import, 不作为公开 skill
#   - skill_5_helpers: 抽出来的 7 个工具函数
# ============================================================
_skill_runners: Dict[str, Any] = {
    "skill_5_3": None,
}
_skill_load_errors: Dict[str, Optional[str]] = {
    "skill_5_3": None,
}

# skill_5_3: 「按位反转 (base-5 digit reversal)」按 TreeGenerate/verify_l6.py 反推的位反转规律
#   - 2026-07-12 新增: 把 2 叉版的 bit_reverse 推广到 5 叉树 (base-2 → base-5)
#   - 用 sentinel (simulate_addition_bitrev) 让 _skill_runners 非空
#   - 实际调用走专门的 /skills/skill_5_3/batch/run endpoint
try:
    from skill_5_3 import simulate_addition_bitrev as _runner_s53
    _skill_runners["skill_5_3"] = _runner_s53
except Exception as _e:
    _skill_load_errors["skill_5_3"] = str(_e)

# 自动加载 main.py 旁边的 .env（无论从哪个目录启动都能加载到）
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ============== 配置 ==============

@dataclass
class ProviderConfig:
    name: str
    api_key: str
    base_url: str
    model: str
    timeout: int = 30
    failure_threshold: int = 5
    recovery_time: int = 60


class Settings:
    def __init__(self):
        self.max_history = int(os.getenv("MAX_HISTORY", "10"))
        self.host = os.getenv("HOST", "0.0.0.0")
        self.port = int(os.getenv("PORT", "38080"))
        self.default_temperature = float(os.getenv("DEFAULT_TEMPERATURE", "0.7"))
        self.max_tokens = int(os.getenv("MAX_TOKENS", "2048"))
        self.global_max_retries = int(os.getenv("GLOBAL_MAX_RETRIES", "2"))

        # 加载多 provider 配置
        # LLM_PROVIDERS=deepseek,qwen  →  列表中第一个为 primary
        # ★ 2026-07-21 (PR #63): LLM 改为 optional, 未配置时优雅降级
        # 业务 (commission 系统) 完全不依赖 LLM, 客户 UAT 不配 key 也能跑
        # chat 端点在 router 找不到 provider 时返回 503
        provider_names = [n.strip() for n in os.getenv("LLM_PROVIDERS", "").split(",") if n.strip()]
        if not provider_names:
            # 未配 LLM: 不 raise, 跳过 provider 初始化
            # 业务侧 (commission / 树视图 / 期间结算) 全部正常工作
            import logging as _logging
            _logging.getLogger("uvicorn").warning(
                "⚠️  LLM_PROVIDERS 未配置 — chat 端点不可用, commission 系统正常运行"
            )

        self.providers_config: List[ProviderConfig] = []
        for name in provider_names:
            api_key = os.getenv(f"{name.upper()}_API_KEY", "")
            base_url = os.getenv(f"{name.upper()}_BASE_URL", "")
            model = os.getenv(f"{name.upper()}_MODEL", "")
            if not (api_key and base_url and model):
                raise ValueError(
                    f"❌ Provider '{name}' 配置不完整！\n"
                    f"需要在 .env 中设置：\n"
                    f"  {name.upper()}_API_KEY=...\n"
                    f"  {name.upper()}_BASE_URL=...\n"
                    f"  {name.upper()}_MODEL=..."
                )
            self.providers_config.append(ProviderConfig(
                name=name,
                api_key=api_key,
                base_url=base_url,
                model=model,
                timeout=int(os.getenv(f"{name.upper()}_TIMEOUT", "30")),
                failure_threshold=int(os.getenv(f"{name.upper()}_FAILURE_THRESHOLD", "5")),
                recovery_time=int(os.getenv(f"{name.upper()}_RECOVERY_TIME", "60")),
            ))


settings = Settings()

# ============== 日志 ==============

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger("stage1")

# ============== 熔断器 ==============

class BreakerState(Enum):
    CLOSED = "closed"      # 正常
    OPEN = "open"          # 熔断（拒绝请求）
    HALF_OPEN = "half_open"  # 半开（放一个探测请求）


class CircuitBreaker:
    """熔断器：CLOSED → OPEN → HALF_OPEN → CLOSED/OPEN"""

    def __init__(self, name: str, failure_threshold: int = 5, recovery_time: int = 60):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.state = BreakerState.CLOSED
        self.recent: deque = deque(maxlen=20)  # 最近 20 次结果（0=成功，1=失败）
        self.opened_at: Optional[float] = None
        self.lock = Lock()

    def allow(self) -> bool:
        with self.lock:
            if self.state == BreakerState.CLOSED:
                return True
            if self.state == BreakerState.OPEN:
                # 检查是否到恢复时间
                if self.opened_at and time.time() - self.opened_at >= self.recovery_time:
                    self.state = BreakerState.HALF_OPEN
                    log.info(f"🔄 [{self.name}] OPEN → HALF_OPEN")
                    return True
                return False
            # HALF_OPEN：放行一个探测请求
            return True

    def record_success(self):
        with self.lock:
            self.recent.append(0)
            if self.state == BreakerState.HALF_OPEN:
                self.state = BreakerState.CLOSED
                self.opened_at = None
                self.recent.clear()
                log.info(f"✅ [{self.name}] HALF_OPEN → CLOSED")

    def record_failure(self):
        with self.lock:
            self.recent.append(1)
            if self.state == BreakerState.HALF_OPEN:
                self.state = BreakerState.OPEN
                self.opened_at = time.time()
                log.warning(f"🔴 [{self.name}] HALF_OPEN → OPEN")
            elif self.state == BreakerState.CLOSED:
                failures = sum(self.recent)
                if failures >= self.failure_threshold:
                    self.state = BreakerState.OPEN
                    self.opened_at = time.time()
                    log.warning(
                        f"🔴 [{self.name}] CLOSED → OPEN "
                        f"({failures} failures in {len(self.recent)} requests)"
                    )

    def get_stats(self) -> dict:
        with self.lock:
            if not self.recent:
                return {"state": self.state.value, "error_rate": 0, "samples": 0}
            return {
                "state": self.state.value,
                "error_rate": round(sum(self.recent) / len(self.recent), 3),
                "samples": len(self.recent),
            }


# ============== LLM Provider ==============

class LLMProvider:
    """单个 LLM Provider（MiniMax / DeepSeek / Qwen / Moonshot / GPT 等 OpenAI 兼容 API）"""

    def __init__(self, config: ProviderConfig, breaker: CircuitBreaker):
        self.config = config
        self.breaker = breaker
        self.client = OpenAI(api_key=config.api_key, base_url=config.base_url, timeout=config.timeout)

    # ----- 非流式 -----
    def chat(self, messages: list, temperature: float, max_tokens: int) -> dict:
        if not self.breaker.allow():
            return {
                "ok": False,
                "error_type": "circuit_open",
                "error_msg": f"[{self.config.name}] circuit breaker is OPEN",
                "provider": self.config.name,
            }

        try:
            start = time.time()
            resp = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            latency = time.time() - start
            self.breaker.record_success()
            log.info(
                f"✅ [{self.config.name}/{self.config.model}] "
                f"prompt={resp.usage.prompt_tokens} completion={resp.usage.completion_tokens} "
                f"latency={latency:.2f}s"
            )
            return {
                "ok": True,
                "reply": resp.choices[0].message.content,
                "model": self.config.model,
                "provider": self.config.name,
                "usage": {
                    "prompt_tokens": resp.usage.prompt_tokens,
                    "completion_tokens": resp.usage.completion_tokens,
                    "total_tokens": resp.usage.total_tokens,
                },
                "latency_ms": int(latency * 1000),
            }
        except (RateLimitError, APITimeoutError, APIConnectionError, APIError) as e:
            self.breaker.record_failure()
            log.warning(f"❌ [{self.config.name}] {type(e).__name__}: {e}")
            return {"ok": False, "error_type": type(e).__name__, "error_msg": str(e), "provider": self.config.name}
        except AuthenticationError as e:
            self.breaker.record_failure()
            log.error(f"🔑 [{self.config.name}] auth failed: {e}")
            return {"ok": False, "error_type": "auth_error", "error_msg": str(e), "provider": self.config.name}
        except BadRequestError as e:
            log.warning(f"⚠️ [{self.config.name}] bad request: {e}")
            return {"ok": False, "error_type": "bad_request", "error_msg": str(e), "provider": self.config.name}
        except Exception as e:
            self.breaker.record_failure()
            log.exception(f"❌ [{self.config.name}] unknown error: {e}")
            return {"ok": False, "error_type": "unknown", "error_msg": f"{type(e).__name__}: {e}", "provider": self.config.name}

    # ----- 流式 -----
    def chat_stream(self, messages: list, temperature: float, max_tokens: int) -> Generator[dict, None, None]:
        if not self.breaker.allow():
            yield {
                "ok": False,
                "error_type": "circuit_open",
                "error_msg": f"[{self.config.name}] circuit breaker is OPEN",
                "provider": self.config.name,
            }
            return

        try:
            stream = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            self.breaker.record_success()
            full_reply = ""
            full_reasoning = ""  # 累积思考过程
            content_buffer = ""  # 用于检测跨 chunk 的 <think>...</think>
            completion_tokens = 0

            def emit_text(text):
                """辅助函数：发 content_delta"""
                nonlocal full_reply, completion_tokens
                if not text:
                    return
                full_reply += text
                completion_tokens += 1
                return {
                    "ok": True,
                    "is_final": False,
                    "event": "content_delta",
                    "delta": text,
                    "provider": self.config.name,
                    "model": self.config.model,
                }

            def emit_reasoning(text):
                """辅助函数：发 reasoning_delta"""
                nonlocal full_reasoning
                if not text:
                    return
                full_reasoning += text
                return {
                    "ok": True,
                    "is_final": False,
                    "event": "reasoning_delta",
                    "delta": text,
                    "provider": self.config.name,
                    "model": self.config.model,
                }

            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                # 兼容 OpenAI SDK 1.x：先尝试独立的 reasoning_content 字段（DeepSeek-R1 / o1 风格）
                delta_dict = {}
                try:
                    delta_dict = delta.model_dump(exclude_unset=False)
                except Exception:
                    pass

                standalone_reasoning = delta_dict.get("reasoning_content") or ""

                # 2) 处理 content（可能在 <think>...</think> 内）
                content = delta.content or ""

                # 如果有独立的 reasoning_content 字段，先发它
                if standalone_reasoning:
                    yield emit_reasoning(standalone_reasoning)

                # 把 content 加入 buffer，循环抽离 <think>...</think>
                if content:
                    content_buffer += content
                    # 处理 buffer 中所有完整的 <think>...</think>
                    while True:
                        ts = content_buffer.find("<think>")
                        if ts == -1:
                            break  # 没有 think 开始标签
                        te = content_buffer.find("</think>", ts)
                        if te == -1:
                            break  # 还没结束标签，等下个 chunk
                        # 抽取
                        before = content_buffer[:ts]
                        thinking = content_buffer[ts + len("<think>") : te]
                        after = content_buffer[te + len("</think>") :]
                        # 输出
                        if before:
                            yield emit_text(before)
                        if thinking:
                            yield emit_reasoning(thinking)
                        content_buffer = after

            # 流结束时，buffer 里残留的（可能是 <think> 没闭合的尾巴）作为 content 输出
            if content_buffer:
                yield emit_text(content_buffer)

            yield {
                "ok": True,
                "is_final": True,
                "event": "done",
                "delta": "",
                "reply": full_reply,
                "reasoning": full_reasoning,  # 完整思考内容
                "provider": self.config.name,
                "model": self.config.model,
                "usage": {
                    "prompt_tokens": 0,  # 流式 OpenAI SDK 通常不返回
                    "completion_tokens": completion_tokens,
                    "total_tokens": completion_tokens,
                },
            }
        except Exception as e:
            self.breaker.record_failure()
            log.warning(f"❌ [{self.config.name}] stream error: {type(e).__name__}: {e}")
            yield {"ok": False, "error_type": type(e).__name__, "error_msg": str(e), "provider": self.config.name}


# ============== Router ==============

class LLMRouter:
    """多 Provider 路由器：选 primary + 自动 fallback"""

    def __init__(self, providers: List[LLMProvider]):
        self.providers = providers  # 第一个为 primary
        self.by_name = {p.config.name: p for p in providers}

    def pick(self, provider_name: Optional[str], model_name: Optional[str]) -> Optional[LLMProvider]:
        if provider_name:
            return self.by_name.get(provider_name)
        if model_name:
            for p in self.providers:
                if p.config.model == model_name:
                    return p
        return self.providers[0]  # 默认 primary

    def build_chain(self, primary: LLMProvider) -> List[LLMProvider]:
        # 选中的放第一位，其他按配置顺序作为 fallback
        chain = [primary]
        for p in self.providers:
            if p is not primary:
                chain.append(p)
        return chain

    # ----- 非流式：自动 fallback -----
    def chat_with_fallback(self, messages, provider_name=None, model_name=None, **kwargs) -> dict:
        primary = self.pick(provider_name, model_name)
        chain = self.build_chain(primary)
        attempts = []
        for p in chain:
            result = p.chat(messages, **kwargs)
            attempts.append({
                "provider": p.config.name,
                "ok": result["ok"],
                "error_type": result.get("error_type"),
            })
            if result["ok"]:
                result["attempts"] = attempts
                result["fallback_used"] = len(attempts) > 1
                return result
            # 鉴权错误 / 内容错误不重试（无意义）
            if result.get("error_type") in ("auth_error", "bad_request"):
                break
        return {
            "ok": False,
            "error_type": "all_providers_failed",
            "error_msg": f"All {len(chain)} providers failed",
            "attempts": attempts,
        }

    # ----- 流式：自动 fallback -----
    def chat_stream_with_fallback(self, messages, provider_name=None, model_name=None, **kwargs) -> Generator[dict, None, None]:
        primary = self.pick(provider_name, model_name)
        chain = self.build_chain(primary)
        for i, p in enumerate(chain):
            used_fallback = i > 0
            failed = False
            for chunk in p.chat_stream(messages, **kwargs):
                if not chunk["ok"]:
                    failed = True
                    break
                if used_fallback:
                    chunk["fallback_used"] = True
                yield chunk
            if not failed:
                return
            # 鉴权错误不重试
            if i == 0:
                # 试 fallback
                continue
        yield {
            "ok": False,
            "error_type": "all_providers_failed",
            "error_msg": f"All {len(chain)} providers failed",
        }

    def list_health(self) -> list:
        return [
            {
                "provider": p.config.name,
                "model": p.config.model,
                **p.breaker.get_stats(),
            }
            for p in self.providers
        ]


# ============== 初始化 ==============

providers: List[LLMProvider] = []
for cfg in settings.providers_config:
    breaker = CircuitBreaker(
        name=cfg.name,
        failure_threshold=cfg.failure_threshold,
        recovery_time=cfg.recovery_time,
    )
    providers.append(LLMProvider(cfg, breaker))

router = LLMRouter(providers)


# ============== Pydantic Models ==============

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    session_id: Optional[str] = None
    model: Optional[str] = Field(None, description="指定模型，如 deepseek-chat")
    provider: Optional[str] = Field(None, description="指定 provider，如 deepseek")
    temperature: float = Field(default=settings.default_temperature, ge=0, le=2)
    system_prompt: Optional[str] = None
    stream: bool = Field(default=False)


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    provider: str
    model: str
    usage: dict
    latency_ms: int
    attempts: list
    fallback_used: bool


# ============== Embedding 客户端 (Stage 2C,★ 2026-07-12 已下线) ==============
# 原 Stage 2C 引入的 EmbeddingClient 全局变量已删除,RAG 知识库整段下线。
# 业务侧只保留 chat (multi-turn 对话) + skills (网体算法) 两条主线。
# 如果未来要重新启用 RAG,需要:1) git revert 此 commit;2) 重新装 python-docx/pypdf 等依赖。

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 初始化数据库（创建表 + 索引）
    init_db()

    # P1.6 §4.2: 预热所有 scenarios (后台 thread, 不阻塞 startup)
    # 注: 1 个 scenario 算 15 月 × ~10ms = 150ms, 全部 scenarios 后台跑
    # 传 SessionLocal (sessionmaker) 而非 session, 避免父进程 close 跟后台 thread race
    from scenario.warmer import warm_all_scenarios
    from database import SessionLocal
    warm_all_scenarios(SessionLocal, total_months=14)

    log.info("=" * 60)
    log.info("🚀 RewardAgentAnalysis Stage 3 启动（SQLite 持久化已启用 · RAG 知识库已下线）")
    log.info(f"   路由链（按优先级）: {' → '.join(p.config.name for p in providers)}")
    for p in providers:
        log.info(f"   {p.config.name}: {p.config.base_url} ({p.config.model})")
    log.info(f"   监听: http://{settings.host}:{settings.port}")
    log.info(f"   Docs: http://{settings.host}:{settings.port}/docs")
    log.info("=" * 60)
    yield
    log.info("👋 Stage 3 关闭")


app = FastAPI(
    title="RewardAgentAnalysis Stage 2",
    description="会话持久化 + 历史回放 + 多 Provider 路由 + SSE + 熔断器",
    version="0.3.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ============== API ==============

@app.get("/")
def index():
    p = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(p):
        return FileResponse(p)
    return {"hint": "static/index.html not found", "docs": "/docs"}


# ★ 2026-08-05: 原版网体可视化 (从 SQLite original_tree_nodes 表读, 不再依赖 JSON 文件)
# PR #15 升级: 数据从 json/original_tree.json 迁到 SQLite 表
# migration 工具: tools/migrate_original_tree.py
@app.get("/api/original_tree/data")
def api_original_tree_data(db: DbSession = Depends(get_db)):
    """从 original_tree_nodes 表读, 构造树形 JSON 响应 (跟原 JSON 结构一致)."""
    from sqlalchemy import text

    # 1. 一次性查所有节点 (303 行, 小数据量可全表读)
    rows = db.execute(text("""
        SELECT
            id, dist_id, name, level, max_lines, parent_id, parent_line_id,
            business_level, gold, iix, rank, status, activity_status_id,
            pv, org_pv, personal_customer_pv,
            has_subscription, is_qualified, status_color, visibility, available,
            rows, max_rows, global_node_id
        FROM original_tree_nodes
        ORDER BY id
    """)).fetchall()

    if not rows:
        raise HTTPException(404, "original_tree_nodes 表为空, 请先跑 tools/migrate_original_tree.py 导入数据")

    # 2. 构造 node dict + 按 dist_id 索引
    nodes_by_id = {}
    children_by_parent = {}  # parent_dist_id (or None for root) -> [node dicts]
    for r in rows:
        # ★ 2026-08-05: PR #24 — global_node_id 字段
        # 5 叉 line 1-2 子: 走 tree 公式, 编号 1-4093 (跟 tree_l1_4_l10 一致)
        # 5 叉 line 3-5 子: 5 叉 own 编号 10000+ (跟 tree 公式脱钩)
        # UI 渲染时根据数值范围决定显示 "N{real}" vs "available L{level} N{id}"
        gid = r.global_node_id
        is_5own = gid is not None and gid >= 10000  # 5 叉 own 编号
        node = {
            "available": bool(r.available) if r.available is not None else None,
            "businessLevel": r.business_level,
            "distId": r.dist_id,
            "globalNodeId": gid,  # ★ PR #24: tree 公式 or 5 叉 own 编号
            "is5Own": is_5own,    # ★ PR #24: True if 5 叉 own 编号 (line 3-5)
            "gold": "YES" if r.gold else ("NO" if r.gold is False else None),
            "iix": "YES" if r.iix else ("NO" if r.iix is False else None),
            "level": str(r.level) if r.level is not None else None,
            "maxLines": str(r.max_lines) if r.max_lines is not None else None,
            "name": r.name,
            "parentId": r.parent_id,
            "parentLineId": str(r.parent_line_id) if r.parent_line_id is not None else None,
            "pv": str(r.pv) if r.pv is not None else "0",
            "rank": r.rank,
            "status": r.status,
            "activity_status_id": r.activity_status_id,
            "visibility": bool(r.visibility) if r.visibility is not None else None,
            "org_pv": str(r.org_pv) if r.org_pv is not None else "0",
            "personal_customer_pv": str(r.personal_customer_pv) if r.personal_customer_pv is not None else "0",
            "has_subscription": "T" if r.has_subscription else ("F" if r.has_subscription is not None else None),
            "is_qualified": "T" if r.is_qualified else ("F" if r.is_qualified is not None else None),
            "status_color": r.status_color,
            "rows": str(r.rows) if r.rows is not None else None,
            "max_rows": str(r.max_rows) if r.max_rows is not None else None,
            "children": [],  # 后填
        }
        nodes_by_id[r.dist_id] = node
        # 按 parent 分组 (None = 顶层 root)
        parent_key = r.parent_id  # 顶层 = None
        children_by_parent.setdefault(parent_key, []).append(node)

    # 3. 拼 children 树 (顶层 parent_id IS NULL 的作为 root)
    root_nodes = children_by_parent.get(None, [])
    if not root_nodes:
        raise HTTPException(500, "original_tree_nodes 表里没有 parent_id IS NULL 的根节点")
    if len(root_nodes) > 1:
        # 多 root 不符合业务, 取第一个
        # (按 id 升序, ORDER BY id 已保证)
        root_nodes = [root_nodes[0]]

    def _attach_children(node):
        """递归把 children_by_parent 的子节点 attach 到 node.children"""
        kids = children_by_parent.get(node["distId"], [])
        # ★ 2026-08-05: 按 officev2 line 排 (parent_line_id 1-5) — 等同 BFS bit_reverse 排
        # 业务: line 1 → BFS 0 → gnode 2, line 2 → BFS 1 → gnode 4, line 3 → BFS 2 → gnode 3, line 4 → BFS 3 → gnode 5
        # (L1 按位反转排列, 严格 2, 4, 3, 5)
        # 旧 PR #32 按 global_node_id 升序排 (2, 3, 4, 5) 跟 BFS 排冲突 (BFS 是 2, 4, 3, 5)
        # 同一 line 多个节点按 gnode 升序排 (defensive, 实际很少见)
        kids.sort(key=lambda c: (int(c.get("parentLineId") or 0), c["globalNodeId"] if c["globalNodeId"] is not None else 0))
        node["children"] = kids
        for k in kids:
            _attach_children(k)

    root = root_nodes[0]
    _attach_children(root)
    return root


@app.get("/original-tree")
def original_tree_page():
    """原版网体可视化页面 (独立页面, 浏览器新 tab 打开)."""
    p = os.path.join(STATIC_DIR, "original_tree.html")
    if os.path.isfile(p):
        return FileResponse(p, media_type="text/html")
    raise HTTPException(404, "static/original_tree.html not found")


@app.get("/favicon.ico")
def favicon():
    """静默 favicon 请求（浏览器自动请求，避免 404 噪音）"""
    # 1x1 透明 PNG（最小响应体）
    import base64
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )
    from fastapi.responses import Response
    return Response(content=png, media_type="image/png")


@app.get("/health")
def health(db: DbSession = Depends(get_db)):
    """健康检查 + 数据库统计"""
    repo = SessionRepository(db)
    return {
        "status": "ok",
        "version": "0.3.0",
        "providers": [{"name": p.config.name, "state": p.breaker.get_stats()["state"]} for p in providers],
        "db": {
            "sessions": repo.count_sessions(),
            "messages": repo.count_messages(),
        },
    }


@app.get("/v1/models")
def list_models():
    """列出所有 Provider 及其健康状态"""
    return {"providers": router.list_health()}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: DbSession = Depends(get_db)):
    """非流式对话：自动 fallback 到下一个 provider"""
    repo = SessionRepository(db)
    sid, sess = repo.get_or_create(req.session_id, primary_provider=req.provider)
    history = repo.get_history_openai(sid, max_messages=settings.max_history)

    messages = []
    if req.system_prompt:
        messages.append({"role": "system", "content": req.system_prompt})
    messages.extend(history)
    messages.append({"role": "user", "content": req.message})

    result = router.chat_with_fallback(
        messages,
        provider_name=req.provider,
        model_name=req.model,
        temperature=req.temperature,
        max_tokens=settings.max_tokens,
    )

    if not result["ok"]:
        db.rollback()
        raise HTTPException(status_code=503, detail=result)

    # 写库：user + assistant 两条消息
    repo.append_message(
        sid=sid, role="user", content=req.message,
        provider=req.provider, model=req.model,
    )
    repo.append_message(
        sid=sid, role="assistant", content=result["reply"],
        provider=result["provider"], model=result["model"],
        prompt_tokens=result["usage"]["prompt_tokens"],
        completion_tokens=result["usage"]["completion_tokens"],
        total_tokens=result["usage"]["total_tokens"],
        is_fallback=result["fallback_used"],
        latency_ms=result["latency_ms"],
    )
    db.commit()

    log.info(
        f"📊 session={sid[:8]}... provider={result['provider']} model={result['model']} "
        f"total={result['usage']['total_tokens']} attempts={len(result['attempts'])} "
        f"fallback={'Y' if result['fallback_used'] else 'N'}"
    )

    return ChatResponse(
        session_id=sid,
        reply=result["reply"],
        provider=result["provider"],
        model=result["model"],
        usage=result["usage"],
        latency_ms=result["latency_ms"],
        attempts=result["attempts"],
        fallback_used=result["fallback_used"],
    )


@app.post("/chat/stream")
def chat_stream(req: ChatRequest, db: DbSession = Depends(get_db)):
    """SSE 流式对话：自动 fallback + 完成后写库"""
    repo = SessionRepository(db)
    sid, sess = repo.get_or_create(req.session_id, primary_provider=req.provider)
    # 关键：立刻 commit session 创建。否则 FastAPI 关闭 db 时会 rollback，
    # 导致 generator 内部的 db2 通过 sid 找不到 session，messages 因 FK 报错被吞。
    db.commit()
    history = repo.get_history_openai(sid, max_messages=settings.max_history)

    messages = []
    if req.system_prompt:
        messages.append({"role": "system", "content": req.system_prompt})
    messages.extend(history)
    messages.append({"role": "user", "content": req.message})

    def event_generator():
        # 整段用 try/except 包裹，任何异常都 yield error 事件给前端，
        # 避免 generator 崩溃导致 SSE 连接中断、前端"什么也收不到"
        try:
            # 第一帧：发送 session_id + provider 选择
            primary = router.pick(req.provider, req.model)
            if primary is None:
                # provider 名不存在（前端传了未配置的 provider）
                avail = [p.config.name for p in providers]
                yield f"event: error\ndata: {json.dumps({'error_type': 'unknown_provider', 'error_msg': f'provider={req.provider!r} 未配置；可用: {avail}'}, ensure_ascii=False)}\n\n"
                return
            yield f"event: start\ndata: {json.dumps({'session_id': sid, 'primary_provider': primary.config.name}, ensure_ascii=False)}\n\n"

            full_reply = ""
            full_reasoning = ""
            provider_used = None
            model_used = None
            fallback_used = False
            usage = {}
            for chunk in router.chat_stream_with_fallback(
                messages,
                provider_name=req.provider,
                model_name=req.model,
                temperature=req.temperature,
                max_tokens=settings.max_tokens,
            ):
                if not chunk.get("ok"):
                    yield f"event: error\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                    return
                if chunk.get("is_final"):
                    full_reply = chunk.get("reply", "")
                    full_reasoning = chunk.get("reasoning", "")
                    provider_used = chunk.get("provider")
                    model_used = chunk.get("model")
                    usage = chunk.get("usage", {})
                    # 完整事件：含 reasoning（用于历史会话展示）
                    yield (
                        f"event: done\n"
                        f"data: {json.dumps({'usage': usage, 'provider': provider_used, 'reasoning': full_reasoning}, ensure_ascii=False)}\n\n"
                    )
                else:
                    # 推理过程 / 正常内容 各自独立 SSE event
                    event_type = chunk.get("event", "delta")  # reasoning_delta / content_delta
                    if chunk.get("fallback_used"):
                        fallback_used = True
                    yield (
                        f"event: {event_type}\n"
                        f"data: {json.dumps({'delta': chunk.get('delta', ''), 'provider': chunk.get('provider')}, ensure_ascii=False)}\n\n"
                    )

            # 完成后写库
            if full_reply:
                try:
                    db2 = SessionLocal()
                    try:
                        repo2 = SessionRepository(db2)
                        if not repo2.get(sid):
                            log.error(f"❌ session={sid[:8]}... 不存在，写库失败（endpoint commit 漏了？）")
                            return
                        repo2.append_message(
                            sid=sid, role="user", content=req.message,
                            provider=req.provider, model=req.model,
                        )
                        repo2.append_message(
                            sid=sid, role="assistant", content=full_reply,
                            reasoning=full_reasoning or None,
                            provider=provider_used, model=model_used,
                            prompt_tokens=usage.get("prompt_tokens", 0),
                            completion_tokens=usage.get("completion_tokens", 0),
                            total_tokens=usage.get("total_tokens", 0),
                            is_fallback=fallback_used,
                        )
                        db2.commit()
                        log.info(f"💾 session={sid[:8]}... 已持久化（{len(full_reply)} 字 + {len(full_reasoning)} 字思考）")
                    finally:
                        db2.close()
                except Exception as e:
                    log.error(f"❌ 持久化失败: {e}")
            else:
                log.warning(f"⚠️ 流式未产出 reply，跳过写库 session={sid[:8]}...")
        except Exception as e:
            # 任何 yield 抛异常都被这里捕获，保证 SSE 连接优雅关闭 + 报错给前端
            log.exception(f"❌ event_generator 异常: {e}")
            try:
                yield f"event: error\ndata: {json.dumps({'error_type': 'internal_error', 'error_msg': str(e)}, ensure_ascii=False)}\n\n"
            except Exception:
                pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/sessions/{sid}")
def get_session(sid: str, db: DbSession = Depends(get_db)):
    """获取会话的精简信息（不含消息）"""
    repo = SessionRepository(db)
    s = repo.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    return s.to_meta_dict()


@app.get("/sessions/{sid}/messages")
def get_session_messages(
    sid: str,
    db: DbSession = Depends(get_db),
):
    """获取会话的完整消息列表（含 reasoning + tokens + provider）—— 侧栏点会话时调用"""
    repo = SessionRepository(db)
    s = repo.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    messages = repo.get_messages(sid)
    return {
        "session_id": sid,
        "title": s.title,
        "primary_provider": s.primary_provider,
        "message_count": len(messages),
        "messages": [m.to_dict() for m in messages],
    }


@app.delete("/sessions/{sid}")
def clear_session(sid: str, db: DbSession = Depends(get_db)):
    """删除会话（CASCADE 删 messages）"""
    repo = SessionRepository(db)
    if not repo.delete(sid):
        raise HTTPException(404, "session not found")
    db.commit()
    return {"ok": True}


@app.get("/sessions")
def list_sessions(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数，1-100"),
    q: Optional[str] = Query(None, description="搜索关键词：命中 title 或任意消息内容"),
    db: DbSession = Depends(get_db),
):
    """列出所有会话，支持翻页 + 关键词搜索（侧栏用）"""
    repo = SessionRepository(db)
    items, total = repo.list_sessions(page=page, page_size=page_size, q=q)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "count": len(items),
        "sessions": [s.to_meta_dict() for s in items],
    }


@app.patch("/sessions/{sid}")
def update_session(
    sid: str,
    payload: dict,
    db: DbSession = Depends(get_db),
):
    """修改会话属性（目前仅支持改 title）"""
    repo = SessionRepository(db)
    if "title" in payload:
        if not repo.update_title(sid, payload["title"]):
            raise HTTPException(404, "session not found")
    db.commit()
    return {"ok": True}


# ★ 2026-07-12 移除:Stage 2C RAG / 知识库 整段(7 个端点 + 5 个 Pydantic model)
#    - POST /documents / GET /documents / DELETE /documents/{id}
#    - POST /documents/upload / POST /documents/import
#    - POST /search
#    - POST /chat/rag
# 业务侧只保留 chat (multi-turn) + skills (网体算法) 两条主线。
# 升级前用户上传的 documents 仍在 SQLite DB 里(Base.metadata.create_all 不会主动 drop),
# 如需彻底清理,可用 sqlite3 手动 DROP TABLE documents / chunks。


# ============== Skills ==============
# ★ 2026-07-15: skill_2 (二叉) 已彻底下线,只保留 skill_5_3 (5 叉按位反转)。
#   - skill_5_3 走 /skills/skill_5_3/batch/run (preview + commit_preview)
#   - Skill2RunRequest / _DEFAULT_SKILL_2_TREE / run_skill_2 / /skills/skill_a/* alias 全部删除
#   - /skills list_skills 只返回 skill_5_3


@app.get("/skills")
def list_skills():
    """列出已注册的 Skills(前端 fetchSlashSkillsCache 用,决定 skill 是否 available)

    ★ 2026-07-15 PR #10 收尾: skill_2 下线,只暴露 skill_5_3。
    """
    labels = {
        "skill_5_3": "按位反转添加新成员 (5 叉树, base-5 digit reversal)",
    }
    return {
        "skills": [
            {
                "id": sid,
                "label": labels[sid],
                "available": _skill_runners.get(sid) is not None,
                "endpoint": f"/skills/{sid}/run",
                "load_error": _skill_load_errors.get(sid),
                "batch_endpoint": f"/skills/{sid}/batch/run",
            }
            for sid in ("skill_5_3",)
        ]
    }


class SkillNRunRequest(BaseModel):
    """Skill N (历史 N 叉,已 deprecated) · 新成员加盟最优布局(N 叉树)

    ★ 2026-07-11: skill_3 / skill_4 / skill_5 已下线,本 Model 保留仅为兼容旧前端 replay。
       ★ 2026-07-13: skill_5_1 / skill_5_2 也下线。
       ★ 2026-07-15: skill_2 (二叉) 也下线,当前活跃 skill 只有 skill_5_3,走专属 endpoint + 专属 Model。
    """
    pv: int = Field(..., gt=0, le=1_000_000, description="新成员 PV")
    name: str = Field("", description="新成员姓名(可选,留空自动命名 '新成员')")
    # 用 builtin `dict` 避免 Python 3.14 PEP 649 + Pydantic ForwardRef 解析失败
    tree: Optional[dict] = Field(None, description="原生 skill_N 格式树(uid/pv/depth/children)")
    include_pairing: bool = Field(True, description="是否计入对等奖金")
    use_local_default: bool = Field(False, description="(历史字段,已 no-op) 加载本地 json/Tree_Nary.json")
    write_back: bool = Field(
        False,
        description="(历史字段,已 no-op) True=实际修改 json/Tree_Nary.json;False=仅计算不写盘",
    )
    lock_id: Optional[str] = Field(
        None,
        description=(
            "悲观锁 id。"
            "  - write_back=false (预览): 服务端 try acquire 锁,成功会返回新 lock_id;被占返回 423。"
            "  - write_back=true  (写盘): 必须带 lock_id(预览阶段拿到的);不带 → 400;锁失效 → 409。"
        ),
    )


class SkillBatchMember(BaseModel):
    """批量挂载单个成员的信息"""
    pv: int = Field(..., gt=0, le=1_000_000, description="个人消费 PV")
    name: str = Field("", description="姓名(可空,留空自动命名 '新成员N')")


class SkillBatchRunRequest(BaseModel):
    """Skill N (历史 N 叉,已 deprecated) 批量 · 一次性挂载多位新成员

    ★ 2026-07-11: skill_3 / skill_4 / skill_5 batch 已下线,本 Model 保留仅为兼容旧前端 replay。
       ★ 2026-07-13: skill_5_1 / skill_5_2 batch 也下线,当前活跃的批量只剩 skill_5_3,走专属 endpoint + 专属 Model。

    算法:按 PV 降序 greedy sequential 挂载,内存里先模拟完整批,
    最后一次性原子写回 JSON(find 模式不写盘)。

    锁机制与 SkillNRunRequest 一致:
        - 预览: 拿锁,返回 lock_id
        - 写盘: 必须带 lock_id;不带 → 400;锁失效 → 409

    ★ 2026-07-15: skill_2 (二叉) 也下线,只剩 skill_5_3 走专属 endpoint。
    """
    members: List[SkillBatchMember] = Field(..., min_length=1, description="新成员列表")
    include_pairing: bool = Field(True, description="是否计入对等奖金")
    use_local_default: bool = Field(True, description="加载本地 json/Tree_Nary.json(每个 skill 用各自的 json)")
    order: str = Field(
        "pv-desc",
        pattern="^(pv-desc|pv-asc|input)$",
        description="挂载顺序:pv-desc 大 PV 先,pv-asc 小 PV 先,input 按输入顺序",
    )
    write_back: bool = Field(
        False,
        description="True=实际修改 json/Tree_Nary.json(按 skill_id 写对应文件);False=仅计算不写盘(find 模式)",
    )
    lock_id: Optional[str] = Field(
        None,
        description="悲观锁 id。语义同 SkillNRunRequest.lock_id。",
    )


def _html(s: Any) -> str:
    """最小 HTML escape(仅用于 chat 卡片 innerHTML 安全)"""
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ============================================================
# Skill 5_3 · 「按位反转 (base-5 digit reversal)」批量添加新成员(纯计算预览)
# ============================================================
# 命名规则延续 skill_X = X 叉树;5_3 表示「5 叉树的 #3 派生」,即按 base-5 digit reversal
# 规律顺次挂入新成员,逐步计算 commission/pairing/total。
#
# ★ 2026-07-13: skill_3 / skill_4 / skill_5 / skill_5_1 / skill_5_2 全部下线
#   当前仅剩 skill_5_3 (5 叉派生 + 按位反转)
#   - 不读不写本地 json/Tree*.json(从空 5 叉 root 树开始模拟,无 json 副作用)
#   - 不需要 tree_lock(没有共享文件)
#   - order 强制 = 'bitrev' (按位反转语义要求固定顺序)
#   - write_back 参数被忽略,永远不写盘(history 仅供前端预览/复盘)
#   - 返回 history 数组 (每步 uid/parent_uid/basic/pairing/total/lift_pct)

class Skill53RunRequest(BaseModel):
    """Skill 5_3 · 按位反转批量加新成员(预览)

    与历史 skill_3/4/5 batch 的差异:
        - 没有 use_local_default(永远从空 5 叉 root 树开始,不读本地 json)
        - 没有 order(按位反转语义要求固定 input 顺序,后端强制)
        - 没有 write_back(永远不写 json/Tree_5ary.json)
    """
    members: List[SkillBatchMember] = Field(..., description="新成员列表(每位 pv + 可选姓名),按输入顺序挂入")
    include_pairing: bool = Field(True, description="是否计入对等奖金")


# skill_5_3 (按位反转 base-5 digit reversal) 单独的本地空 5 叉根路径
#   skill_5_3 永远 local_output=False(纯计算), 所以这份文件保持初始「空 5 叉根」状态。
#   通过 tools/init_tree_empty_5_3.py 一次性 init。
SKILL_5_3_DEMO_TREE_PATH: str = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "json", "Tree_empty_5_3.json",
)


def _max_depth(node) -> int:
    """递归求 Node5 树的最大 depth(用于日志摘要)"""
    if not node.children:
        return node.depth
    return max(_max_depth(c) for c in node.children)


def _node5_to_jstree_dict(
    node,
    dist_id_map: Optional[Dict[int, str]] = None,
) -> Dict[str, Any]:
    """把 Node5(运行时类)递归转成 jsTree 风格的 dict(用于本地演示落盘)

    输出字段对应 officev2 导出格式(主用于 frontend render + 跨进程调试):
        distId      : 二级优先级
                      1. dist_id_map[n.uid] 原值(officev2 真实成员, 保留 "N5637590.1" 原格式)
                      2. fallback: f"N5637590.{abs(uid)}" (本地合成成员, 2026-07-17 PR #50 改, 跟 commit_preview 格式一致)
        name        : 优先用 dist_id_map 原值,否则 node.name
                      ★ 同上,officev2 真实成员的 name 含中文,加载后落到 Node5.name,
                        写盘时直接从原 dict 读更稳(避免编码 round-trip 坑)
        pv          : node.pv
        maxLines    : node.max_children
        level       : node.depth + 1  (jsTree 从 1 计数,Node5 从 0 计数)
        parentLineId: 在 parent.children 中的 index + 1 (1-based;root 为特殊 null)
        children    : 递归 + ★ 补全 avail 占位(maxLines - len(real children) 个)

    ★ 2026-07-11 v4: 本地合成 distId 格式
      用户反馈 (2026-07-11, v3 后又改): 新合成成员 distId 应该跟 officev2 真实段一致
      (张五 N-5637593 = "N" + "-" + 7 位数字, 总 9 字符)。
      之前 v3 的 "N-7{rank:04d}" 是 4 位数字, 总 6 字符, 跟 officev2 真实段位数不一致。
      新方案: "N-7{abs(uid):06d}"  = "N-7" 固定前缀 + 6 位补 0 = 7 位数字总, 跟张五一致
      ★ "7" 段 = 本地合成 marker, 跟 officev2 "5" 段 (N5637590.1) "6" 段 (N-5637591) 区分
        abs(uid) 从 1 累加 (skill_5_helpers 配合 skill_5_3, global_rank = 1, 2, 3, ...)
        → "N-7000001" "N-7000002" "N-7000007" ...

    ★ 2026-07-05 v3: 补全 avail 占位
      之前只递归真实子节点,丢失了"5 个槽位"的结构信息 — 写盘后 JSON 里每个节点
      只有真实子,空槽位完全不见,前端 _tree_render_children 渲染时虽然能根据
      maxLines 自动补 L{i}·空位,但 avail 节点特有的字段(parentId / businessLevel
      等)丢失。补全后下次 read JSON 能看到完整 officev2 风格结构。

    ★ 2026-07-06 v2: dist_id_map 参数
      dist_id_map 是 load_tree_from_jstree_file 返回的 {uid: distId 原字符串} 索引。
      传入后,_walk 优先查 map,n.uid 在 map 里就保留 officev2 原格式(防止 .1 后缀、负数等
      特殊格式被 f"N{uid}" 覆盖)。新写入的负数 uid 不在 map 里,fallback 到
      f"N-7{abs(uid):06d}" (2026-07-11 v4 新格式, 跟 officev2 一致)。
    """
    if dist_id_map is None:
        dist_id_map = {}

    def _walk(n, parent_line_id: Optional[int]) -> Dict[str, Any]:
        # 处理 max_children 容错(可能是字符串/None/0)
        try:
            max_c = int(n.max_children) if n.max_children is not None else 5
        except (TypeError, ValueError):
            max_c = 5
        if max_c <= 0:
            max_c = 5

        # ★ 节点自己的 distId: 二级优先级
        #   1. dist_id_map (officev2 真实成员, 保留 "N5637590.1" / "N-5637591" 原格式)
        #   2. fallback: f"N-7{abs(uid):06d}" (本地合成, 跟 officev2 真实段位数一致)
        if n.uid in dist_id_map:
            own_dist_id = dist_id_map[n.uid]
        else:
            # ★ 2026-07-11 v4: N-7 固定前缀 + abs(uid) 6 位补 0 = 7 位数字
            #   "7" 段是本地合成 marker, 跟 officev2 "5" "6" 段区分
            own_dist_id = f"N5637590.{abs(n.uid)}"

        # ★ 2026-07-14 v6: 算出本节点的「有效激活线数」, avail 占位和真实子都带这字段
        #   - 默认 max_active_lines (用户配置, 默认 2)
        #   - L1+L2 都挂满真实成员 → 4
        #   - L1-L4 都挂满 → 5
        #   - 上限: max_children (5 叉 = 5)
        _effective_active = n.effective_max_active_lines()

        # ★ 递归真实子 + 补全 avail 占位
        children_list = [_walk(c, i + 1) for i, c in enumerate(n.children)]
        avail_count = max_c - len(n.children)
        for j in range(avail_count):
            _avail_line = len(n.children) + j + 1
            # ★ 2026-07-14 v6: avail 是否锁定 (line > effective_max_active_lines)
            _avail_locked = _avail_line > _effective_active
            children_list.append({
                "available": True,
                "businessLevel": None,
                "distId": None,
                "gold": None,
                "iix": None,
                "level": 0,
                "maxLines": 0,
                "parentId": own_dist_id,  # ★ 用节点自己的原 distId(不再是裸 "N{uid}")
                "parentLineId": _avail_line,  # 1-based,接在真实子之后
                "pv": None,
                "rank": None,
                "status": 0,
                "visibility": True,
                "effectiveMaxActiveLines": _effective_active,  # ★ v6: 透传给前端渲染 locked 状态
                "isLocked": _avail_locked,  # ★ v6: True = L3-L5 默认锁
            })

        d: Dict[str, Any] = {
            "distId": own_dist_id,
            "name": n.name or "",
            "pv": n.pv,
            "maxLines": max_c,
            "level": n.depth + 1,
            "parentLineId": parent_line_id,
            "available": False,  # 真实演示节点,非占位
            "maxActiveLines": n.max_active_lines,  # ★ v6: 业务初始值
            "effectiveMaxActiveLines": _effective_active,  # ★ v6: 当前动态值
            "children": children_list,
        }
        return d
    return _walk(node, None)


# ★ 2026-07-12: skill_5_3 — 「按位反转 (base-5 digit reversal)」添加新成员
#   - 来源: TreeGenerate/verify_l6.py 反推的 2 叉 visio 树型图规律,推广到 5 叉树
#   - 算法: L+1 阶段 5^L 个新成员,槽位 = bit_reverse_base5(i, L) = i 的 base-5 表示 (L 位) 倒序
#   - 数据结构: history 数组(每步含 ancestor_chain, parent_dist_id, member_dist_id)
#   - 简化: 不读不写 json (纯计算)
#   - 从空 5 叉 root 起步, 永远



# ★ 2026-07-12: skill_5_3 — 「按位反转 (base-5 digit reversal)」添加新成员
#   - 来源: TreeGenerate/verify_l6.py 反推的 2 叉 visio 树型图规律,推广到 5 叉树
#   - 算法: L+1 阶段 5^L 个新成员,槽位 = bit_reverse_base5(i, L) = i 的 base-5 表示 (L 位) 倒序
#   - 简化: 不读不写 json (纯计算)
#   - 从空 5 叉 root 起步, 永远
# ★ 2026-07-13: skill_5_1 / skill_5_2 已下线,skill_5_3 是当前唯一活跃的 5 叉派生

@app.post("/skills/skill_5_3/batch/run")
def run_skill_5_3_batch(req: Skill53RunRequest):
    """Skill 5_3 · 按位反转 (base-5 digit reversal) 添加新成员

    算法: L+1 阶段 5^L 个新成员,槽位 = bit_reverse_base5(i, L) = i 的 base-5 表示 (L 位) 倒序。
    全员 5 列都挂,满 5 列时整体参与 commission。
    """
    if _skill_runners.get("skill_5_3") is None:
        raise HTTPException(
            503,
            f"skill_5_3 未加载:{_skill_load_errors.get('skill_5_3') or '请确认 skills/skill_5_3.py 存在'}",
        )

    try:
        from skill_5_lib import Node5
        from skill_5_3 import (
            simulate_addition_bitrev,
            total_basic as _tb_53,
            pairing_bonus as _pb_53,
            total_profit as _tp_53,
        )
        # ★ 2026-07-14 v8 fix: 每次 batch 请求重置算法跨调用状态
        #   - _consumed_x (X 坐标顺序挂入) 应该在每个 batch 重新从 X=12 开始
        #     用户场景: 用户每次"提交"一批新成员, 期望从预设 4 槽位头部开始挂入
        #     之前 _consumed_x 跨请求保留, 导致 2nd batch 跳过 X=12/13
        #   - add_user_bitrev._step_state 同样需要重置
        #   - 业务动机: 用户的"挂入"动作是一次性 batch 操作, 不跨 batch 累积
        # ★ 2026-07-15 PR #17: 删了 _reset_find_next_slot_state + _find_next_slot_bitrev_skip_col0
        #   严格按位反转不再需要跨调用状态 — 每次 step 直接算
        from skill_5_3 import (
            add_user_bitrev as _add_user_bitrev_fn,
        )
        if hasattr(_add_user_bitrev_fn, "_step_state"):
            delattr(_add_user_bitrev_fn, "_step_state")
    except ImportError as _imp_e:
        raise HTTPException(503, f"无法导入 skill_5_3 依赖:{_imp_e}")

    if req.include_pairing is False:
        log.info("skill_5_3: include_pairing=False(纯 basic 模式)")

    pvs = [m.pv for m in req.members]
    names = [m.name for m in req.members]

    # ★ 2026-07-16 PR #39: 从 DB 构建 Node5 树 (单一数据源, 跟渲染层 _build_tree_from_db 一致)
    #   之前 (PR #8/19/22): 读 json/Tree_empty_5_3.json → fallback 空 root
    #   现在 (PR #39): DB members 表是权威, 实时从 DB 构 Node5 树
    #   - root: parent_dist_id="" + slot_line_id=0 的 member
    #   - 子节点: parent_dist_id + slot_line_id 索引
    #   - avail 占位: 父的 real_children < maxLines 时补
    #   - start_rank: 从 DB 找最大 N-7XXXXXX 编号 + 1 (新成员 uid 接着递增, 跟 commit_preview 一致)
    try:
        from database import SessionLocal as _RunSL
        with _RunSL() as _db:
            tree, parent_dist_id_map = _build_node5_tree_from_db(_db)
            # start_rank 从 DB 算 (N-7XXXXXX 格式)
            start_rank = _compute_max_synthetic_dist_id_from_db(_db)
    except Exception as _e:
        log.exception("skill_5_3 _build_node5_tree_from_db 失败")
        raise HTTPException(500, f"从 DB 构建 tree 失败: {_e}")

    loaded_from = "DB (members)"  # ★ PR #39 标记: 树来源 = DB (替代 json path)

    log.info(
        f"🌳 skill_5_3: 从 DB 构建 5 叉根 "
        f"(root uid={tree.uid}, name='{tree.name}', depth={_max_depth(tree)}, "
        f"uid→distId 索引 {len(parent_dist_id_map)} 条, start_rank={start_rank})"
    )

    history: list
    try:
        history = simulate_addition_bitrev(
            tree, pvs,
            names=names,
            include_pairing=req.include_pairing,
            parent_dist_id_map=parent_dist_id_map,
            start_rank=start_rank,
        )
    except ValueError as _ve:
        raise HTTPException(400, f"skill_5_3 输入非法:{_ve}")
    except Exception as _e:
        log.exception("skill_5_3 模拟失败")
        raise HTTPException(400, f"skill_5_3 模拟失败:{_e}")

    final_basic = _tb_53(tree)
    final_pairing = _pb_53(tree) if req.include_pairing else 0.0
    final_total = _tp_53(tree, include_pairing=req.include_pairing)

    log.info(
        f"🎯 skill_5_3 预览: 输入 {len(pvs)} 位 → 实际挂入 {len(history)} 位 "
        f"(剩 {len(pvs) - len(history)} 位因树满被丢弃) · "
        f"final basic=${final_basic:.2f} pairing=${final_pairing:.2f} total=${final_total:.2f} "
        f"★ 按位反转 (base-5 digit reversal)"
    )

    return {
        "skill": "skill_5_3_batch",
        "skill_label": "按位反转添加新成员 (5 叉树, base-5 digit reversal)",
        "skill_id": "skill_5_3",
        "n_members": len(pvs),
        "n_mounted": len(history),
        "include_pairing": req.include_pairing,
        "order": "bitrev",             # ★ 按位反转 (5 叉 = base-5 digit reversal)
        "write_back": False,           # 永远不写
        "local_output": False,         # ★ skill_5_3 永远不写盘(纯计算, 无累积)
        "saved_to": None,
        "save_error": None,
        "loaded_from": loaded_from,    # 起算树来源(Tree_empty_5_3.json 路径 / None=空 root 起步)
        "history": history,
        "final_basic": round(final_basic, 4),
        "final_pairing": round(final_pairing, 4),
        "final_total": round(final_total, 4),
        # ★ 2026-07-14 v8: 写盘校验用 — 客户端把 commit_preview 的 fingerprint 传回
        #   服务端 validate 锁时如果盘上指纹变了 → 409 冲突
        # ★ 2026-07-15 fix: 永远从 SKILL_5_3_DEMO_TREE_PATH 读文件算 fingerprint (跟 commit_preview 一致)
        #   - 之前用 loaded_raw,但 fallback 分支 (兼容失败) 时 loaded_raw 可能是 None
        #     → 用空 dict 算 fingerprint, 跟 commit_preview 读真实文件算的不一致 → 409 永久不匹配
        #   - 修法: 永远从原始文件读, 跟 commit_preview 入口逻辑一致
        "tree_fingerprint": _compute_skill53_fingerprint(),
        "period_id": get_current_period_id(),  # 当前 ISO 周, 客户端写盘时一起传回
    }


def _compute_skill53_fingerprint() -> str:
    """★ 2026-07-16 PR #39: deprecated — DB-only 后, 不再需要 fingerprint

    之前 (PR #8): 从 SKILL_5_3_DEMO_TREE_PATH 读文件算 fingerprint (跟 commit_preview 一致)
    现在 (PR #39): DB 是权威, commit_preview 不读 json, 也不校验 fingerprint
    - run_skill_5_3_batch 仍调一次 (返空字符串保持 API 兼容)
    """
    return ""


# ============================================================
# ★ 2026-07-16 PR #39: skill_5_3 batch 写盘 endpoint (DB-only)
# ============================================================
# 业务动机: 跟渲染层 PR #39 一致, 树 view + 算法层都以 DB 为权威
#   之前 (PR #8/19/22): 真改 Tree_empty_5_3.json + 写 DB
#   现在 (PR #39):     只写 DB (members + pv_ledger), json 不再读写
#
# 流程:
#   1. 前端先调 /skills/skill_5_3/batch/run 拿 preview history
#   2. 用户点 "⚠️ 写盘" 按钮 → 前端调 /api/skill_5_3/commit_preview
#   3. 后端:
#      - 分配新 distId (从 DB 找 max N-7XXXXXX + 1)
#      - 解析 PREVIEW-N → 本 batch 真实 distId
#      - 校验父在 DB 里存在 + 槽位空闲
#      - INSERT Member + INSERT PVLedger (单事务)
#   4. 前端收到 success, 重新渲染 Tree 视图 (新成员在)
#
# 失败模式:
#   - 400: history 里的 parent_dist_id 找不到 / 槽位已被占 / slot_line_id 超父 max_lines
#   - 500: 写盘失败 (DB)


class Skill53CommitItem(BaseModel):
    """commit_preview 单条历史 — 对应 batch_preview 的一条 AdditionStep"""
    parent_dist_id: str = Field("", description="父节点 distId;空串=父是 root")
    parent_line_id: int = Field(..., ge=1, le=5, description="在父节点的第几条线 (1..maxLines)")
    name: str = Field("", description="新成员姓名")
    pv: int = Field(..., ge=0, description="新成员 PV")
    # 来自 preview 阶段: 新成员临时 distId (PREVIEW-N), 写盘后会换成 N-7XXXXXX
    member_dist_id: str = Field("", description="preview 阶段分配的新成员 distId (PREVIEW-N), 写盘后会被替换")
    # ★ 2026-07-16 PR #41: 角色 (写入 DB; 留空 = 默认 consumer)
    role: str = Field("consumer", description=f"角色; 可选: {sorted(VALID_ROLES)}; 留空=consumer")


class Skill53CommitRequest(BaseModel):
    """skill_5_3 batch 写盘请求"""
    history: List[Skill53CommitItem] = Field(..., min_length=1, description="preview 阶段返回的 history 列表")
    # ★ 2026-07-16 PR #39: tree_fingerprint 字段保留 (兼容旧前端), 后端忽略
    tree_fingerprint: str = Field("", description="preview 阶段返回的 tree 指纹;PR #39 后不再校验")
    period_id: str = Field(..., description="写盘关联的 ISO 周编号 (e.g. 2026-W28); 来自 preview 响应")


@app.post("/api/skill_5_3/commit_preview")
def api_skill_5_3_commit_preview(
    req: Skill53CommitRequest,
    db: DbSession = Depends(get_db),
):
    """★ 2026-07-16 PR #39: skill_5_3 batch 写盘 — 只写 DB (members + pv_ledger)

    之前 (PR #8/19/22): 真改 Tree_empty_5_3.json + 写 DB
    现在 (PR #39):     只写 DB (members + pv_ledger), json 不再读写 (DB 是单一数据源)
    - 不再需要 _get_tree_lock / fingerprint 校验
    - 不再需要 _find_max_synthetic_dist_id / _replace_avail_with_real (json 操作)
    - PREVIEW-N → N-7XXXXXX 映射保留 (算法层 preview 仍分配 PREVIEW-N 临时 distId)

    流程:
      1. 分配新 distId (从 DB 找 max N-7XXXXXX + 1)
      2. 解析 parent_dist_id (PREVIEW-N → 本 batch 真实 distId)
      3. 校验父在 DB 里存在 + 槽位空闲
      4. 任何 step 失败 → 整批回滚 (db.rollback)
      5. 全部成功 → INSERT Member + INSERT PVLedger (单事务)
      6. 返新成员列表

    Returns:
        {
            "ok": True,
            "skill_id": "skill_5_3",
            "wrote_to": "DB (members + pv_ledger)",  # ★ PR #39 改
            "n_members_written": N,
            "members": [{member_dist_id, name, pv, parent_dist_id, parent_line_id, period_id}, ...],
            "period_id": "2026-W28",
            "tree_fingerprint": "",  # ★ PR #39 改: 不再需要 fingerprint
        }
    """
    skill_id = "skill_5_3"

    try:
        # 1. 分配新 distId
        # ★ 2026-07-17 PR #50: 直接用 history 里的 PREVIEW-N 编号作为 N5637590.N
        #   - preview 算法算 PREVIEW-N 时用 start_rank = _compute_max_synthetic_dist_id_from_db
        #   - commit 跟 preview 用同一 N 号 → 写盘后 DB max 增加, 下次 preview start_rank 同步增长
        #   - 保证 distId 连续 (.2, .3, .4) 且不撞 (DB 真实 max 已包含)
        #
        #   旧 (PR #39): commit 用 _compute_max_synthetic_dist_id_from_db 算 max_dist, 给 N-7XXXXXX
        #   - commit 跟 preview 各自用 DB max, 跟 PR #45 的 "batch 内允许前置 PREVIEW" 不冲突
        #
        #   修 (PR #50): commit 用 PREVIEW-N 编号 = N5637590.N (直接转换, 不走 max_dist 累加)
        #   - 这样跟 preview 的 N 号严格一致, 避免 preview 跟 commit 间的 +1 步进 gap
        max_dist = _compute_max_synthetic_dist_id_from_db(db)
        new_members: List[Dict[str, Any]] = []
        _preview_dist_id_map: Dict[str, str] = {}

        # ★ 2026-07-16 PR #45: 两阶段 (allocate → validate), 修 batch 内父挂前置 PREVIEW 的 bug
        #   旧流程: 单 loop 内 "分配 distId + 解析 PREVIEW parent + 校验 parent 在 DB" — 第 3 步起,
        #     parent 解析出 N-7XXXXXX (#1 真实 distId), 但 #1 还没 INSERT, DB 找不到 → 400
        #   新流程:
        #     Pass 1 (allocate): 给每个 step 分配 distId, 收集到 batch_dist_ids set,
        #       同时构建 _preview_dist_id_map (PREVIEW-N → 真实 distId)
        #     Pass 2 (validate): 解析每个 step 的 parent (PREVIEW-N → 真实 distId),
        #       父可来自 2 处: (a) 本 batch 的 batch_dist_ids (前置 step) 或 (b) DB
        #       校验槽位空闲: DB 的用 SQL, batch 内的用 in-memory slot_owners dict
        #     Pass 3 (insert): 跟旧逻辑一样, 单事务 INSERT
        #   这样 4 成员 (#1 root L1, #2 root L2, #3 #1 L1, #4 #2 L1) 全能一次写成功
        for i, h in enumerate(req.history):
            # ★ 2026-07-17 PR #50: 用 PREVIEW-N 编号作为 N5637590.N (跟 preview N 号一致)
            #   - history 里有 PREVIEW-N → new_dist_id = f"N5637590.{N}"
            #   - history 里有非 PREVIEW (兼容老数据) → 走 max_dist 累加
            if h.member_dist_id and h.member_dist_id.startswith("PREVIEW-"):
                try:
                    _n = int(h.member_dist_id[8:])
                    new_dist_id = f"N5637590.{_n}"
                    if _n > max_dist:
                        max_dist = _n
                except (ValueError, IndexError):
                    max_dist += 1
                    new_dist_id = f"N5637590.{max_dist}"
            else:
                max_dist += 1
                new_dist_id = f"N5637590.{max_dist}"
            # ★ PR #19 fix: PREVIEW-N (h.member_dist_id) → 真实 distId 映射
            if h.member_dist_id and h.member_dist_id.startswith("PREVIEW-"):
                _preview_dist_id_map[h.member_dist_id] = new_dist_id
            new_members.append({
                "member_dist_id": new_dist_id,
                "name": h.name,
                "pv": int(h.pv),
                "parent_dist_id": h.parent_dist_id or "",  # 原值, 含 PREVIEW
                "parent_line_id": h.parent_line_id,
                "period_id": req.period_id,
                "role": _normalize_role(getattr(h, "role", None)),
                "business_level": _normalize_business_level(getattr(h, "business_level", None)),  # ★ PR #75
            })

        # Pass 2: 解析所有 parent + 校验 (parent 可在 batch 内 set 中, 也可在 DB 中)
        batch_dist_ids: set = {nm["member_dist_id"] for nm in new_members}
        slot_owners: Dict[Tuple[str, int], int] = {}  # (parent, slot) -> step (1-based)
        for i, nm in enumerate(new_members):
            h = req.history[i]
            actual_parent_dist_id = nm["parent_dist_id"]
            if actual_parent_dist_id and actual_parent_dist_id.startswith("PREVIEW-"):
                mapped = _preview_dist_id_map.get(actual_parent_dist_id)
                if mapped is None:
                    raise HTTPException(
                        400,
                        f"挂入点 #{i+1} (parent={h.parent_dist_id} L{h.parent_line_id}) "
                        f"是 PREVIEW 临时 distId, 但本 batch 内找不到对应 step — 请重新预览",
                    )
                actual_parent_dist_id = mapped
            elif not actual_parent_dist_id:
                actual_parent_dist_id = ""

            if actual_parent_dist_id:
                if actual_parent_dist_id in batch_dist_ids:
                    # 父在本 batch 内 — 槽位检查在下面 slot_owners dict 里做
                    pass
                else:
                    # 父在 DB — 校验存在 + 槽位空闲 (DB) + max_lines
                    parent = db.query(Member).filter_by(member_dist_id=actual_parent_dist_id).first()
                    if parent is None:
                        raise HTTPException(
                            400,
                            f"挂入点 #{i+1} (parent={actual_parent_dist_id} L{h.parent_line_id}) "
                            f"在 DB 中找不到父成员",
                        )
                    existing_sibling = (
                        db.query(Member)
                        .filter_by(parent_dist_id=actual_parent_dist_id, slot_line_id=h.parent_line_id)
                        .filter(Member.member_dist_id != actual_parent_dist_id)
                        .first()
                    )
                    if existing_sibling is not None:
                        raise HTTPException(
                            400,
                            f"挂入点 #{i+1} (parent={actual_parent_dist_id or 'ROOT'} L{h.parent_line_id}) "
                            f"在 DB 中槽位已被 {existing_sibling.member_dist_id} 占用 — 请重新预览",
                        )
                    if h.parent_line_id > (parent.max_lines or 5):
                        raise HTTPException(
                            400,
                            f"挂入点 #{i+1} (parent={actual_parent_dist_id}) slot_line_id={h.parent_line_id} "
                            f"超过父 max_lines={parent.max_lines or 5}",
                        )

            # 校验同 batch 内 (parent, slot) 不重复
            if actual_parent_dist_id:
                key = (actual_parent_dist_id, h.parent_line_id)
                if key in slot_owners:
                    raise HTTPException(
                        400,
                        f"挂入点 #{i+1} 跟 #{slot_owners[key]} 同 batch 同一槽位 "
                        f"({actual_parent_dist_id} L{h.parent_line_id}) — 请重新预览",
                    )
                slot_owners[key] = i + 1

            # 更新实际 parent (写 DB 用)
            nm["parent_dist_id"] = actual_parent_dist_id or None  # None = root

        # 5. 写 DB (members + pv_ledger, 单事务)
        member_repo = MemberRepository(db)
        for nm in new_members:
            # ★ PR #39: 不再传 h.parent_dist_id (原值, 含 PREVIEW-N), 改传解析后的实际 distId
            existing = member_repo.get_by_dist_id(nm["member_dist_id"])
            if existing is None:
                member = Member(
                    member_dist_id=nm["member_dist_id"],
                    member_name=nm["name"],
                    parent_dist_id=nm["parent_dist_id"],
                    slot_line_id=nm["parent_line_id"],
                    max_lines=5,
                    current_pv_balance=0,
                    total_commission=0.0,
                    created_period_id=nm["period_id"],
                    role=nm["role"],  # ★ 2026-07-16 PR #41: 角色
                    last_period_id=None,
                )
                db.add(member)
                db.flush()
                member_id = member.id
            else:
                member_id = existing.id
            # 加 PVLedger (status=pending, 等待当期结算)
            ledger = PVLedger(
                member_id=member_id,
                member_dist_id=nm["member_dist_id"],
                period_id=nm["period_id"],
                pv_amount=int(nm["pv"]),
                status="pending",
            )
            db.add(ledger)
        db.commit()

        log.info(
            f"💾 skill_5_3 commit_preview DONE (PR #39 DB-only): 写 {len(new_members)} 位新成员到 DB, "
            f"period_id={req.period_id}"
        )

        return {
            "ok": True,
            "skill_id": skill_id,
            "wrote_to": "DB (members + pv_ledger)",  # ★ PR #39
            "n_members_written": len(new_members),
            "members": new_members,
            "period_id": req.period_id,
            "tree_fingerprint": "",  # ★ PR #39: 不再需要 fingerprint
        }
    except HTTPException:
        raise
    except Exception as e:
        # 兜底: 出错时回滚
        try:
            db.rollback()
        except Exception:
            pass
        log.exception("skill_5_3 commit_preview 失败")
        raise HTTPException(500, f"写盘失败: {e}")


# ============================================================
# Alias 路由 — 兼容旧前端 /skills/skill_a/* 硬编码
# ============================================================
# ★ 2026-07-15: skill_2 / skill_a 全部下线,所有 alias 路由删除。
#   旧前端 (static/index.html) 残留 /skills/skill_a/* 调用会直接 404。
# skill_5_3 走 /skills/skill_5_3/batch/run,纯计算 preview,无会话保存需求。

# ============== 把 skill 预计算结果存到会话里 ==============
# 用户反馈:预计算结果只显示在 chat 里,关闭网页就丢了。
# 改成自动创建一个 session,把"用户输入描述"+"完整 skill 返回 JSON"作为 2 条消息存进去。
# 后续在侧栏点这个会话,前端会把 tool 消息重新渲染成 skill 卡。
#
# ★ 2026-07-11 重写:原 /skills/skill_b/save_preview(对应 skill_3/4/5)已下线,
# ★ 2026-07-13: skill_5_1 / skill_5_2 也下线,新版用 /skills/save_preview + body.skill 字段,
# ★ 2026-07-15: skill_2 也下线,当前活跃 skill 只有 skill_5_3。skill 字段不再硬编码到 URL。

class SkillSavePreviewRequest(BaseModel):
    """把一次预计算结果存到会话(用户消息 + tool 消息)"""
    session_id: Optional[str] = Field(None, description="已有 session_id 就接续,否则新建")
    # ★ 2026-07-15: 当前活跃 skill 只有 skill_5_3 (含 _batch 变体)
    skill: str = Field(..., description="skill_id,例如 'skill_5_3' / 'skill_5_3_batch'")
    input_summary: str = Field(..., description="一句话描述这次预计算的输入 — 用作 user 消息(也会被截断成会话标题)")
    # 完整的 skill 返回 JSON(skill_5_3 含 data 字段;skill_5_3_batch 含 history 字段)
    result: Dict[str, Any] = Field(..., description="完整 skill 返回对象")
    # batch 专用:成员列表 + 顺序(前端再渲染 chatCommitBatch 按钮的 onclick 需要)
    members: Optional[List[Dict[str, Any]]] = Field(None, description="batch 输入成员列表 [{pv, name}, ...]")
    order: Optional[str] = Field(None, description="batch 挂载顺序 pv-desc|pv-asc|input")


@app.post("/skills/save_preview")
def save_skill_preview(
    req: SkillSavePreviewRequest,
    db: DbSession = Depends(get_db),
):
    """把预计算结果存到会话 —— 防止页面关闭后丢失

    写入 2 条消息:
        - role=user   : input_summary(简短文字,作为会话标题来源)
        - role=tool   : JSON 编码的 { skill, data, members?, order? }(前端 re-render 时直接喂给对应 render 函数)
    """
    repo = SessionRepository(db)
    sid, _ = repo.get_or_create(req.session_id)
    user_msg = repo.append_message(sid=sid, role="user", content=req.input_summary)
    tool_payload = {"skill": req.skill, "data": req.result}
    if req.members is not None:
        tool_payload["members"] = req.members
    if req.order is not None:
        tool_payload["order"] = req.order
    tool_msg = repo.append_message(
        sid=sid,
        role="tool",
        content=json.dumps(tool_payload, ensure_ascii=False),
    )
    db.commit()
    log.info(
        f"💾 Skill preview saved: session={sid[:8]}... skill={req.skill} "
        f"user_msg_id={user_msg.id} tool_msg_id={tool_msg.id}"
    )
    return {
        "ok": True,
        "session_id": sid,
        "user_message_id": user_msg.id,
        "tool_message_id": tool_msg.id,
    }


# ============== 把 skill 预计算结果存到会话里 ==============
# 用户反馈:预计算结果只显示在 chat 里,关闭网页就丢了。
# 改成自动创建一个 session,把"用户输入描述"+"完整 skill 返回 JSON"作为 2 条消息存进去。
# 后续在侧栏点这个会话,前端会把 tool 消息重新渲染成 skill 卡。
#
# ★ 2026-07-11: 原 /skills/skill_b/save_preview(对应 skill_3/4/5)已下线,
# ★ 2026-07-13: skill_5_1 / skill_5_2 也下线,skill_5_3 是纯计算 preview(无锁无写盘),
# 无会话持久化需求,本段保留 class 仅为兼容未来其他 skill 复用,目前没有 active endpoint。


# ============== 网体树渲染(整树 HTML) ==============

class TreeHighlightItem(BaseModel):
    """树视图高亮条目:即将挂载的新成员位置"""
    parent_dist_id: str = Field("", description="父节点 distId;空串表示父是 root 或父 distId 不可知")
    parent_line_id: int = Field(..., description="在父节点的第几条线 (1..maxLines)")
    name: str = Field("", description="新成员姓名")
    pv: int = Field(0, description="新成员 PV")
    rank: int = Field(0, description="挂载顺序,从 1 开始;0=无标记")
    # ★ 2026-07-05 v3: 新成员自己的 distId(officev2 真实 或 PREVIEW-N)
    #   用于 _tree_render_children 检测"该替换位置是否还有虚拟 children"
    #   (例:#1 替换后 #3 挂在 #1 下面, member_dist_id=PREVIEW-1 会让后端
    #    在 highlight_map[PREVIEW-1] 里查 children)
    member_dist_id: str = Field("", description="新成员自己的 distId(PREVIEW-N 或 officev2)")


class TreeRenderRequest(BaseModel):
    """渲染整树请求"""
    # ★ 2026-07-03: 加 skill 字段,按 skill_id 选 json 文件
    # ★ 2026-07-15: 默认 skill_5_3 (5 叉按位反转,业务主线;skill_2 已下线)
    skill: str = Field(
        DEFAULT_TREE_SKILL,
        description=f"要渲染哪个 skill 的树文件;可选: {list(TREE_PATHS.keys())}",
    )
    highlights: List[TreeHighlightItem] = Field(default_factory=list, description="高亮条目列表")
    # ★ 关键:committed=true 时,认为 JSON 已经被本次写盘改过(已经是挂载后的最终状态),
    # 这时 highlights 字段被忽略,不再二次叠加
    committed: bool = Field(False, description="本次 session 是否已经 commit;true=不要再标 highlights")
    # ★ 2026-07-16 PR #23: 业务规则「树状图默认显示: 仅激活槽位」
    #   slot_view=active (默认): 隐藏 locked 槽位, 只显示 L1..eff_active
    #   slot_view=all: 显示所有槽位 (含 locked 灰色)
    slot_view: str = Field("active", description='槽位显示模式: "active" (默认,仅激活) 或 "all" (全部)')


def _tree_render_node(
    node: Dict[str, Any],
    highlight_map: Dict[str, Dict[int, Dict[str, Any]]],
    expand_set: Optional[set] = None,
    depth: int = 0,
    preview_rank_map: Optional[Dict[str, int]] = None,
    _n_inc: Optional[int] = None,
    _inherited_max_lines: Optional[int] = None,
    orphan_set: Optional[set] = None,  # ★ 2026-07-16 PR #39: deprecated, 保留兼容旧调用
    _parent_root_line: Optional[int] = None,  # ★ 2026-08-04 PR #7: 父节点在 root 下的 line (1..4), 透传给 L_k+1 子
) -> str:
    """递归渲染树节点 HTML

    highlight_map      : {parent_dist_id: {line_id: highlight_info}}
    expand_set         : 自动展开的 dist_id 集合(highlight 节点 + 所有祖先链上的节点)
                         由 _collect_expand_dist_ids 预算;空集合表示按默认 depth<2 展开
    _n_inc             : 5 叉 L_k 阶段跨父跨列 1-based 序号 N_inc (含 PREVIEW), 0-based depth
                         渲染时由 _tree_render_children 调 _next_n_inc(depth, line, parent_root_line) 算出来传进来
    _inherited_max_lines: 父节点的 max_lines(透传给无 maxLines 字段的 avail/leaf 节点,
                         让 L4 avail 这种"无 children 数据"的节点也能算出正确的 L5 子节点数)
    orphan_set         : ★ 2026-07-16 PR #39: deprecated, tree view 以 DB 为权威后没 orphan 概念
    _parent_root_line  : ★ 2026-08-04 PR #7: 父节点在 root 下的 line (1..4),
                         用于 _next_n_inc 算本节点 N_inc (跨 4 大区 (line, parent_region) 排 1-based N)
    """
    # ★ 2026-07-16 PR #39: tree view 以 DB 为权威后, 没 "json 树有但 DB 没有" 的孤儿 (DB 是单一数据源)
    orphan_set = orphan_set or set()
    is_orphan = False  # PR #39: 永远 False, 保留变量名兼容
    # ★ 2026-07-08: avail 节点的前置 "?" 已无意义(avail_badge 已经标识"avail"),
    #   直接默认空字符串。空槽位的"身份"靠 L1-L5 line badge + avail_badge 表达。
    available = node.get("available") is True  # 提前到 name 计算之前,避免 NameError
    raw_name = node.get("name") or ""
    if available:
        name = ""
    else:
        name = raw_name if raw_name else (node.get("distId") or "?")
    pv_raw = node.get("pv", 0)
    try:
        pv = int(pv_raw) if pv_raw is not None else 0
    except (TypeError, ValueError):
        pv = 0
    dist_id = node.get("distId") or ""
    rank = node.get("rank") or ""
    is_root = depth == 0
    # ★ 2026-07-16 PR #39: orphan 标记废弃 (DB 是权威, 没 orphan 概念)
    orphan_badge = ""
    # ★ 2026-07-16 PR #38: 直推人数 (从 node.directCount 拿, _build_tree_from_db 已注入)
    #   只对 non-avail 节点显示 (avail 节点没 distId 不算)
    _direct_count = int(node.get("directCount", 0)) if available is False else 0
    direct_badge = (
        f'<span class="tv-badge tv-badge-direct" title="直推人数 (DB members.parent_dist_id 实时聚合)">直推 {_direct_count}</span>'
        if (available is False and dist_id and _direct_count > 0) else ""
    )
    # ★ 2026-07-17 PR #51: 本期新增 PV 字段 (从 PVLedger.pv_amount 聚合)
    #   - 替代之前的 `pv` (剩余 PV = current_pv_balance)
    #   - avail 节点不显示 (无意义)
    #   - 0 不显示 (避免冗余) / >0 用绿色 (CSS data-pv-positive)
    #   - ★ 2026-07-17 PR #54: 加 0 隐藏 (跟剩余 PV 徽章保持一致, 都是 0 不显示)
    #   - ★ 2026-07-17 PR #54 v2: 只在 current_period.status=open 时显示
    #     用户反馈: "结算后张a 本期500PV 这个位置应该变成 剩余200PV (500-300)"
    #     业务规则: 本期 (open) vs 剩余 (settled 或 carry) 同一位置互斥显示, 避免重复
    _period_pv = int(node.get("periodPv", 0) or 0)
    _cur_period_status = node.get("currentPeriodStatus", "open") or "open"
    period_pv_badge = ""
    if available is False and dist_id and _period_pv > 0 and _cur_period_status == "open":
        period_pv_badge = (
            f'<span class="tv-badge tv-badge-pv" data-pv-positive="1" '
            f'title="本期新增 PV (从 PVLedger.pv_amount 聚合, period_id=current)">'
            f'本期 {_period_pv} PV</span>'
        )
    # ★ 2026-07-17 PR #54: 剩余 PV 徽章 (跨期 carry, 来自 Member.current_pv_balance)
    #   - 跟本期新增是**两个独立字段**: 本期新注入 vs 跨期 carry 余额
    #   - 用户 (2026-07-17) 反馈: "结算后张a 500 PV 应该变成剩余 200 PV (500-300)"
    #   - 实际上**两个都该显示** (语义不同): 本期 500 = 新增, 剩余 200 = 跨期 carry
    #   - avail 节点不显示; =0 不显示 (避免冗余, 跟本期一致)
    _carry_pv = int(node.get("pv", 0) or 0)  # node.pv = current_pv_balance
    carry_pv_badge = ""
    if available is False and dist_id and _carry_pv > 0:
        carry_pv_badge = (
            f'<span class="tv-badge tv-badge-carry" '
            f'title="剩余 PV (跨期 carry, 来自 Member.current_pv_balance, 结算时 update)">'
            f'剩余 {_carry_pv} PV</span>'
        )
    # ★ PR #51: 累计 commission 字段 (DB Member.total_commission, 历史所有期总和)
    _total_comm = float(node.get("totalCommission", 0.0) or 0.0)
    total_comm_badge = ""
    if available is False and dist_id and _total_comm > 0:
        total_comm_badge = (
            f'<span class="tv-badge tv-badge-comm-total" '
            f'title="累计 commission (基本 + 7 代对等, 历史所有期总和)">'
            f'累计 ${_total_comm:.2f}</span>'
        )
    # ★ 2026-07-16 PR #41/42/44: 角色徽章
    #   - PR #41: 加 7 角色 enum key, 短名居中在 name 下方
    #   - PR #42: DB 存全名 label, 居中在 name 下方 (父级 tv-role-row flex 居中)
    #   - PR #44: 移到 line 1 (跟 name 同行), 不用 tv-role-row 容器, 视觉跟主体一体
    #   - avail 节点不显示 (没 distId, 没意义)
    #   - 颜色按 MEMBER_ROLES 配置, 一眼能区分
    role_badge = ""
    if available is False and dist_id:
        _role_label = _normalize_role(node.get("role"))
        _role_info = MEMBER_ROLES[_role_label]
        role_badge = (
            f'<span class="tv-badge tv-badge-role" '
            f'role-label="{_html(_role_label)}" '
            f'style="background:{_role_info["bg"]}; color:{_role_info["fg"]};" '
            f'title="{_html(_role_label)}">'
            f'{_html(_role_label)}</span>'
        )
    # ★ 2026-08-06 PR #75: 业务档位 badge (4 档位独立列, 跟 role badge 并列)
    #   - 业务定位: 4 档位 (激活/商务/精英/至尊) 跟 PR #71 teamBonus 4 档对应
    #   - 跟 role badge 并列显示 (2 套独立), 不替换
    #   - avail 节点不显示
    business_level_badge = ""
    if available is False and dist_id:
        _bl_label = _normalize_business_level(node.get("business_level"))
        _bl_info = MEMBER_BUSINESS_LEVELS[_bl_label]
        business_level_badge = (
            f'<span class="tv-badge tv-badge-business-level" '
            f'business-level-label="{_html(_bl_label)}" '
            f'style="background:{_bl_info["bg"]}; color:{_bl_info["fg"]};" '
            f'title="业务档位: {_html(_bl_label)} (tier_pv={_bl_info["tier_pv"]})">'
            f'{_html(_bl_label)}</span>'
        )

    # ★ 2026-07-12 v3: 「点位编号」徽章 — 用户规则:父下的 1-based 位置,纯数字 1..5
    #   业务术语化的「奇左偶右」配色 (2026-07-10 新色卡 #5AA4AE 主):
    #     1/2(原 L1/L2): 浅青底 #D6ECF0 + 深字     — 业务双轨·一/二轨(浅)
    #     3/4/5(原 L3/L4/L5): 主色 teal #5AA4AE + 白字 — 业务双轨延伸·三/四/五轨(深,强调)
    #   每个非根节点都标注自己在父 children 里的 1-based 位置(parentLineId),
    #   树视图一眼能看出每个节点是父的「第几个点位」,avail 占位也有明确身份。
    #   2026-07-12 改为去掉 "L" 前缀: 跟用户口径一致("张三是 1" 而非"张三是 L1"),
    #   也避免 "L" 被误解为 level/layer。
    line_badge_html = ""
    if not is_root:
        _plid_raw = node.get("parentLineId")
        try:
            _plid = int(_plid_raw) if _plid_raw is not None else None
        except (TypeError, ValueError):
            _plid = None
        if _plid is not None:
            if _plid == 1:
                _lb_text, _lb_bg, _lb_fg = "1", "#D6ECF0", "#1F2937"
            elif _plid == 2:
                _lb_text, _lb_bg, _lb_fg = "2", "#D6ECF0", "#1F2937"
            elif _plid == 3:
                _lb_text, _lb_bg, _lb_fg = "3", "#5AA4AE", "#FFFFFF"
            elif _plid == 4:
                _lb_text, _lb_bg, _lb_fg = "4", "#5AA4AE", "#FFFFFF"
            elif _plid == 5:
                _lb_text, _lb_bg, _lb_fg = "5", "#5AA4AE", "#FFFFFF"
            else:
                _lb_text, _lb_bg, _lb_fg = str(_plid), "#D6ECF0", "#1F2937"
            line_badge_html = (
                f'<span class="tv-badge tv-badge-line" '
                f'style="background:{_lb_bg}; color:{_lb_fg};">'
                f'{_html(_lb_text)}</span>'
            )

    # 节点信息行
    name_class = "tv-name" + (" root" if is_root else "")
    avail_badge = '<span class="tv-badge tv-badge-avail">avail</span>' if available else ""
    rank_badge = f'<span class="tv-badge tv-badge-rank">{_html(rank)}</span>' if rank and not available else ""

    # ★ 2026-07-13 v3: 5 叉 L_k 阶段 1-based 序号 N_inc badge
    #   跟 line badge 区分: line badge 是"在父下的位置 (1-based col)"
    #   x_coord badge 是"5 叉 L_k 阶段跨父跨列 1-based 序号"
    #   例如: 张三 (PR #71 v3 fill step 1) = L1·1 (k=1, N=1, 4 大区 A)
    #         李三 (PR #71 v3 fill step 2) = L1·2 (k=1, N=2, 4 大区 C)
    #         王五 (PR #71 v3 fill step 3) = L1·3 (k=1, N=3, 4 大区 B)
    #         赵六 (PR #71 v3 fill step 4) = L1·4 (k=1, N=4, 4 大区 D)
    #         张三下面第 1 个 L2 子 (PR #71 v3 fill step 5) = L2·1
    #   ★ 2026-08-04 PR #4 (PR #71 v3 业务规则): X = N 1-based 编号 (旧 X = 2^k + bit_reverse 翻案)
    #   翻案原因: 5 叉树 5^N 节点, 旧公式 N > 2^k 时 X=None, 第 3/4 个 4 大区 L1 不显示 X 标
    #   新业务规则: 1-based N 编号, 跟 PR #71 v3 fill step 顺序严格一致, 12 个点位 pattern 全部可标
    x_coord_badge = ""
    if _n_inc is not None and _n_inc > 0:
        _x = _x_coord_from_n(_n_inc, depth)
        _lv = depth  # 0-based L 标签 (L0=root, L1=depth 1, ...) 跟 TreeGenerate 一致
        if _x is not None:
            # 颜色按 0-based level: L0=蓝, L1=青, L2=黄, L3=紫, L4=粉
            _xb_color_map = {
                0: ("#4f9dff", "#fff"),   # L0: 蓝
                1: ("#2dd4bf", "#0f1115"),  # L1: 青
                2: ("#f59e0b", "#0f1115"),  # L2: 黄
                3: ("#c084fc", "#fff"),   # L3: 紫
                4: ("#ec4899", "#fff"),   # L4: 粉
            }
            _xb_bg, _xb_fg = _xb_color_map.get(_lv, ("#D6ECF0", "#1F2937"))
            # ★ 2026-07-13 v4 fix: avail 节点也显示 X 坐标(原本只 real 节点显示)
            #   avail 节点通常没有 name/distId,所以标题/内容是空的,但 X 坐标徽章还是显示
            #   例: 高学武 2 个 avail 应显示 L4-16 / L4-24(per bit_reverse 公式 + 含 avail 序号累加)
            x_coord_badge = (
                f'<span class="tv-badge tv-badge-xcoord" '
                f' style="background:{_xb_bg}; color:{_xb_fg};" '
                f' title="5 叉 L_k 阶段 1-based 序号 N={_n_inc} → 2 叉 bit_reverse X 坐标 (TreeGenerate 风格)">'
                f'L{_lv}·{_x}</span>'
            )

    # 默认展开: 根 + 前 2 层;若 highlight 在子树内则强制展开此节点(用户反馈:树深很难找新挂位置)
    in_expand_chain = bool(dist_id and expand_set and dist_id in expand_set)
    open_attr = " open" if depth < 2 or in_expand_chain else ""

    children = node.get("children") or []
    # ★ 2026-07-13 v4: max_lines 优先级 node.maxLines > _inherited_max_lines > 5
    #   让 avail 这种无 maxLines 字段的节点也能继承父的 max_lines(2-叉=2, 5-叉=5)
    #   这样 L4 avail 加 L5 子节点时,L5 子节点数跟树型一致(2-叉 2 个 / 5-叉 5 个)
    try:
        _node_max_lines = int(node.get("maxLines") or 0)
    except (TypeError, ValueError):
        _node_max_lines = 0
    if _node_max_lines > 0:
        max_lines = _node_max_lines
    elif _inherited_max_lines and _inherited_max_lines > 0:
        max_lines = _inherited_max_lines
    else:
        max_lines = 5

    my_highlights = highlight_map.get(dist_id, {}) if dist_id else {}
    has_highlight = bool(my_highlights)
    has_anything = bool(children) or has_highlight

    # ★ 2026-07-13 v4: L4 avail (depth=4) 强制渲染为 details,带 2/5 个 L5 avail 虚拟子节点
    #   用户反馈 (2026-07-13): "第五层也需要从高学武下面增加对应的avail节点后,设置序号,依次排列过去"
    #   - depth=4 表示 L4 阶段的 avail 节点(高学武的 L4-16/L4-24 等)
    #   - 当前 available=True 且无 children, 会走 else 分支当 leaf 渲染
    #   - 这里拦截: 强制按 details 展开,给 max_lines 个 L5 avail 虚拟子节点(2-叉 2 个 / 5-叉 5 个)
    #   - 这些 L5 avail 会被 _tree_render_children 渲染, 走 _next_n_inc(depth+1) 自然参与全局 N_inc 计数
    #   - L5+ avail 不再递归(L5 avail 仍按 leaf 渲染), 避免树爆炸
    if available and not has_anything and not is_root and depth == 4:
        _virtual_max_lines = max_lines  # 2 for 2-叉, 5 for 5-叉
        # ★ 2026-07-14 v6: 虚拟子 avail 标 isLocked (L4 avail 默认 effective=2, L5 全部 locked)
        #   L4 avail 自身被父节点 effective 锁控 (上面 ch["isLocked"] 注入)
        #   L4 avail 自己的 effective = 2, 它的 5 个虚拟子 (L5) 全部 locked
        _virtual_children = [
            {"available": True, "parentLineId": _i, "maxLines": _virtual_max_lines,
             "isLocked": _i > 4}  # root eff=4 (PR 拍板), avail 渲染 line 1-4 unlocked, line 5 locked
            for _i in range(1, _virtual_max_lines + 1)
        ]
        # ★ 2026-07-14 v6: L4 avail 也带 locked 状态 (父 L4 active=2 时, L4 节点本身 unlocked,
        #   但 L4 的子节点(L5 虚拟)是 locked)
        _is_locked_self = bool(node.get("isLocked"))
        _locked_class = " tv-node-locked" if _is_locked_self else ""
        _locked_attr = ' data-locked="1"' if _is_locked_self else ""
        # ★ 2026-07-16 PR #44: L4 avail 走 2-行 grid 卡片结构 (跟其他节点统一)
        return (
            f'<details class="tv-node tv-avail{_locked_class}"{_locked_attr} open>'
            f'<summary class="tv-card">'
            f'<span class="tv-caret"></span>'
            f'<div class="tv-card-line1">'
            f'<span class="{name_class}"></span>'
            f'{avail_badge}{rank_badge}{line_badge_html}{x_coord_badge}'
            f'</div>'
            f'<div class="tv-card-line2">'
            # ★ PR #51: avail 节点不显示 PV (无意义, 改空格)
            f'<span class="tv-distid">{_html(dist_id)}</span>'
            f'</div>'
            f'</summary>'
            + _tree_render_children(node, _virtual_children, _virtual_max_lines, my_highlights, highlight_map, depth, expand_set, preview_rank_map, orphan_set, parent_root_line=_parent_root_line)
            + '</details>'
        )

    # ★ 2026-07-21 PR #58: 改用 commissionPreview (ownBasic + pairBonus 7 层对等) 替换旧的 own basic 计算
    #   旧 (PR #11/14/22): 用 children[].pv (剩余 PV, 跨期 carry, 本期未 settle 时=0) → commission=0 不显示
    #   新 (PR #58): 用 _build_tree_from_db 注入的 commissionPreview (ownBasic + pairBonus) 实时显示
    #     - ownBasic = MIN(MAX 子区 periodPv, SUM 其余 4) × 15%
    #     - pairBonus = 7 层对等累加 (子孙节点的 ownBasic × [0.15, 0.10, 0.05×5])
    #     - 跟 settle_period._settle_node + _apply_pairing_bonus 规则完全一致
    #   业务: z1 本期 500 + z2 本期 300 → 王常军 commissionPreview = ownBasic ¥45 + pairBonus ¥0 = ¥45
    #   用户 (2026-07-21) 反馈: "本期金额出现后, 应该同时模拟算出基本佣金, 对等佣金等值, 显示在父节点上"
    # ★ PR #69: commissionPreview 现在 = ownBasic + pairBonus + teamBonus
    #   - 基本佣金 = ownBasic (5 子区 P/L 配对 × 15%, own 不参与)
    #   - 对等奖金 = pairBonus (7 层对等累加, 子孙 ownBasic 分给祖先)
    #   - 团队培育奖金 = teamBonus (1区+2区 新PV × 30%, 节点自己拿不分给祖先)
    # ★ 2026-08-06 PR #73: commission 数字直接当美元理解 (commission rate 15% 跟储蓄比例 15% 同源)
    #   - 用户原话: "在计算基本佣金的时候, 都会用乘以 15%, 结果就可以直接理解为美金了. 不存在汇率计算的问题"
    #   - 之前示例 ¥2000.10 = $2000.10, 全局 ¥ → $ 符号
    _commission_preview = float(node.get("commissionPreview", 0.0) or 0.0)
    _own_basic_preview = float(node.get("ownBasic", 0.0) or 0.0)
    _team_bonus_preview = float(node.get("teamBonus", 0.0) or 0.0)
    _savings_preview = float(node.get("savingsPreview", 0.0) or 0.0)  # ★ 2026-08-06 PR #73
    # 对等奖金 = 总 - 基本 - 团队培育 (因为 commissionPreview = own + pair + team)
    _pair_bonus_preview = _commission_preview - _own_basic_preview - _team_bonus_preview
    # 显示规则 (PR #58):
    #   1) 有真实子节点 或 是 root, 且非 avail
    #   2) commissionPreview > 0
    #   3) currentPeriodStatus == "open" (settled 期已落账, 不显示预览)
    #   ★ 0 不显示 (跟"本期 PV" / "剩余 PV" 风格一致)
    _show_commission_preview = (
        (bool(children) or is_root)
        and not available
        and _commission_preview > 0
        and _cur_period_status == "open"
    )
    # ★ 2026-08-06 PR #73: 储蓄奖金显示规则
    #   - 触发: ownBasic ≥ $250
    #   - savings > 0 才显示
    #   - 跟 commission preview 一样, only period=open
    _show_savings_preview = (
        _savings_preview > 0
        and _cur_period_status == "open"
        and (bool(children) or is_root)
        and not available
    )
    _commission_html = ""
    if _show_commission_preview:
        # ★ PR #69 → PR #71: tooltip 文案更新 — 团队培育奖金按 4 档精确匹配
        #   旧 (PR #69): 1区/2区新PV 全部按 30% 算 (用户 2026-07-27 反馈)
        #   新 (PR #71, 2026-08-06): 按"每个新成员 own periodPv"严格精确匹配 4 档
        #     - 200 PV → 15% / 500 PV → 20% / 1000 PV → 25% / 1500 PV → 30%
        #     - 其它 PV (300/700/1200/2000/...) → 0% (严格精确, 不套档)
        #   tooltip 三段文案: 基本佣金 + 对等奖金 + 团队培育奖金 = 总额
        # ★ PR #73: ¥ → $ 符号
        _commission_html = (
            f'<span class="tv-commission-preview" '
            f'title="本期可拿 — 基本佣金: ${_own_basic_preview:.2f} '
            f'+ 对等奖金: ${_pair_bonus_preview:.2f} '
            f'+ 团队培育奖金: ${_team_bonus_preview:.2f} '
            f'= ${_commission_preview:.2f}">'
            f'本期可拿 ${_commission_preview:.2f}</span>'
        )
    # ★ 2026-08-06 PR #73: 储蓄奖金徽章 (绿色, 跟 commission preview 紫色区分)
    #   - 业务: ownBasic ≥ $250 时, savings = min(ownBasic × 15%, $500)
    #   - 美元, 跟 commission 数字同源
    #   - 节点自己拿, 不分给祖先
    _savings_html = ""
    if _show_savings_preview:
        _savings_html = (
            f'<span class="tv-savings-preview" '
            f'title="储蓄奖金 — 基本佣金 ≥ $${SAVINGS_BONUS_USD_THRESHOLD:.0f} 触发, '
            f'存入比例: ownBasic × {SAVINGS_BONUS_USD_RATE*100:.0f}%, '
            f'上限 ${SAVINGS_BONUS_USD_CAP:.0f}/周">'
            f'💰 储蓄 +${_savings_preview:.2f}</span>'
        )

    # 容器: 用 <details> 折叠
    if has_anything and not is_root:
        # 子节点 - 用 details 包裹
        # ★ 2026-07-16 PR #44: 名片风格 2-行 grid
        #   line1 (身份): name + role badge (跟主体一起, 不再下方居中) + line/xcoord
        #   line2 (meta): distId + 直推 + PV + commission
        #   hover: 白底 + teal 边框 + 阴影 + 上浮 2px + role 缩放 1.05 (200ms ease-out)
        return (
            f'<details class="tv-node{(" tv-avail" if available else "")}"{open_attr}>'
            f'<summary class="tv-card">'
            f'<span class="tv-caret"></span>'
            f'<div class="tv-card-line1">'
            f'<span class="{name_class}">{_html(name)}</span>'
            f'{role_badge}{business_level_badge}'  # ★ PR #44 + PR #75: role + business_level 同行
            f'{avail_badge}{orphan_badge}{rank_badge}{line_badge_html}{x_coord_badge}'
            f'</div>'
            f'<div class="tv-card-line2">'
            f'<span class="tv-distid">{_html(dist_id)}</span>'
            f'{direct_badge}'
            # ★ PR #51: PV 改成 period_pv (本期新增 from PVLedger)
            f'{period_pv_badge}'
            # ★ PR #54: 剩余 PV 徽章 (跨期 carry, 结算后更新)
            f'{carry_pv_badge}'
            f'{_commission_html}'
            # ★ 2026-08-06 PR #73: 储蓄奖金徽章 (绿色, 紧跟 commission 紫色)
            f'{_savings_html}'
            f'{total_comm_badge}'
            f'</div>'
            f'</summary>'
            + _tree_render_children(node, children, max_lines, my_highlights, highlight_map, depth, expand_set, preview_rank_map, orphan_set, parent_root_line=_parent_root_line)
            + '</details>'
        )
    elif is_root:
        # 根节点 - 永远展开,金黄渐变背景 (跟普通节点区分)
        # ★ 2026-07-16 PR #44: 2-行 grid (line1: 身份 / line2: meta)
        return (
            f'<div class="tv-node tv-root">'
            f'<div class="tv-card tv-card-root">'
            f'<div class="tv-card-line1">'
            f'<span class="tv-crown">★</span>'
            f'<span class="{name_class}">{_html(name)}</span>'
            f'{role_badge}{business_level_badge}'  # ★ PR #44 + PR #75
            f'{rank_badge}{orphan_badge}'
            f'</div>'
            f'<div class="tv-card-line2">'
            f'<span class="tv-distid">{_html(dist_id)}</span>'
            f'{direct_badge}'
            # ★ PR #51: 改用 period_pv (本期新增 from PVLedger)
            f'{period_pv_badge}'
            # ★ PR #54: 剩余 PV 徽章 (跨期 carry, 结算后更新)
            f'{carry_pv_badge}'
            f'{_commission_html}'
            # ★ 2026-08-06 PR #73: 储蓄奖金徽章
            f'{_savings_html}'
            f'{total_comm_badge}'
            f'</div>'
            f'</div>'
            + _tree_render_children(node, children, max_lines, my_highlights, highlight_map, depth, expand_set, preview_rank_map, orphan_set, parent_root_line=_parent_root_line)
            + '</div>'
        )
    else:
        # 叶子节点(无 children,无 highlight) — commission 无意义,不显示
        # ★ 2026-07-16 PR #44: 2-行 grid
        return (
            f'<div class="tv-node tv-leaf{(" tv-avail" if available else "")}">'
            f'<div class="tv-card">'
            f'<div class="tv-card-line1">'
            f'<span class="{name_class}">{_html(name)}</span>'
            f'{role_badge}{business_level_badge}'  # ★ PR #44 + PR #75
            f'{avail_badge}{orphan_badge}{rank_badge}{line_badge_html}{x_coord_badge}'
            f'</div>'
            f'<div class="tv-card-line2">'
            f'<span class="tv-distid">{_html(dist_id)}</span>'
            f'{direct_badge}'
            # ★ PR #51: 改用 period_pv (本期新增 from PVLedger)
            f'{period_pv_badge}'
            # ★ PR #54: 剩余 PV 徽章 (跨期 carry, 结算后更新)
            f'{carry_pv_badge}'
            f'{total_comm_badge}'
            f'</div>'
            f'</div>'
            + '</div>'
        )


def _tree_render_children(
    parent: Dict[str, Any],
    children: List[Dict[str, Any]],
    max_lines: int,
    my_highlights: Dict[int, Dict[str, Any]],
    full_highlight_map: Dict[str, Dict[int, Dict[str, Any]]],
    depth: int,
    expand_set: Optional[set] = None,
    preview_rank_map: Optional[Dict[str, int]] = None,
    orphan_set: Optional[set] = None,
    parent_root_line: Optional[int] = None,  # ★ 2026-08-04 PR #7: parent 在 root 下的 line (1..4), 透传给子
) -> str:
    """渲染父节点的子槽位列表 (固定 max_lines 个,缺的补空位/高亮)

    重要:jsTree 的 children 列表顺序 ≠ parentLineId 顺序(实测: 林晓霞的 children 是 [L2, L1, L3, L4, L5])
    所以不能用 list index,必须按 parentLineId 字段做索引

    ★ 2026-08-04 PR #7: parent_root_line 透传规则
      - depth=0 (root 调 _tree_render_children): parent_root_line=None, L1 父的 root_line = child.line (i 循环变量)
      - depth>=1: 透传父的 root_line 给 L_k+1 子 (业务上 L1 父的 root_line 永远是 1..4, 子继承)
    """
    # ★ 关键修复: 用 parentLineId 做 key 建索引(容忍字符串/数字)
    by_line: Dict[int, Dict[str, Any]] = {}
    for c in children:
        lid = c.get("parentLineId")
        try:
            by_line[int(lid)] = c
        except (TypeError, ValueError):
            pass

    # ★ 2026-07-15 PR #14: 回归 PR #4 自动提升
    #   业务规则 (用户拍板 2026-07-15):
    #     - 默认 eff = 2 (L1+L2 激活, line 3+ 默认锁)
    #     - 1-2 区满员 (children line 1, 2 都填了真实成员) → eff 升到 4 (L3+L4 同时开)
    #     - 1-4 区都满员 → eff 升到 5 (L5 单独开)
    #   跟 skills/skill_5_lib.py Node5.effective_max_active_lines() 逻辑一致
    #   但这里接收的是 JSON dict (渲染函数从 json 读), 不是 Node5
    _eff_active = _compute_effective_active_from_json(parent, max_lines=max_lines, max_active_lines=int(parent.get("maxActiveLines", 2) or 2))

    items = []
    # ★ 2026-08-04 PR #5 (PR #71 v3): 按 HORIZONTAL_ORDER [1, 3, 2, 4, 5] 顺序遍历 children
    #   旧 (PR #18): for i in range(1, max_lines + 1) — 按 line 顺序 (1, 2, 3, 4, 5) 排
    #   问题: 4 大区 L1 父 N_inc 按 line 顺序 = A=L1·1, B=L1·2, C=L1·3, D=L1·4
    #         但 PR #71 v3 fill step 顺序 = A, C, B, D → A=L1·1, C=L1·2, B=L1·3, D=L1·4
    #   业务: 标号跟 fill step 顺序严格一致, 12 个点位 pattern 全部按 (1, 3, 2, 4) 排
    _line_iter = [l for l in _LINE_FILL_ORDER_PR71 if l <= max_lines]
    for i in _line_iter:
        ch = by_line.get(i)
        hl = my_highlights.get(i)

        if ch is not None and hl:
            # 有真实子节点 + 本次将挂载
            # avail 升级: 显示该 avail 节点 + 标注"将被替换"
            # ★ 2026-08-04 PR #7: 透传 child_root_line 给子
            _child_root_line = i if depth == 0 else parent_root_line
            ch_html = _tree_render_node(ch, full_highlight_map, expand_set, depth + 1, preview_rank_map, _inherited_max_lines=max_lines, orphan_set=orphan_set, _parent_root_line=_child_root_line)
            rank_tag = f'<span class="tv-rank-num">#{hl.get("rank", "?")}</span>' if hl.get("rank") else ""
            # ★ 2026-07-05 v3: 该替换位置挂载的新成员(PREVIEW-{rank})还可能有 children
            #   比如 #1 替换后, #3 会挂在 #1 下面 — 这些 children 在 highlight_map[member_dist_id] 里
            #   在替换标记下方追加一段 "预览子树" 显示这些 children
            member_dist_id = hl.get("member_dist_id") or ""
            # ★ 2026-07-13 v3: PREVIEW 节点 (丁 1/2/3) 用 5 叉 L_(k+1) 阶段"含 PREVIEW 1-based 序号" + TreeGenerate 2 叉公式
            #   PREVIEW 节点不在 raw dict, _compute_bitrev_x_coord 算不到, 这里用渲染顺序计数器:
            #     N_inc = _next_n_inc(depth + 1)  (跨父跨列, 跳过 avail, 含 PREVIEW 的 1-based 序号)
            #     X = 2^(depth+1) + bit_reverse(N_inc-1, depth+1)
            preview_x_coord_badge = ""
            try:
                # ★ 2026-07-13 v3 fix: PREVIEW 节点替换 ch (avail) 节点, depth 跟 ch 一样
                #   在 _tree_render_children 中循环到 ch (avail) 父节点时, depth 是 ch 父 depth
                #   PREVIEW 节点 depth = ch 父 depth + 1 = depth + 1 (跟 ch 一样, PREVIEW 替换 ch)
                _pv_depth_0b = depth + 1  # PREVIEW 节点 depth = ch 父 depth + 1
                # ★ 2026-08-04 PR #9: PREVIEW 节点 N 用 (line, 父的 line 槽位) 算
                #   parent_line_id 业务上 = parent.parentLineId (L1 父 1, 2, 3, 4 / L2+ 父 1, 2)
                _pv_n_inc = _next_n_inc(_pv_depth_0b, line=i, parent_line_id=int(parent.get("l1RootLine") or 0), l2_line=int(parent.get("parentLineId") or 0) if _pv_depth_0b >= 3 else None)
                _pv_x = _x_coord_from_n(_pv_n_inc, _pv_depth_0b)
                if _pv_x is not None:
                    _pv_label = f"L{_pv_depth_0b}"
                    _pxb_color_map = {
                        0: ("#4f9dff", "#fff"),
                        1: ("#2dd4bf", "#0f1115"),
                        2: ("#f59e0b", "#0f1115"),
                        3: ("#c084fc", "#fff"),
                        4: ("#ec4899", "#fff"),
                    }
                    _pxb_bg, _pxb_fg = _pxb_color_map.get(_pv_depth_0b, ("#D6ECF0", "#1F2937"))
                    preview_x_coord_badge = (
                        f'<span class="tv-badge tv-badge-xcoord" '
                        f'style="background:{_pxb_bg}; color:{_pxb_fg}; margin-left:4px;" '
                        f' title="5 叉 L_(k+1) 阶段 含 PREVIEW 1-based 序号 N={_pv_n_inc} → 2 叉 bit_reverse X 坐标 (TreeGenerate 风格)">'
                        f'{_pv_label}·{_pv_x}</span>'
                    )
            except Exception:
                pass
            preview_children_html = ""
            if member_dist_id and member_dist_id in full_highlight_map:
                # 构造一个虚拟 parent dict 用于递归 _tree_render_children
                # 复用 ch 的字段(因为 avail 节点本身是空位,children=[]),但 max_lines 用 ch.maxLines
                try:
                    virtual_max_lines = int(ch.get("maxLines") or 5)
                except (TypeError, ValueError):
                    virtual_max_lines = 5
                if virtual_max_lines <= 0:
                    virtual_max_lines = 5
                virtual_parent = dict(ch)  # 浅拷贝 — 包含 maxLines 等
                preview_children_html = _tree_render_children(
                    virtual_parent, ch.get("children") or [],
                    virtual_max_lines,
                    full_highlight_map[member_dist_id],
                    full_highlight_map,
                    depth + 1,
                    expand_set,
                    preview_rank_map,
                    orphan_set,
                )
            items.append(
                f'<li class="tv-slot tv-slot-hl tv-slot-replace">'
                f'{ch_html}'
                f'<div class="tv-slot-mark tv-slot-mark-replace">'
                f'▲ {rank_tag}将替换为 <b>{_html(hl.get("name") or "新成员")}</b>'
                f' <span class="tv-pv-inline">{hl.get("pv", 0)} PV</span>'
                f'{preview_x_coord_badge}'
                f'<span class="tv-preview-tag" style="background:#D6ECF0;color:#1F2937;font-size:9px;padding:0 4px;border-radius:3px;margin-left:4px;font-family:ui-monospace,monospace;border:1px solid rgba(90,164,174,0.35);">{_html(member_dist_id) or "(无distId)"}</span>'
                f'</div>'
                f'{preview_children_html}'
                f'</li>'
            )
        elif ch is not None and not ch.get("available"):
            # 纯子节点 (非 avail, 真实成员)
            # ★ 2026-07-13 v3: 真实子节点算 N_inc 传给 _tree_render_node
            # ★ 2026-07-13 v4 fix: avail 也参与 N_inc 累加(原版"跳过 avail"会让 avail 槽位的 X 坐标
            #   跟 1st 真实子的 X 坐标冲突) — 例: 高学武 2 个 avail + 刘悦 2 个真实子的 4 子区
            #   按"父优先 + 列优先" + 含 avail 序号, 应该是 16/24/20/28(per bit_reverse 公式)
            # ★ 2026-08-04 PR #9: 真实子 N 用 (line, 父的 line 槽位) 算
            #   parent_line_id 业务上 = parent.parentLineId (L1 父 1, 2, 3, 4 / L2+ 父 1, 2)
            _ch_n_inc = _next_n_inc(depth + 1, line=i, parent_line_id=int(parent.get("l1RootLine") or 0), l2_line=int(parent.get("parentLineId") or 0) if (depth + 1) >= 3 else None)
            # ★ 2026-08-04 PR #7: 透传 child_root_line 给子 (L1 父 child_root_line=i, 其他继承, 业务上 L3+ 还需要)
            _child_root_line = i if depth == 0 else parent_root_line
            ch_html = _tree_render_node(ch, full_highlight_map, expand_set, depth + 1, preview_rank_map, _n_inc=_ch_n_inc, _inherited_max_lines=max_lines, orphan_set=orphan_set, _parent_root_line=_child_root_line)
            items.append(f'<li class="tv-slot">{ch_html}</li>')
        elif ch is not None and ch.get("available"):
            # 纯 avail 节点 (无 PREVIEW 替换) — 也要算 N_inc, 让 avail 空位有正确的 X 坐标
            #   (例: 高学武 col 0/1 的 2 个 avail 应该显示 L4-16/L4-24, 而不是空着)
            # ★ 2026-07-14 v6: 临时给 ch dict 加 isLocked 字段, 让 _tree_render_node 内部读得到
            #   (json 树没这字段, 渲染时实时算)
            _is_locked = i > _eff_active
            # ★ 2026-07-14 v7: locked 槽位不参与 N_inc 累加, 不显示位反转 X 坐标
            #   业务反馈: "张五下面暂时只开 2 个区, 3/4/5 区先不要按位反转规律排列, 等开了再排"
            #   unlocked 时: 走原版逻辑(累加 N_inc + 显示 X 坐标)
            #   locked 时: N_inc=None, _tree_render_node 不渲染 x_coord_badge
            # ★ 2026-08-04 PR #9: avail 节点 N 用 (line, 父的 line 槽位) 算
            #   parent_line_id 业务上 = parent.parentLineId
            _ch_n_inc = _next_n_inc(depth + 1, line=i, parent_line_id=int(parent.get("l1RootLine") or 0), l2_line=int(parent.get("parentLineId") or 0) if (depth + 1) >= 3 else None, is_locked=_is_locked)
            ch["isLocked"] = _is_locked
            _child_root_line = i if depth == 0 else parent_root_line
            ch_html = _tree_render_node(ch, full_highlight_map, expand_set, depth + 1, preview_rank_map, _n_inc=_ch_n_inc, _inherited_max_lines=max_lines, orphan_set=orphan_set, _parent_root_line=_child_root_line)
            # ★ 2026-07-16 PR #23: 业务规则「树状图默认显示: 仅激活槽位」
            #   树状图只显示 L1..eff_active 激活的 line, locked 槽位 (line > eff_active) 跳过不渲染
            #   工具栏可切到 "全部槽位" 模式 (slotView=active vs all) — 默认 active
            if _is_locked and not _SLOT_VIEW_SHOW_LOCKED:
                continue
            _slot_class = "tv-slot tv-slot-locked" if _is_locked else "tv-slot"
            _locked_attr = ' data-locked="1"' if _is_locked else ""
            items.append(f'<li class="{_slot_class}"{_locked_attr}>{ch_html}</li>')
        elif hl:
            # 空槽位 + 本次将挂载(append)
            rank_tag = f'<span class="tv-rank-num">#{hl.get("rank", "?")}</span>' if hl.get("rank") else ""
            # ★ 2026-07-13 v3: tv-slot-new 也要算 x_coord (PREVIEW 节点是空槽位挂入的新成员)
            #   跨父跨列, 跳过 avail, 含 PREVIEW 1-based 序号 N_inc
            #   X = 2^(depth+1) + bit_reverse(N_inc-1, depth+1)
            tv_slot_new_badge = ""
            try:
                _tv_depth_0b = depth + 1
                # ★ 2026-08-04 PR #9: 空槽位 N 用 (line, 父的 line 槽位) 算
                _tv_n_inc = _next_n_inc(_tv_depth_0b, line=i, parent_line_id=int(parent.get("l1RootLine") or 0), l2_line=int(parent.get("parentLineId") or 0) if _tv_depth_0b >= 3 else None)
                _tv_x = _x_coord_from_n(_tv_n_inc, _tv_depth_0b)
                if _tv_x is not None:
                    _tv_label = f"L{_tv_depth_0b}"
                    _tv_color_map = {
                        0: ("#4f9dff", "#fff"),
                        1: ("#2dd4bf", "#0f1115"),
                        2: ("#f59e0b", "#0f1115"),
                        3: ("#c084fc", "#fff"),
                        4: ("#ec4899", "#fff"),
                    }
                    _tv_bg, _tv_fg = _tv_color_map.get(_tv_depth_0b, ("#D6ECF0", "#1F2937"))
                    tv_slot_new_badge = (
                        f'<span class="tv-badge tv-badge-xcoord" '
                        f'style="background:{_tv_bg}; color:{_tv_fg}; margin-left:4px;" '
                        f' title="5 叉 L_(k+1) 阶段 含 PREVIEW 1-based 序号 N={_tv_n_inc} → 2 叉 bit_reverse X 坐标 (TreeGenerate 风格)">'
                        f'{_tv_label}·{_tv_x}</span>'
                    )
            except Exception:
                pass
            items.append(
                f'<li class="tv-slot tv-slot-hl tv-slot-new">'
                f'<div class="tv-new-member">'
                f'<span class="tv-new-star">▲</span>'
                f'{rank_tag}'
                f'<span class="tv-new-name">{_html(hl.get("name") or "新成员")}</span>'
                f'<span class="tv-pv">{hl.get("pv", 0)} PV</span>'
                f'<span class="tv-new-tag">新挂载(原空位)</span>'
                f'{tv_slot_new_badge}'
                f'</div>'
                f'</li>'
            )
        else:
            # 真空位(无 ch 无 hl) — 也要算 N_inc, 这样缺失的子位也有 X 坐标
            #   (跟 avail 节点保持一致: 父优先 + 列优先, 含所有 5 个槽位的 1-based 序号)
            # ★ 2026-08-04 PR #9: 真空位 N 用 (line, 父的 line 槽位) 算
            _empty_n_inc = _next_n_inc(depth + 1, line=i, parent_line_id=int(parent.get("l1RootLine") or 0), l2_line=int(parent.get("parentLineId") or 0) if (depth + 1) >= 3 else None)
            _empty_x = _x_coord_from_n(_empty_n_inc, depth + 1)
            _empty_label = f"L{depth + 1}"
            if _empty_x is not None:
                _empty_x_html = (
                    f'<span class="tv-badge tv-badge-xcoord" '
                    f' style="background:#D6ECF0; color:#1F2937; margin-left:4px;" '
                    f' title="5 叉 L_k 阶段 1-based 序号 N={_empty_n_inc} → 2 叉 bit_reverse X 坐标 (TreeGenerate 风格)">'
                    f'{_empty_label}·{_empty_x}</span>'
                )
            else:
                _empty_x_html = ""
            items.append(
                f'<li class="tv-slot tv-slot-empty">'
                f'<div class="tv-empty">L{i} · 空位{_empty_x_html}</div>'
                f'</li>'
            )

    # ★ 2026-07-13 v4: 包一层 div.tv-row, 左侧加 tv-level-tag 层数标尺 (用户 2026-07-13 反馈:
    #   "最好在整个页面的左侧显示层数")
    #   level = depth + 1 (root 的 children 是 L1, root.children[0] 的 children 是 L2, ...)
    _row_level = depth + 1
    return (
        f'<div class="tv-row" data-depth="{_row_level}">'
        f'<span class="tv-level-tag">L{_row_level}</span>'
        f'<ul class="tv-children">{"".join(items)}</ul>'
        f'</div>'
    )


def _collect_expand_dist_ids(
    root: Dict[str, Any],
    highlight_map: Dict[str, Dict[int, Dict[str, Any]]],
) -> set:
    """预算需要自动展开的 dist_id 集合 — highlight 节点本身 + 所有祖先链上的节点

    用户反馈: 树深 161 节点,默认只展开前 2 层,要看到挂入位置得点十几次 ▶
    → 后端预算好 expand_set,渲染时强制 open,前端不用做事

    算法: 对每个 highlight parent_dist_id,沿 root 向下找该节点,记录从 root 到它的整条祖先链 dist_ids,
         这些 dist_ids 全部加进 expand set (父节点展开才能看到 highlight 槽位)
    """
    if not highlight_map:
        return set()

    target_dist_ids = set(highlight_map.keys())
    expand: set = set()

    def find_path(node: Dict[str, Any], target: str, ancestors: List[str]) -> Optional[List[str]]:
        """DFS 找 target_dist_id 的节点, 返回从 root 到它的祖先链 dist_id 列表(含自己)"""
        my_dist = node.get("distId") or ""
        my_chain = ancestors + ([my_dist] if my_dist else [])
        if my_dist == target:
            return my_chain
        for c in (node.get("children") or []):
            r = find_path(c, target, my_chain)
            if r is not None:
                return r
        return None

    for hl_dist_id in target_dist_ids:
        path = find_path(root, hl_dist_id, [])
        if path:
            for d in path:
                if d:
                    expand.add(d)
    return expand


# ★ 2026-07-13 v3: 5 叉 L_k 阶段 1-based 序号 + TreeGenerate 2 叉 bit_reverse 公式
#   算法 (跟 TreeGenerate 2 叉 visual i-order 一致):
#     1. 5 叉 L_k 阶段 真实节点按"父优先 + 列优先" 排, 跳过 avail, 1-based 序号 N (1, 2, 3, ...)
#     2. X 坐标 = 2^k + bit_reverse(N-1, k)  (跟 TreeGenerate 2 叉 L_k 公式完全一致)
#     3. N > 2^k 时 X = None (2 叉公式只到 2^k 位, 5 叉树超过 2^k 的真实节点没有 X 坐标)
#
#   5 叉 L2 阶段 4 个真实节点 + 2 叉 L2 公式 (k=2) 验证:
#     N=1 (张五)   → 2^2 + bit_reverse(0, 2) = 4 + 0 = 4   (L2-4 ✓)
#     N=2 (李三)   → 4 + bit_reverse(1, 2)     = 4 + 2 = 6   (L2-6 ✓)
#     N=3 (李四)   → 4 + bit_reverse(2, 2)     = 4 + 1 = 5   (L2-5 ✓)
#     N=4 (李五)   → 4 + bit_reverse(3, 2)     = 4 + 3 = 7   (L2-7 ✓)
#
#   5 叉 L3 阶段 4 个真实节点 + 2 叉 L3 公式 (k=3):
#     N=1 (赵 1)   → 2^3 + bit_reverse(0, 3) = 8 + 0 = 8   (L3-8 ✓)
#     N=2 (赵 2)   → 8 + bit_reverse(1, 3)     = 8 + 4 = 12
#     N=3 (赵 3)   → 8 + bit_reverse(2, 3)     = 8 + 2 = 10
#     N=4 (赵 4)   → 8 + bit_reverse(3, 3)     = 8 + 6 = 14
#
#   PREVIEW 节点 X (丁 1/2/3) 不在 raw dict, 在 _tree_render_children 渲染时
#   单独算"含 PREVIEW 5 叉 L_(k+1) 阶段 1-based 序号" N_inc + 2 叉公式
def bit_reverse(n: int, bits: int) -> int:
    """2 进制位反转 (跟 TreeGenerate gen_full_html.py::bit_reverse 一致)

    把 n 写成 bits 位二进制, 把位反转后转回 10 进制
    n=0, bits=2 → 0
    n=1, bits=2 → 2
    n=2, bits=2 → 1
    n=3, bits=2 → 3
    """
    r = 0
    for _ in range(bits):
        r = (r << 1) | (n & 1)
        n >>= 1
    return r


# ★ 2026-07-13 v3: 5 叉 L_(k+1) 阶段跨父跨列 1-based 序号 N_inc 计数器
#   渲染顺序 = "父优先 + 列优先" 排, 跳过 avail, 含 PREVIEW
#   raw 树真实子 + PREVIEW 节点都参与 N_inc 计数, 避免 X 坐标冲突
_GLOBAL_LV_K_N_INC: Dict[int, int] = {}  # depth → 含 PREVIEW 的 1-based 序号 N_inc (渲染顺序计数器)
# ★ 2026-07-16 PR #23: 业务规则「树状图默认显示: 仅激活槽位」
#   True = 显示全部槽位 (含 locked 灰色)
#   False (默认) = 仅显示激活槽位 (L1..eff_active)
#   api_tree_render 入口根据 req.slot_view 决定
_SLOT_VIEW_SHOW_LOCKED: bool = False


# ★ 2026-08-04 PR #5 → PR #9 (PR #71 v3 业务规则): 5 叉 line fill 顺序
#   4 大区按 line asc 排 (PR #9 翻案 PR #5 HORIZONTAL_ORDER [1, 3, 2, 4] 排):
#     line 1 = 4 大区 L1 父 1 (A, root.line 1)
#     line 2 = 4 大区 L1 父 2 (B, root.line 2)
#     line 3 = 4 大区 L1 父 3 (C, root.line 3)
#     line 4 = 4 大区 L1 父 4 (D, root.line 4)
#     line 5 = 4 大区 L1 父 5 (locked, eff=4 时不显示)
#   跟 skills/skill_5_3.HORIZONTAL_ORDER 同步, 用于 N_inc 渲染顺序
#   业务: 渲染时按 [1, 3, 2, 4, 5] 顺序遍历 children, N_inc 编号跟 PR #71 v3 fill step 严格一致
#   例: 4 大区 L1 父 (A, C, B, D) 标 L1·1, L1·2, L1·3, L1·4 (1-based N 编号)
# ★ 2026-08-04 PR #7: 4 大区横向顺序 (A=1, C=3, B=2, D=4) 跟 skills/skill_5_3.HORIZONTAL_ORDER 同步
#   用于 _next_n_inc 把 L2+ 子的 (line, parent_root_line) 映射到 1-based N
#   parent_region_idx = HORIZONTAL_ORDER_PR71.index(parent_root_line) (0..3)
_HORIZONTAL_ORDER_PR71: List[int] = [1, 3, 2, 4]

_LINE_FILL_ORDER_PR71: List[int] = [1, 2, 3, 4, 5]


def _settle_button_html(
    period_id: str,
    status: str,
    phase: str,
    can_supp: bool,
) -> str:
    """★ 2026-07-20 PR #55: 工具栏按钮动态 HTML

    业务规则:
      - phase=open (Sun-Fri): "💰 结算本周" 按钮 (主 settle, 算 own + 7 代对等)
      - phase=supplement (Sat-Mon): "🩹 补录上周" 按钮 (补录, 算 own only, 对等链冻结)
      - phase=closed (Tue 起): 按钮隐藏
      - status=open: 只能主 settle
      - status=settled + phase=supplement + can_supp: 只能补录
      - status=closed: 按钮隐藏

    Args:
        period_id: 当前业务周期 ID
        status: period.status (open / settled / closed)
        phase: 期间阶段 (open / supplement / closed)
        can_supp: can_supplement 判定
    Returns:
        HTML 字符串 (按钮 或 空字符串)
    """
    if phase == "supplement" and status == "settled" and can_supp:
        # 补录模式
        return (
            f'<button type="button" class="tv-toolbar-btn-settle tv-toolbar-btn-supplement" '
            f'id="settleCurrentWeekBtn" data-mode="supplement" '
            f'onclick="settleCurrentWeek(this)" '
            f'title="补录当前周期 ({period_id}): 只能补基本 commission, 对等链已冻结 (Mon 23:59 后失效)">'
            f'🩹 补录上周</button>'
        )
    elif phase == "open" and status == "open":
        # 主 settle 模式
        return (
            f'<button type="button" class="tv-toolbar-btn-settle" '
            f'id="settleCurrentWeekBtn" data-mode="settle" '
            f'onclick="settleCurrentWeek(this)" '
            f'title="结算当前周期 ({period_id}): 计算基本佣金 + 7 代对等, 剩余 PV carry 到下周期">'
            f'💰 结算本周</button>'
        )
    elif phase == "closed" or status in ("settled", "closed"):
        # 已经 settled/closed, 按钮隐藏 (或者显示 "已结算" 灰按钮)
        return (
            f'<span class="tv-stat tv-stat-settled" title="周期 ({period_id}) 已结算, '
            f'phase={phase} status={status}">✓ 本周已结算</span>'
        )
    # 默认 (其他异常状态): 显示主 settle 按钮
    return (
        f'<button type="button" class="tv-toolbar-btn-settle" '
        f'id="settleCurrentWeekBtn" data-mode="settle" '
        f'onclick="settleCurrentWeek(this)" title="结算当前周期 ({period_id})">'
        f'💰 结算本周</button>'
    )


def _reset_global_lv_k_n_inc() -> None:
    """重置 _GLOBAL_LV_K_N_INC 计数器 (每次 _build_tree_render_html 渲染前调用)"""
    global _GLOBAL_LV_K_N_INC
    _GLOBAL_LV_K_N_INC = {}


def _next_n_inc(
    depth: int,
    line: Optional[int] = None,
    parent_root_line: Optional[int] = None,  # 沿用 PR #7 参数 (透传, 业务上 L3+ 还需要, 暂保留)
    parent_line_id: Optional[int] = None,  # ★ 2026-08-04 PR #9: 节点在父的 line 槽位 (1-5)
    l2_line: Optional[int] = None,  # ★ 2026-08-04 PR #71 v5: L2 父 在 L1 父 的 line 槽位 (L3+ 父 用)
    is_locked: bool = False,
) -> Optional[int]:
    """深度 depth 的下一个含 PREVIEW 1-based 序号 N_inc (从 1 开始)

    渲染顺序 = "父优先 + 列优先" 排, 跳过 avail, 含 PREVIEW
    每次渲染一个真实子或 PREVIEW 节点后调用

    ★ 2026-08-04 PR #9 (PR #71 v3 业务规则, 用户原话 2026-08-04 翻案 PR #8):
      业务: L2+ 标 = line 优先 4 大区后, 4 大区按 parentLineId (1, 2, 3, 4) asc 排
        - L1 父 (depth=1): N=1..4 按 HORIZONTAL_ORDER 排 (PR #5 拍板, 不变)
        - L2+ (depth>=2): N = 4 + (depth-2)*8 + (line-1)*4 + parent_line_id
          业务动机 (用户原话 2026-08-04 翻案 PR #8):
            "m5: L2-5; m7: L2-6; m6: L2-7; m8: L2-8 -> 4 个大区, 左支全部布局完成;
             m9: L2-9; m11: L2-10; m10: L2-11; m12: L2-12 -> 右支全部布局完成"
            业务解读 (跟用户原话 12 个点位严格匹配):
              - 4 大区按 parentLineId asc 排 (1=A.line 1, 2=B.line 2, 3=C.line 3, 4=D.line 4)
              - 不是 HORIZONTAL_ORDER [1, 3, 2, 4], 是 line asc 排 [1, 2, 3, 4]
              - line 优先 4 大区后: line 1 4 大区全排, line 2 4 大区全排
            公式推导 (8 = 4 region × 2 active_line per region):
              - A.line 1 = 4 + 0*4 + 1 = 5 (parentLineId 1, line 1)
              - B.line 1 = 4 + 0*4 + 2 = 6 (parentLineId 2, line 1)
              - C.line 1 = 4 + 0*4 + 3 = 7 (parentLineId 3, line 1)
              - D.line 1 = 4 + 0*4 + 4 = 8 (parentLineId 4, line 1)
              - A.line 2 = 4 + 1*4 + 1 = 9
              - B.line 2 = 4 + 1*4 + 2 = 10
              - C.line 2 = 4 + 1*4 + 3 = 11
              - D.line 2 = 4 + 1*4 + 4 = 12
            - L3+ 沿用同样 (line, parentLineId) 排, (depth-2)*8 累加
              L3 line 1 (parentLineId 1, 2, 3, 4) = 13..16
              L3 line 2 (parentLineId 1, 2, 3, 4) = 17..20
              L4 line 1 = 21..24, ... L9 line 2 = 73..76
            - 业务 hardcode active_lines=2 (root.eff=2, 跟 L_k 父 eff 业务规则对齐, PR #18 拍板)
            - "L1 层和 Root 都不在规则中考虑" (用户原话): L1 父 N=1..4 不变, Root 不算 N
            - "4 叉 bit_reverse 公式" 业务理解: 4 大区 × 2 line 槽位 = 8 槽位 per depth
              业务 X 坐标公式 = 4^k + bit_reverse(N-1, k) 已被 1-based N 翻案 (PR #4)
              实际公式 = (line-1)*4 + parentLineId, 不用 bit_reverse, 业务理解跟 4 叉 base 类似
    - PR #8 翻案: 4 大区按 HORIZONTAL_ORDER [1, 3, 2, 4] 排, 每大区 line 1, 2 排 (region 优先 line 后)
      业务: A.line 1+2 = N 5, 6; C.line 1+2 = N 7, 8; B.line 1+2 = N 9, 10; D.line 1+2 = N 11, 12
      用户最新原话 (2026-08-04) 期望: 4 大区按 parentLineId asc 排 (1, 2, 3, 4)
        m5=5, m7=6, m6=7, m8=8 (A, B, C, D = parentLineId 1, 2, 3, 4 asc)
      PR #8 算法跟用户最新原话不符 (跟用户截图一致, 但跟用户最新原话文字不一致)
    - PR #7 翻案: line 优先 4 大区后, 4 大区按 HORIZONTAL_ORDER [1, 3, 2, 4] 排
      业务: line 1 4 大区 (A, C, B, D) = N 5..8, line 2 = N 9..12
      用户原话 PR #7: m5=5, m7=6, m6=7, m8=8 (跟 PR #9 一致!), line 2 同理
      但用户最新反馈 (2026-08-04) 说 "怎么 L2 层变成顺序排列了?" (指 PR #8 渲染 m5→m9→m6→m10)
        用户认为 PR #8 渲染的 L2 行 m5→m9→m6→m10→... 是"顺序排列" (region 优先, line 后)
        跟用户原话 (m5=5, m7=6, m6=7, m8=8) 不一致, 用户翻案 PR #8
      但 PR #7 算法也跟用户原话不一致 (m5=5, m7=6, m6=7, m8=8 是 PR #9 line 优先 parentLineId asc)
        PR #7 用 region_idx (=HORIZONTAL_ORDER.index(parent_root_line)), 业务上 A=0, C=1, B=2, D=3
        PR #7 m5=5, m6=6, m7=7, m8=8 (按 A, C, B, D), 跟用户原话 m5=5, m7=6, m6=7, m8=8 不符
        PR #7 实际渲染跟用户原话不一致 (用户当时给的是文字规则, 跟 PR #7 渲染细节不一致)
    - PR #6 4 叉 bit_reverse 翻案 (跟 PR #7, PR #8 翻案原因一致): 4 叉 L2 (k=2) 16 槽位
      vs 5 叉 4 大区 L2 20 节点, mod 4 cycle 重复
    - 兜底: line/parent_line_id 缺失时回退到旧"depth 累加"逻辑 (兼容老调用)

    ★ 2026-07-14 v7: is_locked=True (业务规则「双轨制」locked 槽位) 时:
       - 不累加 N_inc 计数器 (locked 槽位暂不参与位反转排位)
       - 返回 None (调用方不渲染 x_coord_badge)
       业务动机 (2026-07-14): 用户反馈"张五下面暂时只开 2 个区, 3/4/5 区先不要
       按位反转规律排列, 等开了再排", locked 槽位的位反转坐标不应该预先算出来。
       后续真解锁时, N_inc 会自然从 1 重新累加, X 坐标按新 unlocked 序列重算。
    """
    global _GLOBAL_LV_K_N_INC
    if is_locked:
        return None
    if depth == 0:
        # root (L0 阶段) 不算 N_inc, _tree_render_node 看 depth=0 不渲染 x_coord_badge
        return None
    if depth == 1:
        # L1 父: N=1..4 按 HORIZONTAL_ORDER 排 (PR #5 拍板, 不变)
        _GLOBAL_LV_K_N_INC[1] = _GLOBAL_LV_K_N_INC.get(1, 0) + 1
        return _GLOBAL_LV_K_N_INC[1]
    if depth >= 2 and line is not None and parent_line_id is not None:
        # L2+ (PR #10): N = line 优先 4 大区后, 4 大区按 region_idx (HORIZONTAL_ORDER) 排
        # PR #10 翻案 PR #9: region_idx = HORIZONTAL_ORDER_PR71.index(parent_line_id)
        #   parentLineId 1(A)→0, 2(B)→2, 3(C)→1, 4(D)→3
        #   让 N 标按 distId 顺序 (m5=5, m6=6, m7=7, m8=8 跟用户原话一致)
        # 8 = 4 region × 2 active_line (root.eff=2, PR #18 拍板)
        if parent_line_id in _HORIZONTAL_ORDER_PR71:
            region_idx = _HORIZONTAL_ORDER_PR71.index(parent_line_id)
        else:
            region_idx = 0  # 兜底: line 5 locked
        if depth == 2:
            # L2 (PR #10): N = 5 + (l2-1)*4 + region_idx
            n = 4 + (line - 1) * 4 + region_idx + 1
            return n
        # L3+ (PR #71 v5): N = (2^(d+1) - 3) + (l_d-1)*2^d + (l_(d-1)-1)*2^(d-1) + ... + (l2-1)*4 + region_idx
        # 业务: l_d (业务 line) + region_idx 业务 业务 业务 业务 业务
        # 业务: l_(d-1), ..., l2 业务 l2_line 业务 业务 (业务 L3+ 父 业务 业务 业务 业务 l2_line, 业务 业务 业务 业务 L4+ 业务 业务)
        n = 2 ** (depth + 1) - 3
        n += (line - 1) * (2 ** depth)  # l_d
        if depth == 3:
            # L3: l2 (业务 (l2-1)*4) 业务 l2_line 业务 业务
            if l2_line is not None and l2_line >= 1:
                n += (l2_line - 1) * 4
        else:
            # L4+: 业务 l2 (业务 (l2-1)*2^(d-1)) 业务 l2_line 业务 业务
            # 业务: l3 业务 (l3-1)*2^(d-2) 业务 l3_line 业务 业务 (业务 TODO: 业务 业务 业务 业务 l3_line)
            if l2_line is not None and l2_line >= 1:
                n += (l2_line - 1) * (2 ** (depth - 1))
            # 业务 l3_line 业务 业务 业务 业务 业务 业务 业务 (l3_line-1) * 2^(d-1)
            # 业务: 业务 业务 业务 业务 l3_line 业务 业务 业务 业务, 业务 业务 业务 业务 业务 业务 (TODO: 业务 业务 业务 l3_line)
            pass  # 业务 业务 业务 业务 业务 业务 业务 L4+ 业务 业务 业务 业务 业务 业务 业务 业务 业务
        n += region_idx
        return n
    # 兜底: 旧"depth 累加"逻辑 (兼容没传 line/parent_line_id 的老调用)
    _GLOBAL_LV_K_N_INC[depth] = _GLOBAL_LV_K_N_INC.get(depth, 0) + 1
    return _GLOBAL_LV_K_N_INC[depth]


def _x_coord_from_n(n: Optional[int], depth: int) -> Optional[int]:
    """N (1-based 序号) + depth (0-based L_k 阶段 k) → X 坐标

    ★ 2026-08-04 PR #9 (PR #71 v3 业务规则, 用户原话 2026-08-04 翻案 PR #8):
      业务: L2+ 标 = line 优先 4 大区后, 4 大区按 parentLineId (1, 2, 3, 4) asc 排
        - L1 父 (depth=1): N=1..4 按 HORIZONTAL_ORDER 排 (PR #5, 不变)
        - L2+ (depth>=2): N = 4 + (depth-2)*8 + (line-1)*4 + parentLineId
          例: m5(A.line 1)=5, m7(B.line 1)=6, m6(C.line 1)=7, m8(D.line 1)=8
              m9(A.line 2)=9, m11(B.line 2)=10, m10(C.line 2)=11, m12(D.line 2)=12
    - PR #8 翻案: 4 大区按 HORIZONTAL_ORDER [1, 3, 2, 4] 排, 每大区 line 1, 2 排
      业务: A.line 1+2=5, 6; C.line 1+2=7, 8; B.line 1+2=9, 10; D.line 1+2=11, 12
      用户最新原话 (2026-08-04) 期望 4 大区按 parentLineId asc 排, 跟 PR #8 不符
    - PR #7 翻案: 4 大区按 HORIZONTAL_ORDER [1, 3, 2, 4] 排, line 优先 4 大区后
      业务: line 1 4 大区 (A, C, B, D) = N 5..8, line 2 = N 9..12
      实际渲染 (A=5, C=6, B=7, D=8) 跟用户原话文字 (A=5, B=6, C=7, D=8) 不符
    - PR #6 4 叉 bit_reverse 翻案: 4 叉 L2 (k=2) 16 槽位 vs 5 叉 4 大区 L2 20 节点
      N=5..20 跟 N=1..16 模 4 cycle 重复, 业务显示 L2·16, L2·17, L2·16, L2·17 重标
      跟用户原话 "L2·5..L2·12 单调递增" 不符
    - PR #4 1-based N 翻案回: 维持 1-based N 编号, 跨 4 大区 line 优先 parentLineId 排
      L2 标 = L2·5..L2·12 (单调递增, 跟用户最新原话 12 个点位严格匹配)
    """
    if n is None or n <= 0:
        return None
    return n  # 1-based N 编号, 跨 4 大区 line 优先 parentLineId 排 (PR #9 翻案 PR #8 region 排)


# ★ 2026-07-13 v3: 不再需要 _compute_bitrev_x_coord (raw 树预遍历算 _x_coord 字段)
#   改用 _GLOBAL_LV_K_N_INC 跨父跨列 1-based 序号计数器, 在 _tree_render_children 渲染时
#   算每个真实子和 PREVIEW 节点的 N_inc + X 坐标 (避免 raw 树 N 序号和 PREVIEW N 序号冲突)


def _compute_direct_count_map(db) -> Dict[str, int]:
    """★ 2026-07-16 PR #38: 聚合每个成员被几个直推挂入 (parent_dist_id = self)

    - 直推人数 = DB members 表里 parent_dist_id = 当前节点 dist_id 的成员数
    - 实时算, 不存 DB (跟 PR #36 orphan 一样, 简单, 准, 不用 migration)
    - 返回 {dist_id: count}, 没在任何成员 parent 的 → 没在 dict 里 (默认 0)
    - 树状图/json 树都按这个 map 取
    """
    from sqlalchemy import select, func as sqlfunc
    stmt = (
        select(Member.parent_dist_id, sqlfunc.count(Member.id).label("n"))
        .where(Member.parent_dist_id.isnot(None))
        .where(Member.parent_dist_id != "")
        .group_by(Member.parent_dist_id)
    )
    out: Dict[str, int] = {}
    for row in db.execute(stmt).all():
        if row.parent_dist_id:
            out[row.parent_dist_id] = int(row.n or 0)
    return out


# ============================================================
# ★ 2026-08-06 PR #72: 基本佣金每条 commission line 每周 max 13334 PV (用户拍板)
#   业务: "基本佣金：以每个节点计算下面分支的佣金时候，每条佣金线每周最大值是13334PV。
#         超过的PV值也是按照最高13334PV来计算佣金。约合2000美金."
#   业务:
#     - 每条 commission line (= 5 子区 each) 每周 max 13334 PV
#     - P/L 配对时, 每子区 PV > 13334 算 13334 (cap, 但 carry 仍用原 PV)
#     - 最大 ownBasic = 13334 * 0.15 = ¥2000.10 ≈ $2000/周
#   业务场景: 5 子区都 20000 PV → capped 5×13334, P=13334, L=4×13334=53336, pair=13334, ownBasic=¥2000
#   跟 PR #71 teamBonus 不同维度: 这里是 5 子区 P/L 配对 cap, 不影响团队培育 (tier-based 累加)
#   跟 carry 关系: cap 只影响 commission 算, 剩余 PV (P_remain) 仍走 carry, 用原 PV
# ============================================================
BASIC_COMMISSION_LINE_PV_CAP: int = 13334


def _cap_commission_line_pv(pv: int) -> int:
    """PR #72: 每条 commission line PV cap 13334 (用于 ownBasic 5 子区 P/L 配对)"""
    return min(int(pv or 0), BASIC_COMMISSION_LINE_PV_CAP)


# ============================================================
# ★ 2026-08-06 PR #71: 团队培育奖金 4 档精确匹配 (用户拍板)
#   旧 (PR #69): 1区新PV + 2区新PV 全部按 30% 算 (单一比率)
#   新 (PR #71): 按"每个新成员 own periodPv"严格精确匹配, 4 档:
#     - 200 PV  → 15%
#     - 500 PV  → 20%
#     - 1000 PV → 25%
#     - 1500 PV → 30%
#     - 其它 (300/700/1200/2000/...)  → 0% (严格精确, 不套档不四舍五入)
#   业务场景: 1区新成员 A (500 PV) + 2区新成员 B (1500 PV)
#   → teamBonus = 500*20% + 1500*30% = 100 + 450 = 550
# ============================================================
TEAM_BONUS_TIER_RATES: dict = {
    200: 0.15,
    500: 0.20,
    1000: 0.25,
    1500: 0.30,
}


def _team_bonus_tier_rate(period_pv: int) -> float:
    """PR #71: 4 档精确匹配 — period_pv 必须严格 = {200, 500, 1000, 1500} 才给奖, 其它 0%"""
    return TEAM_BONUS_TIER_RATES.get(int(period_pv or 0), 0.0)


def _team_bonus_walk_subtree(node: Optional[Dict[str, Any]]) -> float:
    """PR #71: 递归走 1区/2区 subtree, 对每个成员的 own periodPv 应用 4 档精确匹配 rate, 累加

    Args:
        node: subtree 根节点 (slot 1 或 slot 2 子节点本身), dict 含 periodPv + children
    Returns:
        teamBonus 累加值 (¥)
    业务:
        1区 subtree 有 3 个新成员: A(500) + A.children[0](1500) + A.children[1](200)
        → 累加 500*20% + 1500*30% + 200*15% = 100 + 450 + 30 = 580
    """
    if node is None or node.get("available"):
        return 0.0
    own_pv = int(node.get("periodPv", 0) or 0)
    rate = _team_bonus_tier_rate(own_pv)
    total = own_pv * rate
    for c in node.get("children") or []:
        total += _team_bonus_walk_subtree(c)
    return total


# ============================================================
# ★ 2026-08-06 PR #73: 储蓄奖金 preview (跟 settle 公式一致)
#   - 业务: ownBasic ≥ $250 USD 时, savings = min(ownBasic × 15%, $500)
#   - 跟 ownBasic 联动, commission 数字直接当美元理解 (无汇率)
#   - 节点自己拿, 不分给祖先
#   - preview 跟 settle 一致
# ============================================================
SAVINGS_BONUS_USD_THRESHOLD: float = 250.0
SAVINGS_BONUS_USD_RATE: float = 0.15
SAVINGS_BONUS_USD_CAP: float = 500.0


def _savings_bonus_usd(own_basic: float) -> float:
    """★ 2026-08-06 PR #73: 储蓄奖金 (USD) = min(ownBasic × 15%, $500) if ownBasic ≥ $250 else 0
    commission 数字直接当美元理解 (无汇率, 跟 COMMISSION_RATE=0.15 同源)
    """
    if own_basic < SAVINGS_BONUS_USD_THRESHOLD:
        return 0.0
    return round(min(float(own_basic) * SAVINGS_BONUS_USD_RATE, SAVINGS_BONUS_USD_CAP), 4)


# ============================================================
# ★ 2026-07-16 PR #39: tree view 以 DB 为权威 — 完全从 DB 构建 5 叉树 dict
#   替代之前的 _sync_raw_names_with_db / _compute_orphan_set / _inject_direct_count
#   返回结构跟 json fixture 兼容 (递归 dict, 含 distId/name/parentLineId/maxLines/children/available)
#   下游 _build_tree_render_html / _tree_render_node / 算法层都可以直接用
# ============================================================
def _build_tree_from_db(db) -> Dict[str, Any]:
    """★ 2026-07-16 PR #39: 从 members 表构建完整 5 叉树 dict (DB 是权威)

    - 拉所有 members, 找 root (parent_dist_id=空 + slot_line_id=0)
    - 按 parent_dist_id + slot_line_id 建索引
    - 递归从 root 构建 dict, 算 avail 占位 (real_children < maxLines 时补)
    - 实时算 directCount (PR #38)
    - 注入 period_pv: 本期 (current_period) 新增 PV 聚合 (PR #51, 从 PVLedger.pv_amount 算)
    - 没有 root 时返回占位空树
    """
    # ★ 2026-07-17 PR #51: 本期 PV 聚合 (从 PVLedger.pv_amount 算)
    from sqlalchemy import func as sqlfunc  # noqa: F401
    members = db.query(Member).all()
    # 1. 找 root
    roots = [m for m in members if (not m.parent_dist_id) and (m.slot_line_id or 0) == 0]
    # 2. 按 parent_dist_id + slot_line_id 建索引
    children_by_parent: Dict[str, Dict[int, Any]] = {}
    for m in members:
        if m.parent_dist_id and m.slot_line_id and m.slot_line_id > 0:
            children_by_parent.setdefault(m.parent_dist_id, {})[int(m.slot_line_id)] = m
    # 3. 直推数 (PR #38 实时聚合)
    direct_count_map = _compute_direct_count_map(db)
    # 4. ★ PR #51: 本期新增 PV 聚合 (从 PVLedger.pv_amount 算)
    #   - 按 member_id + period_id=current 聚合 SUM(pv_amount)
    #   - 替代之前 _tree_render_node 显示 Member.current_pv_balance (剩余 PV, 跨期 carry)
    #   - 用户 (2026-07-17) 反馈: 名片上要看本期新增, 不是剩余
    _current_period = get_current_period_id()
    # ★ 2026-07-17 PR #54 v2: 查当前 ISO 周的 status
    #   - 本期 PV 徽章只在 current_period.status == "open" 时显示
    #   - 用户反馈: "结算后张a 本期500PV 这个位置应该变成 剩余200PV"
    #   - 业务规则: 同一位置, 本期(open) vs 剩余(settled 或 carry 余额) 互斥显示
    #   - 之前 PR #51 错误: 任何 _period_pv > 0 都显示, 跟 carry 重复展示已 settled 的本期
    _current_period_status = "open"  # 默认 open (没在 commission_periods 表里)
    _period_row = (
        db.query(CommissionPeriod)
        .filter(CommissionPeriod.id == _current_period)
        .one_or_none()
    )
    if _period_row is not None:
        _current_period_status = _period_row.status or "open"
    _period_pv_map: Dict[int, int] = {}
    _period_pv_rows = (
        db.query(PVLedger.member_id, sqlfunc.coalesce(sqlfunc.sum(PVLedger.pv_amount), 0))
        .filter(PVLedger.period_id == _current_period)
        .group_by(PVLedger.member_id)
        .all()
    )
    for _mid, _sum in _period_pv_rows:
        _period_pv_map[int(_mid)] = int(_sum or 0)
    if not roots:
        # 没有 root 行 → 返回空树
        return {
            "distId": "", "name": "(空 — DB 还没有 root 行)", "parentLineId": 0,
            "maxLines": 5, "maxActiveLines": 4, "pv": 0, "periodPv": 0, "directCount": 0, "depth": 0, "children": [],
        }
    root_member = roots[0]

    def _build(member, depth: int, parent_line_id: int, l1_root_line: int = 0) -> Dict[str, Any]:
        # 2026-08-03 feat-eff-4-root: root 节点 maxActiveLines=4 (PR 拍板), 其他 default 2
        _is_root = (member.parent_dist_id is None)
        _max_active_lines = 4 if _is_root else 2
        # ★ PR #71 v5: L1 父 在 root 的 line 槽位 (供 L3+ 标 region_idx)
        #   - L1 父 (depth=1): 等于自己的 parentLineId (= root line 槽位)
        #   - L2+ 父 (depth>=2): 父的 l1RootLine (L1 父 在 root 的 line 槽位)

        real_children = children_by_parent.get(member.member_dist_id, {})
        max_lines = int(member.max_lines or 5)
        # 收集 real 子节点 (按 slot_line_id 排序)
        child_dicts: List[Dict[str, Any]] = []
        for slot in sorted(real_children.keys()):
            # ★ PR #71 v5: 传 l1RootLine 给子
            #   - depth=0 (root) → L1 父: l1RootLine = slot (L1 父 在 root 的 line 槽位)
            #   - depth>=1 (L1 父) → L2+ 父: l1RootLine = l1_root_line (继承自 L1 父)
            _child_l1_root_line = slot if depth == 0 else l1_root_line
            child_dicts.append(_build(real_children[slot], depth + 1, slot, l1_root_line=_child_l1_root_line))
        # 补 avail 占位 (real 没占满的位置)
        for slot in range(1, max_lines + 1):
            if slot not in real_children:
                child_dicts.append({
                    "available": True,
                    "parentLineId": slot,
                    "maxLines": max_lines,  # 继承父
                })
        # ★ 2026-07-23 PR #67: 算 ownBasic 用递归累加的"子区总 PV" (subtreePv)
        #   - 业务: ABCD 4 member 树 root → A(L1) + B(L2), A → C, B → D
        #     root 1 区 = A 子区 (A own + C own 递归) = 3000, 2 区 = B 子区 (B own + D own) = 2000
        #     MIN(3000, 2000) × 15% = 300 (用户的"1区/2区"是递归累加, 不是只看直接子)
        #   - 旧 (PR #58): 用 children[].periodPv 只看 1 层, max(1500,1000)=1500, pair=1000, commission=150
        #     → 跟算法层 PR #66 (递归累加) 不对齐, 算少一半
        #   - 新 (PR #67): 用 children[].subtreePv (own + 子孙 PV 递归累加, 跟算法层 c_pv_total 一致)
        #     max(3000, 2000)=3000, pair=2000, commission=300
        #   - 跟 settle_period._settle_node 算 node.commission 完全一致
        own_pv = int(_period_pv_map.get(int(member.id), 0))
        # ★ PR #67: 算本节点 subtreePv = own + sum(子节点 subtreePv), 递归
        children_subtree_pv = sum(
            int(cd.get("subtreePv", 0) or 0)
            for cd in child_dicts
            if not cd.get("available")
        )
        subtree_pv = own_pv + children_subtree_pv
        # ★ PR #69 → PR #71: 团队培育奖金 — 4 档精确匹配 (用户 2026-08-06 拍板)
        #   - 旧 (PR #69): 1区新PV + 2区新PV 全部按 30% 算
        #   - 新 (PR #71): 按"每个新成员 own periodPv"严格精确匹配 4 档:
        #     - 200 PV  → 15%
        #     - 500 PV  → 20%
        #     - 1000 PV → 25%
        #     - 1500 PV → 30%
        #     - 其它 → 0% (严格精确, 不套档不四舍五入)
        #   - 只看 slot 1 / slot 2 (1区左支 + 2区右支), 不看 3/4/5 区
        #   - 走 1区/2区 子树, 对每个成员 own periodPv 应用 tier rate, 累加
        #   - 业务场景: 1区新成员 A (500) + 2区新成员 B (1500)
        #     → teamBonus = 500*20% + 1500*30% = 100 + 450 = 550
        children_subtree_period_pv = sum(
            int(cd.get("subtreePeriodPv", 0) or 0)
            for cd in child_dicts
            if not cd.get("available")
        )
        subtree_period_pv = own_pv + children_subtree_period_pv
        # PR #71: 找 1区 (slot 1) + 2区 (slot 2) 子树根, 递归算 tier-based 累加
        left_branch_subtree: Optional[Dict[str, Any]] = None
        right_branch_subtree: Optional[Dict[str, Any]] = None
        for cd in child_dicts:
            if cd.get("available"):
                continue
            cd_slot = int(cd.get("parentLineId", 0) or 0)
            if cd_slot == 1:
                left_branch_subtree = cd
            elif cd_slot == 2:
                right_branch_subtree = cd
        team_bonus = _team_bonus_walk_subtree(left_branch_subtree) + _team_bonus_walk_subtree(right_branch_subtree)
        # 子区配对: P = max(n 子区 subtreePv), L = 其他 (n-1) 子区
        real_child_pvs = [
            int(cd.get("subtreePv", 0) or 0)
            for cd in child_dicts
            if not cd.get("available")
        ]
        # ★ PR #68 翻案 PR #67: 节点 commission = sub_pair × 15% (n 子区 P/L 配对)
        #   旧 (PR #67): (own_pair + sub_pair) × 15% — own 参与配对, 错!
        #   新 (PR #68): own 不参与, 只算 n 子区 P/L 配对
        # ★ PR #72: 每条 commission line 每周 max 13334 PV
        #   业务: "每条佣金线每周最大值是13334PV, 超过按 13334 算, 约合 2000 美金"
        #   业务区分 (用户 2026-08-06 拍板):
        #     - 2 叉 (2 子区, 1 P + 1 L): sub_pair = min(P, L) × 15% (cap 13334)
        #     - >2 叉 (3/4/5 子区, 1 P + (n-1) L): (n-1) 个 L 线各 cap 13334 × 15%
        #       P 不参与 commission 算
        #       每条 L 线 commission = min(L, 13334) × 15%
        #       carry: 所有 n 条线 (P + L) 各 carry = max(0, PV - 13334)
        #   业务示例 (5 子区, 各 20000 PV):
        #     - 旧 (sub_pair): 4 L lines × 13334 × 15% = 8000 (错, P 算 1 pair)
        #     - 新 (L-lines): 4 L lines × 13334 × 15% = 8000.40 (P 0)
        #   业务示例 (2 子区, 各 20000 PV):
        #     - sub_pair = min(13334, 13334) = 13334
        #     - commission = 13334 × 15% = 2000.10
        #   carry: P_carry = max(0, P - 13334), L_carry = max(0, L - 13334) (per-line cap)
        capped_child_pvs = [_cap_commission_line_pv(pv) for pv in real_child_pvs]
        own_basic = 0.0
        if capped_child_pvs:
            n_lines = len(capped_child_pvs)
            if n_lines == 2:
                # 2 叉: sub_pair = min(P_capped, L_capped) × 15%
                p_pv = max(capped_child_pvs)
                l_sum = sum(capped_child_pvs) - p_pv
                sub_pair = min(p_pv, l_sum)
                own_basic = float(sub_pair * 0.15)
            else:
                # >2 叉: (n-1) 个 L 线各 cap 13334 × 15%, P 不参与
                # 找 P (最强) + (n-1) L 线 (其它)
                sorted_capped = sorted(capped_child_pvs, reverse=True)
                l_pvs_capped = sorted_capped[1:]  # (n-1) 个 L 线 (cap 后)
                own_basic = float(sum(l_pvs_capped) * 0.15)
        # ★ PR #69: commissionPreview 加上团队培育奖金
        #   旧 (PR #58-#68): ownBasic + pairBonus (7 层对等)
        #   新 (PR #69): ownBasic + pairBonus (7 层对等) + teamBonus (团队培育奖金)
        commission_preview = own_basic
        return {
            "distId": member.member_dist_id or "",
            "name": member.member_name or "",
            "parentDistId": member.parent_dist_id or "",
            "parentLineId": parent_line_id,
            # ★ PR #71 v5: L1 父 在 root 的 line 槽位 (供 _next_n_inc 算 L3+ 标 region_idx)
            "l1RootLine": l1_root_line,
            "maxLines": max_lines,
            "maxActiveLines": _max_active_lines,  # 2026-08-03 feat-eff-4-root: root=4 / 其他=2
            # ★ PR #51 改名: pv 字段 = 剩余 PV (carry, 跨期累积) — 留给 commission 计算
            "pv": int(member.current_pv_balance or 0),
            # ★ PR #51 新增: periodPv = 本期新增 PV 聚合 (从 PVLedger)
            "periodPv": int(_period_pv_map.get(int(member.id), 0)),
            # ★ 2026-07-17 PR #54 v2: currentPeriodStatus = 当前 ISO 周状态 (open/settled)
            #   - 本期 PV 徽章仅在 status=open 时显示
            #   - settled 期下隐藏本期 PV (本期已落账到 carry/commission, 应显示 carry)
            "currentPeriodStatus": _current_period_status,
            # ★ PR #51 新增: totalCommission = 累计 commission (历史所有期总和, 来自 Member.total_commission)
            "totalCommission": float(member.total_commission or 0.0),
            "directCount": int(direct_count_map.get(member.member_dist_id, 0)),
            "depth": depth,
            # ★ 2026-07-16 PR #41: 角色 (供 _tree_render_node 渲染徽章)
            "role": _normalize_role(getattr(member, "role", None)),
            # ★ 2026-08-06 PR #75: 业务档位 (4 档位独立列, 跟 role 字段独立)
            #   - 业务上 4 档位 (激活/商务/精英/至尊) 跟 PR #71 teamBonus 4 档对应
            #   - 跟 role 字段独立 (role 7 个, business_level 4 个, 2 套并存)
            "business_level": _normalize_business_level(getattr(member, "business_level", None)),
            # ★ 2026-07-24 PR #67: subtreePv = own + 子孙 PV 递归累加 (跟算法层 c_pv_total 一致)
            #   - 父节点 ownBasic 算 5 子区 P/L 配对时用这个递归子区 PV
            #   - 跟 PR #66 算法层 _settle_node._sum_sub 一致
            "subtreePv": subtree_pv,
            # ★ PR #69: subtreePeriodPv = own + 子孙 periodPv 递归累加 (只本期新增, 不含 carry)
            #   - 跟 subtreePv 类似, 但只用 periodPv (本期的 PV)
            #   - 用在 teamBonus 算 1区/2区 新PV
            "subtreePeriodPv": subtree_period_pv,
            # ★ PR #69 → PR #71: 1区/2区 tier-based 累加 (跟 teamBonus 公式一致, 方便前端展示)
            #   - 旧 (PR #69): 1区/2区 整个 subtree 的 recursive 新PV
            #   - 新 (PR #71): 1区/2区 每个成员 own periodPv 严格精确匹配 4 档累加
            #   - 业务: 1区新成员 A(500) → 1区贡献 500*20% = 100
            "leftBranchPv": _team_bonus_walk_subtree(left_branch_subtree),
            "rightBranchPv": _team_bonus_walk_subtree(right_branch_subtree),
            # ★ PR #69 → PR #71: 团队培育奖金 = left + right tier-based 累加
            "teamBonus": team_bonus,
            # ★ 2026-07-21 PR #58 + 2026-07-24 PR #67: ownBasic = 本期 own basic commission
            #   - PR #58: 5 子区 P vs L × 15%, 用 children[].periodPv (只看 1 层)
            #   - PR #67: 改用 children[].subtreePv (递归累加, 跟算法层 PR #66 对齐)
            #     + own_pair (own 跟 P 配对消耗, 兼容 T5 测试) + sub_pair (5 子区 P/L)
            "ownBasic": own_basic,
            # ★ 2026-07-21 PR #58: commissionPreview = 本期可拿 = ownBasic + pairBonus (7 层对等)
            #   - 初始化 = ownBasic, _accumulate_pair_bonus 累加子孙分润
            #   - PR #69: 再加 teamBonus (团队培育奖金)
            "commissionPreview": commission_preview,
            # ★ 2026-08-06 PR #73: 储蓄奖金 preview (美元, ownBasic ≥ 250 才显示)
            #   - 跟 ownBasic 联动: savings = min(ownBasic × 15%, $500)
            #   - 业务: 当周基本佣金 ≥ $250 时触发, 上限 $500
            "savingsPreview": _savings_bonus_usd(own_basic),
            # ★ 2026-08-06 PR #73: 储蓄奖金累计 (历史总和, USD, 来自 Member.savings_balance)
            "savingsBalance": float(member.savings_balance or 0.0),
            "children": child_dicts,
        }

    tree = _build(root_member, 0, 0)

    # ★ 2026-07-21 PR #58: 1-6 代对等累加 (PR #74 拍板, 7 代拿不到)
    #   对每个节点的 ownBasic, 按 PAIRING_BONUS_RATIOS (dict, key=1..6) 分给 1/2/3/4/5/6 代祖先
    #   跟 settle_period._apply_pairing_bonus 规则完全一致 (PR #1 + PR #74 业务规则)
    #   简化实现: 前序遍历, ancestor_nodes = [父, 祖父, ..., 6代祖先], 累加到每个 ancestor.commissionPreview
    # ★ PR #69: 同步累加 teamBonus 到 commissionPreview (1区 + 2区 新PV × 30%)
    #   teamBonus 不分给祖先 (团队培育是节点自己的下线奖励, 跟 1-6 代对等是不同维度)
    # ★ PR #74: 4-5 代门槛检查 (ancestor 本期 ownBasic USD ≥ $500 / $1000)
    #   - 6 代 always 拿 (默认 1 个佣金部门, 业务上 always 满足)
    #   - 7 代永远拿不到 (业务上做不到 2 个佣金部门, ratio=0)
    def _accumulate_pair_bonus(node: Dict[str, Any], ancestor_nodes: List[Dict[str, Any]]) -> None:
        own = float(node.get("ownBasic", 0.0) or 0.0)
        if own > 0:
            for i, anc in enumerate(ancestor_nodes[:PAIRING_BONUS_MAX_DEPTH]):
                # i 是 0-based (i=0 → 第 1 代), PAIRING_BONUS_RATIOS key 是 1-based
                gen = i + 1
                ratio = PAIRING_BONUS_RATIOS.get(gen, 0.0)  # 7 代拿不到
                if ratio <= 0:
                    continue
                # ★ PR #74: 4-5 代 ancestor 门槛检查 (ownBasic USD)
                if gen == 4:
                    anc_ownbasic = float(anc.get("ownBasic", 0.0) or 0.0)
                    if anc_ownbasic < PAIRING_BONUS_4TH_USD_THRESHOLD:
                        continue
                elif gen == 5:
                    anc_ownbasic = float(anc.get("ownBasic", 0.0) or 0.0)
                    if anc_ownbasic < PAIRING_BONUS_5TH_USD_THRESHOLD:
                        continue
                # 6 代: always 拿 (默认 1 个部门, 业务 always 满足)
                anc["commissionPreview"] = float(anc.get("commissionPreview", 0.0) or 0.0) + own * ratio
        # 团队培育奖金只加给节点自己, 不分给祖先
        team_bonus = float(node.get("teamBonus", 0.0) or 0.0)
        if team_bonus > 0:
            node["commissionPreview"] = float(node.get("commissionPreview", 0.0) or 0.0) + team_bonus
        for child in node.get("children", []) or []:
            if child.get("available"):
                continue
            _accumulate_pair_bonus(child, [node] + ancestor_nodes)

    _accumulate_pair_bonus(tree, [])

    return tree


# ============================================================
# ★ 2026-07-16 PR #39: 算法层 (skill_5_3) 也从 DB 拿树, 不用 json
#   - 之前 (PR #8/19/22): load_tree_from_jstree_file 读 json/Tree_empty_5_3.json
#   - 现在 (PR #39): _build_node5_tree_from_db 直接从 DB 拉 members, 构 Node5 树
#   - 跟 _build_tree_from_db (渲染层) 互相对应 — 同一数据源, 同一棵树
# ============================================================
def _build_node5_tree_from_db(db) -> Tuple[Node5, Dict[int, str]]:
    """★ 2026-07-16 PR #39: 从 members 表构建 Node5 树 (供算法层 simulate_addition_bitrev 用)

    跟 _build_tree_from_db (渲染层) 的差异:
      - 返 Node5 对象 (不是 dict) — 算法层模拟挂入需要
      - avail 占位节点用 distId="" + is_avail=True 表示 (跟 load_from_jstree_dict 一致)
      - 返 uid_to_dist_id: uid (int) → distId (str) 反查表 (算法层 simulate_addition_bitrev
        用它把 Node5.uid 映射回 officev2 distId, 给前端 highlight 用)

    找不到 root 时返空 5 叉 root (跟旧 fallback 行为一致, 算法可以预览)
    """
    from skill_5_lib import Node5

    members = db.query(Member).all()
    roots = [m for m in members if (not m.parent_dist_id) and (m.slot_line_id or 0) == 0]

    uid_to_dist_id: Dict[int, str] = {}

    def _member_to_uid(m: Member) -> int:
        """把 member_dist_id 转成 Node5.uid (int) — ★ 2026-07-17 PR #50 修

        旧实现 (PR #39):  "(N5637590.1).lstrip('N').split('.')[0]" = "5637590"
                          → 所有 N5637590.X 节点都解析成 uid=5637590 (跟 root 同!)
                          → 算法 BFS 索引混乱, 4 成员 batch 全部挂同一槽位
        新实现 (PR #50):
          - N5637590.X  → 5637590 * 10^8 + X = 唯一大整数 (X ∈ 1..10^8)
                          跟 "PREVIEW-N" 负数区分, 跟 root=563759000000001 区分
                          例: N5637590.1 → 563759000000001, N5637590.10 → 563759000000010
          - N-7XXXXXX   → 负数 (跟 root 区分), 保留原 PR #39 行为
          - A<n>.<k>    → 7_000_000_000_000 + n*100 + k (★ 2026-08-05 原树迁入加)
                          原树 20 个 A 格式节点 (root=万陵洋 A8066781.1),
                          旧 fallback int("A8066781") 失败 → uid=0 撞 avail 占位保留值
                          独立号段 (7×10^12 起), 不跟 N5637590 段 (5.6×10^14) /
                          N-7 负数段 / N 格式 fallback 裸数字撞号
          - 其他/空     → 0
        """
        did = (m.member_dist_id or "").strip()
        if not did:
            return 0
        # 新格式 N5637590.X
        if did.startswith("N5637590."):
            try:
                tail = int(did.split(".", 1)[1])
                return 5637590 * 100_000_000 + tail
            except (ValueError, IndexError):
                return 0
        # 旧格式 N-7XXXXXX (负数, 跟 root 区分)
        if did.startswith("N-7"):
            try:
                num_str = did[3:]
                return -int(num_str)
            except ValueError:
                return 0
        # ★ 2026-08-05 原树迁入: A<n>.<k> 格式 (e.g. A8066781.1)
        import re as _re_uid
        _am = _re_uid.match(r"^A(\d+)\.(\d+)$", did)
        if _am:
            return 7_000_000_000_000 + int(_am.group(1)) * 100 + int(_am.group(2))
        # fallback (N-5.../N-6.../空): 跟旧实现一致
        digits = did.lstrip("N").lstrip("n").split(".")[0]
        try:
            return int(digits)
        except (ValueError, TypeError):
            return 0

    if not roots:
        # 没 root → 返空 5 叉 root (跟旧 load_tree_from_jstree_file fallback 一致)
        root = Node5(uid=1, pv=1000, depth=0, name="", max_children=5, max_active_lines=4, is_avail=False, line_id=0)
        uid_to_dist_id[1] = "N5637590.1"  # 占位 distId (前端 highlight 用)
        return root, uid_to_dist_id

    root_member = roots[0]

    # 按 parent_dist_id + slot_line_id 建索引 (跟 _build_tree_from_db 一致)
    children_by_parent: Dict[str, Dict[int, Member]] = {}
    for m in members:
        if m.parent_dist_id and m.slot_line_id and m.slot_line_id > 0:
            children_by_parent.setdefault(m.parent_dist_id, {})[int(m.slot_line_id)] = m

    def _build_node5(member: Member, depth: int, line_id: int) -> Node5:
        uid = _member_to_uid(member)
        if uid and member.member_dist_id:
            uid_to_dist_id[uid] = member.member_dist_id
        max_children = int(member.max_lines or 5)
        node = Node5(
            uid=uid,
            pv=int(member.current_pv_balance or 0),
            depth=depth,
            name=member.member_name or "",
            max_children=max_children,
            max_active_lines=(4 if line_id == 0 else 2),  # root 显式 4 (PR 拍板), 其他 2 渐进解锁
            is_avail=False,
            line_id=line_id,
        )
        real_children = children_by_parent.get(member.member_dist_id, {})
        # 补 avail 占位 + real 子 (按 slot_line_id 排序)
        for slot in range(1, max_children + 1):
            if slot in real_children:
                node.children.append(_build_node5(real_children[slot], depth + 1, slot))
            else:
                # avail 占位 — uid=0 (跟 load_from_jstree_dict 行为一致: 跳过 avail 节点的 distId 解析)
                avail = Node5(
                    uid=0, pv=0, depth=depth + 1, name="",
                    max_children=max_children, max_active_lines=4,  # 跟 root 同步 (PR 拍板), 渲染 L4 avail line 1-4 unlocked
                    is_avail=True, line_id=slot,
                )
                node.children.append(avail)
        return node

    return _build_node5(root_member, 0, 0), uid_to_dist_id


def _compute_max_synthetic_dist_id_from_db(db) -> int:
    """★ 2026-07-17 PR #50: 从 DB 找最大 N5637590.X 编号 (尾号)

    - 用途: 算法层 simulate_addition_bitrev.start_rank, 让新 uid 全局递增
    - 旧 (PR #39): regex `^N-7(\d{6,})$` 找 N-7XXXXXX 最大编号
    - 新 (PR #50): regex `^N5637590\.(\d+)$` 找 N5637590.X 最大尾号
      - 用户 (2026-07-17) 要求所有 member 编码用 N5637590.X 格式, 尾号依次 +1
      - 下个新成员分配: f"N5637590.{max_num + 1}"
    - 没找到返回 0 (下个新成员分配 N5637590.1, 但 root 已经是 .1 所以不会到 0)
    """
    import re
    pattern = re.compile(r"^N5637590\.(\d+)$")
    max_num = 0
    for m in db.query(Member.member_dist_id).all():
        did = m.member_dist_id or ""
        match = pattern.match(did)
        if match:
            try:
                n = int(match.group(1))
                if n > max_num:
                    max_num = n
            except (TypeError, ValueError):
                pass
    return max_num


def _build_tree_render_html(
    raw: Dict[str, Any],
    highlight_map: Dict[str, Dict[int, Dict[str, Any]]],
    preview_rank_map: Optional[Dict[str, int]] = None,
    orphan_set: Optional[set] = None,  # ★ 2026-07-16 PR #39: deprecated, 保留参数兼容旧调用 (now ignored)
    db: Optional[Any] = None,  # ★ 2026-07-17 PR #51: 注入 db session (给 toolbar 算本期 commission 概览)
) -> str:
    """构建整树 HTML 字符串,带 toolbar 容器
    preview_rank_map : {member_dist_id (PREVIEW-N): rank} — 2026-07-05 v3:
                       用于 PREVIEW- 父节点下动态插入虚拟子成员子树(#3 这种)
    db               : ★ 2026-07-17 PR #51: db session, 给 toolbar 算本期 commission 概览
                       None 时跳过 (兼容旧 callers)
    orphan_set       : 2026-07-16 PR #36: dist_id 集合, 表示"json 树有但 DB 没有"的孤儿节点
                       工具栏显示计数, 节点本身加 .tv-orphan class + ✗ 标记
    """
    orphan_set = orphan_set or set()
    # ★ 2026-07-17 PR #51: 局部 import sqlfunc (跟 _compute_direct_count_map 保持一致)
    from sqlalchemy import func as sqlfunc  # noqa: F401
    # ★ 2026-07-13 v3: 重置 5 叉 L_(k+1) 阶段跨父跨列 1-based 序号 N_inc 计数器
    #   渲染顺序 = "父优先 + 列优先" 排, 跳过 avail, 含 PREVIEW
    #   raw 树真实子 + PREVIEW 节点都参与 N_inc 计数, 避免 X 坐标冲突
    _reset_global_lv_k_n_inc()

    # ★ 预算需要自动展开的 dist_id 集合 — 让 highlight 位置的所有祖先链都展开
    expand_set = _collect_expand_dist_ids(raw, highlight_map)
    # root (L0 阶段) N_inc = 1, X = 2^0 + bit_reverse(0, 0) = 1
    root_n_inc = _next_n_inc(0)
    body = _tree_render_node(raw, highlight_map, expand_set=expand_set, depth=0, preview_rank_map=preview_rank_map or {}, _n_inc=root_n_inc, orphan_set=orphan_set)

    # 摘要
    def _count(n):
        c = 1
        a = 1 if n.get("available") is True else 0
        for ch in n.get("children") or []:
            x, y = _count(ch)
            c += x; a += y
        return c, a

    total_nodes, total_avail = _count(raw)
    hl_count = sum(len(v) for v in highlight_map.values())
    # ★ 2026-07-16 PR #39: orphan 工具栏统计废弃 (DB 是权威, 没 orphan 概念)
    # ★ 2026-07-17 PR #51: 加 "💰 结算本周" 按钮 + 本周 commission 概览
    #   - 当前 ISO 周: 工具栏显示, 跟用户口径 "本周" 一致
    #   - 本周总 commission: 来自本期 ledger 中 total_commission 之和 (由 settle API 写)
    #     但结算前是 0, 结算后才有值, 渲染时从本期 ledger 聚合 (实时, 不需要缓存)
    _cur_period = get_current_period_id()
    _cur_period_comm = 0.0
    _cur_period_pv_total = 0
    # ★ 2026-07-20 PR #55: 工具栏按钮动态文案 (基于 current period 的 phase)
    #   - open: 标准期, "💰 结算本周" (own + pairing)
    #   - supplement: Sat-Mon 补录期, "🩹 补录上周" (own only, 对等冻结)
    #   - closed: Tue 起, 按钮隐藏
    from skills.period import get_period_phase, can_supplement as _can_supplement
    _cur_phase = get_period_phase(_cur_period)
    # 找上一周期 (closed 期才能补) - 这里只看 current 的 phase
    # 实际补录的是「上一周期」, 业务上 "本周" 仍可被补 (因为 Sat-Mon 时, 业务周期 ID = 上一周期)
    _can_supp = _can_supplement(_cur_period)
    if db is not None:
        # 本期总 commission (本期 settle 后, ledger.commission_amount 之和)
        _cur_period_comm = float(
            db.query(sqlfunc.coalesce(sqlfunc.sum(PVLedger.commission_amount), 0.0))
            .filter(PVLedger.period_id == _cur_period)
            .scalar() or 0.0
        )
        # 本期总新增 PV (本期 ledger.pv_amount 之和, 跟 _build_tree_from_db 的 _period_pv_map 一致)
        _cur_period_pv_total = int(
            db.query(sqlfunc.coalesce(sqlfunc.sum(PVLedger.pv_amount), 0))
            .filter(PVLedger.period_id == _cur_period)
            .scalar() or 0
        )
        # ★ PR #55: 补录按钮显隐 (只有 current_period.status='settled' + can_supplement 才显示)
        if db is not None:
            _cur_period_row = (
                db.query(CommissionPeriod)
                .filter(CommissionPeriod.id == _cur_period)
                .one_or_none()
            )
            _cur_period_status = _cur_period_row.status if _cur_period_row else "open"
        else:
            _cur_period_status = "open"
    else:
        _cur_period_status = "open"
    return f'''<div class="tree-view">
  <!-- ★ 2026-07-17 PR #52: 工具栏分两行布局 (信息行 + 操作行) — 解决 PR #51 单行太挤问题
       第 1 行: 树概览 + 本周 commission/PV 概览 + 结算按钮 (核心信息)
       第 2 行: 视图过滤器 + 折叠/展开/拖动提示 + 关闭 (次要操作) -->
  <div class="tree-view-toolbar">
    <div class="tv-toolbar-row">
      <span class="tv-stat">🪜 <b>5 叉网体</b></span>
      <span class="tv-toolbar-divider"></span>
      <span class="tv-stat"><b>{total_nodes}</b> 节点</span>
      <span class="tv-stat"><b>{total_avail}</b> avail</span>
      <span class="tv-stat tv-stat-hl"><b>{hl_count}</b> 待挂载</span>
      <span class="tv-spacer"></span>
      <!-- ★ 2026-07-17 PR #51: 本周 ISO 周 + commission/PV 概览 -->
      <span class="tv-stat">📅 本周 <b>{_html(_cur_period)}</b></span>
      <span class="tv-stat tv-stat-hl">💰 <b>${_cur_period_comm:.2f}</b></span>
      <span class="tv-stat">📥 <b>{_cur_period_pv_total}</b> PV</span>
      <span class="tv-spacer"></span>
      <!-- ★ 2026-07-20 PR #55: 工具栏按钮按 period 状态动态切文案
           - open: "💰 结算本周" (own + 7 代对等)
           - supplement: "🩹 补录上周" (own only, 对等链冻结, Mon 23:59 后失效)
           - closed: 按钮隐藏 -->
      {_settle_button_html(_cur_period, _cur_period_status, _cur_phase, _can_supp)}
      <!-- ★ 2026-07-27 PR #70: 下单管理按钮 (新业务: 库存 + 备货 + 单价表) -->
      <button type="button" class="tv-toolbar-btn-order" id="orderMgmtBtn"
              onclick="openOrderMgmtModal()" title="下单管理: 库存 + 备货 + 单价 (单按钮加载, 数据在 DB order_items 表)">
        📋 下单管理
      </button>
      <!-- ★ 2026-07-20 PR #56: 重置测试数据按钮 (二级警告, 删所有非 root + 全清 ledger + 全清 periods)
           目的: 反复测试时节点爆满, 一键回到初始状态 (root 保留) -->
      <button type="button" class="tv-toolbar-btn-reset" id="resetTestDataBtn"
              onclick="resetTestData(this)" title="重置测试数据: 删所有非 root 成员 + 全清 PV 流水 + 全清结算期, 保留 root (王常军) — ⚠️ 不可逆">
        🗑️ 重置
      </button>
    </div>
    <div class="tv-toolbar-row tv-toolbar-row-ops">
      <span class="tv-stat tv-stat-label">视图</span>
      <!-- ★ 2026-07-12 新增:节点显示过滤器 — 全部节点 vs 仅含用户节点
           切到「有用户的节点」时,所有 .tv-avail 占位节点通过 CSS 隐藏,SVG 重新 layout -->
      <select id="treeNodeFilter" class="tv-btn" onchange="treeViewFilterNodes(this.value)" title="选择显示范围:全部节点 vs 仅含真实成员的节点" style="cursor:pointer; padding-right:24px;">
        <option value="all" selected>全部节点</option>
        <option value="filled">仅含用户节点</option>
      </select>
      <!-- ★ 2026-07-14 v6: 槽位视图切换 — 全部槽位 vs 仅激活槽位
           业务规则「双轨制」: 默认 active=2 (L1+L2), L3-L5 显示为 locked 灰色
           - 全部槽位: 5 叉结构完整显示, locked 槽位灰底 + 🔒
           - 仅激活槽位: 隐藏 locked 槽位, 只显示 L1+L2 (业务运营视图) -->
      <select id="treeSlotView" class="tv-btn" onchange="treeViewSlotViewMode(this.value)" title="选择槽位显示模式: 仅激活槽位 vs 全部槽位" style="cursor:pointer; padding-right:24px;">
        <option value="active" selected>仅激活槽位</option>
        <option value="all">全部槽位</option>
      </select>
      <span class="tv-toolbar-divider"></span>
      <!-- ★ 2026-07-16 PR #23: 删掉紧凑模式总开关 (用户拍板: 紧凑模式折叠子表功能可以去掉) -->
      <button type="button" class="tv-btn" onclick="treeViewExpandAll(this)">全部展开</button>
      <button type="button" class="tv-btn" onclick="treeViewCollapseAll(this)">全部折叠</button>
      <span class="tv-spacer"></span>
      <!-- ★ 2026-07-12: 拖动改为「按住鼠标右键即拖」,无需按钮。保留按钮作为提示。
           toggleTreePanMode 在前端 no-op,仅设置 title 提示用户操作方式。 -->
      <span class="tv-stat tv-stat-hint">🖐 按住右键拖动</span>
      <button type="button" class="tv-btn tv-btn-close" onclick="closeTreeViewModal()">关闭 ✕</button>
    </div>
  </div>
  <div class="tree-view-body">
    <div class="tv-zoom-wrap" id="treeZoomWrap" style="--tv-zoom: 1;">
      {body}
    </div>
  </div>
  <!-- ★ 缩放控制(FAB 浮在模态右下角,始终可见;不随 body 滚动)
       transform 放在内层 .tv-root 而不是 wrap,wrapper box 由 JS 注入
       natural size × zoom,这样 body 滚动区 = visual 大小,完美对齐 -->
  <div class="tv-zoom-controls" aria-label="缩放控制">
    <button type="button" class="tv-zoom-btn" onclick="zoomTreeOut()" title="缩小 (Ctrl+-)" aria-label="缩小">−</button>
    <input type="range" id="treeZoomSlider" class="tv-zoom-slider"
           min="0.3" max="3" step="0.05" value="1"
           oninput="setZoomFromSlider(this.value)"
           title="拖动缩放 (30% - 300%)" aria-label="缩放滑块">
    <span class="tv-zoom-display" id="treeZoomDisplay" onclick="resetTreeZoom()" title="点击重置为 100% (Ctrl+0)">100%</span>
    <button type="button" class="tv-zoom-btn" onclick="zoomTreeIn()" title="放大 (Ctrl++)" aria-label="放大">+</button>
    <button type="button" class="tv-zoom-btn" onclick="fitTreeToScreen()" title="适应窗口 — 自动算最佳 zoom 把整树装下" aria-label="适应窗口">⤢</button>
  </div>
</div>'''


@app.post("/api/tree/render")
def api_tree_render(req: TreeRenderRequest, db: DbSession = Depends(get_db)):
    """★ 2026-07-16 PR #39: tree view 以 DB 为权威 — 从 members 表构建 tree dict

    之前 (PR #34/36/38):
      - 读 json/Tree_empty_5_3.json 拿 raw 树
      - 再从 DB 拉 name/orphan/direct_count 注入
      - 双重数据源, 不同步时显示 orphan 提示

    现在 (PR #39):
      - 单一数据源: DB members 表
      - 实时从 DB 构建完整 5 叉树 dict
      - avail 占位自动算 (real_children < maxLines 时补)
      - directCount 实时聚合 (PR #38)
      - depth / x_coord / locked 由渲染层算 (跟算法层共享)

    - committed=false: tree view + 用 highlights 标记本次即将挂载位置
    - committed=true:  tree view (没有 highlights 标记)
    - req.slot_view: "active" (默认,隐藏 locked) / "all" (显示所有槽位)
    """
    # ★ 2026-07-16 PR #23: 设置全局槽位显示模式 (单线程 FastAPI OK)
    global _SLOT_VIEW_SHOW_LOCKED
    _SLOT_VIEW_SHOW_LOCKED = (req.slot_view == "all")

    # ★ 2026-07-16 PR #39: 从 DB 构建 tree dict (DB 是权威)
    try:
        from database import SessionLocal as _SessionLocal
        with _SessionLocal() as _db:
            raw = _build_tree_from_db(_db)
    except Exception as _e:
        log.error(f"PR #39 _build_tree_from_db 失败: {_e}")
        raise HTTPException(500, f"从 DB 构建 tree 失败:{_e}")

    # ★ 2026-07-17 PR #51: 把 db 传给 _build_tree_render_html 算本期 commission/PV 概览
    #   用 Depends 注入的 db session 即可, 跟 _build_tree_from_db 用同一个 session
    _settle_db = db

    # 索引化 highlights: {parent_dist_id: {line_id: hl_info}}
    # ★ 2026-07-05 v3: 不过滤空 parent_dist_id 的 highlight
    #   即使父是模拟过程新建的节点(parent_dist_id = PREVIEW-N),也保留,
    #   后端 _tree_render_children 看到 PREVIEW- 前缀会动态插入虚拟子树
    highlight_map: Dict[str, Dict[int, Dict[str, Any]]] = {}
    member_dist_to_rank: Dict[str, int] = {}  # PREVIEW-N → rank(用于递归 children 渲染)
    if not req.committed:
        for h in req.highlights:
            if h.parent_line_id:
                hl_info = {
                    "name": h.name, "pv": h.pv, "rank": h.rank,
                    "member_dist_id": h.member_dist_id or "",
                }
                pdid = h.parent_dist_id or ""
                highlight_map.setdefault(pdid, {})[int(h.parent_line_id)] = hl_info
                if h.member_dist_id and h.member_dist_id.startswith("PREVIEW-"):
                    member_dist_to_rank[h.member_dist_id] = h.rank

    html = _build_tree_render_html(raw, highlight_map, preview_rank_map=member_dist_to_rank, db=_settle_db)
    return {
        "html": html,
        "root_name": raw.get("name") or "",
        "root_dist_id": raw.get("distId") or "",
        "committed": req.committed,
        "highlight_count": sum(len(v) for v in highlight_map.values()),
    }


# ============================================================
# 紧凑模式 — 节点「+挂入」按钮 stub endpoint
# ============================================================
# 2026-07-14 用户反馈 (Q1): 折叠子表里加「+挂入」按钮 → 点完直接挂入那个槽位
#
# 当前实现: STUB — 只 log + 返回 200 + 弹 toast, 不真正写 json/Tree_*.json
#   - 真实落盘需要: 读 json → 找槽位 → 插入 Node5 → 算 commission → 写盘
#   - 涉及 tree_lock / 数据完整性校验 / 事务回滚, 超出 200 行预算
#   - 后续单独做一个 PR 处理真实接通
#   - 现阶段用户能看完整 UI + 提交 → 弹「演示挂入成功」toast, 验证交互流
class TreeCommitSlotRequest(BaseModel):
    """紧凑表格「+挂入」按钮的提交请求"""
    parent_dist_id: str = Field("", description="父节点 distId (空串表示父是 root)")
    slot_index: int = Field(..., ge=1, le=9, description="在父节点的第几条线 (1..maxLines)")
    pv: int = Field(..., ge=0, description="新成员 PV")
    name: str = Field("", description="新成员姓名(可空)")
    skill: str = Field("skill_5_3", description="目标 skill, 用于选 json 文件")


# ============================================================
# ★ 2026-07-15 PR #14: 回归 PR #4 自动提升 (删除 3 个手动解锁 endpoints)
#   - /api/tree/toggle_lock    (鼠标点击 🔒 触发) — 撤销
#   - /api/tree/manual_unlocks (前端启动时拉取)  — 撤销
#   - /api/tree/clear_unlocks  (调试用)           — 撤销
#   - 渲染时 eff 完全靠 _compute_effective_active_from_json(根据 children 状态自动算)
# ============================================================




# ============================================================
# 主动释放锁
# ============================================================
# 用户拍板(2026-07-01):卡片右上角加「✕ 取消」按钮 → 调这个端点 → 服务端释放锁。
# 用途:用户预览后不想挂 / 选错了 / 浏览器快关 → 主动释放让别人/自己能立刻再预览。

class TreeReleaseLockRequest(BaseModel):
    """释放 Tree 锁(由前端「✕ 取消」按钮 或 管理员「强制释放」调用)

    两种模式:
        - 普通: 传 lock_id,服务端只释放匹配的(其他锁不动)
        - 强制: force=true,服务端释放当前任何锁(无需 lock_id)
    """
    lock_id: str = Field("", description="要释放的锁 id(普通模式必填,force 模式可空)")
    force: bool = Field(
        False,
        description="True=强制释放当前任何锁(管理员救场用,无 lock_id 也能用)",
    )


@app.post("/api/tree/release_lock")
def api_tree_release_lock(req: TreeReleaseLockRequest):
    """释放锁(2026-07-03 后支持多 skill 多锁)

    - 普通模式(force=false):
        - 在 _tree_locks 字典里找 lock_id 匹配的 skill 释放
        - 没找到 → 返回 {ok: False, reason}
    - 强制模式(force=true):
        - 释放所有 skill 的锁(不管是谁的,用于救"孤儿锁")
        - 返回被释放的 lock_id 列表
    """
    if req.force:
        # 管理员级: 强制释放所有 skill 的锁
        released_ids = _force_release_all_tree_locks()
        if released_ids:
            return {
                "ok": True,
                "force": True,
                "lock_ids": released_ids,
                "reason": "force-released",
            }
        return {"ok": True, "force": True, "reason": "no_lock"}

    if not req.lock_id:
        return {"ok": False, "reason": "lock_id is empty"}
    # 在 _tree_locks 字典里找匹配的锁
    matched_skill = _release_tree_lock_by_id(req.lock_id)
    if matched_skill:
        return {"ok": True, "lock_id": req.lock_id, "skill_id": matched_skill}
    # 没释放成功:可能是 id 错 / 已过期 / 根本没持锁(可能在别的 skill 下)
    return {
        "ok": False,
        "reason": "lock_id 不匹配或锁已被释放/过期",
        "active_locks": [
            {"skill_id": sid, "lock_id_prefix": lock._holder[:8] if lock._holder else None}
            for sid, lock in _tree_locks.items()
            if lock._holder
        ],
    }


# ============================================================
# 周 commission 结算 API (2026-07-14 v1) — PR-A 阶段
# ============================================================
# 4 个 endpoint:
#   GET  /api/period/current          — 当前期 (ISO 周编号)
#   GET  /api/period/list             — 列出所有期 (按时间倒序)
#   POST /api/period/{id}/settle      — 立即结算指定期
#   GET  /api/period/{id}/summary     — 查指定期结算结果 (未 settle 时返回 pending 状态)
#
# 暂不做的 (留 PR-B):
#   - /api/member/{dist_id}  查成员详情 (含 PV 余额历史)
#   - /api/period/{id}/ledger  查期所有 ledger 流水
#   - 自动 cron 结算 (依赖外部 scheduler)

from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import (
    Member, PVLedger, CommissionPeriod, OrderItem,
)
from repository import (
    MemberRepository, PVLedgerRepository, CommissionPeriodRepository,
)
from skills.period import (
    get_current_period_id, get_period_range, list_periods_in_range,
    PAIRING_BONUS_RATIOS, PAIRING_BONUS_MAX_DEPTH, COMMISSION_RATE,
    PAIRING_BONUS_4TH_USD_THRESHOLD, PAIRING_BONUS_5TH_USD_THRESHOLD,  # ★ PR #74
)
from skills.pair_commission import settle_period, get_or_create_period


@app.get("/api/period/current")
def api_period_current():
    """返回当前 ISO 周编号 + 范围 + 状态"""
    pid = get_current_period_id()
    start, end = get_period_range(pid)
    return {
        "period_id": pid,
        "start_at": start,
        "end_at": end,
        "start_iso": __import__("datetime").datetime.fromtimestamp(start).isoformat(),
        "end_iso": __import__("datetime").datetime.fromtimestamp(end).isoformat(),
    }


@app.get("/api/period/list")
def api_period_list(limit: int = 50, db: Session = Depends(get_db)):
    """列出所有结算期 (按 end_at DESC)

    ★ 2026-07-20 PR #55: 每个 period 加 phase 字段 (open / supplement / closed)
      - open: Sun-Fri 期间, 标准结算期
      - supplement: Sat-Mon 期间, 补录窗口 (只算 own_commission)
      - closed: Tue 起, 周期彻底结束
    """
    import time as _time
    repo = CommissionPeriodRepository(db)
    periods = repo.list_periods(limit=limit)
    now_ts = _time.time()
    items = []
    for p in periods:
        d = p.to_dict()
        # 算 phase
        from skills.period import get_period_phase, can_supplement
        try:
            d["phase"] = get_period_phase(p.id)
            d["can_supplement"] = can_supplement(p.id) and p.status == "settled"
        except ValueError:
            d["phase"] = "unknown"
            d["can_supplement"] = False
        items.append(d)
    return {
        "periods": items,
        "count": len(items),
        "now_ts": now_ts,
    }


@app.post("/api/period/{period_id}/settle")
def api_period_settle(
    period_id: str,
    supplement_only: bool = False,
    db: Session = Depends(get_db),
):
    """立即结算指定期 (admin/手动触发, 暂不接 cron)

    ★ 2026-07-20 PR #55:
      - supplement_only=False (默认): 主 settle (own + pairing, 算对等 7 代分润)
      - supplement_only=True: 补录 (只算 own_commission, 不动对等 7 代分润)
        业务规则: Sat-Mon 期间, 补基本 commission (对等链已冻结)

    Returns:
        结算结果:
          - total_commission / total_pv_consumed / total_pv_carried / member_count
          - members: 期间涉及的成员详情 [{dist_id, name, carry_out, commission, last_period_id}, ...]
            ★ PR #9 新增: 供前端结算卡展示每位成员的 carry/commission
            - 排序: 按 dist_id (稳定顺序)
            - commission = 该成员自己拿到的 (own + ancestor share) 总和
    """
    # 1. 确保 period 存在 (不存在就 init)
    get_or_create_period(period_id, db)
    db.commit()

    # 2. 跑结算
    try:
        result = settle_period(period_id, db, settled_by="manual", supplement_only=supplement_only)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # 3. ★ PR #9: 查每位成员的最终状态 (settle 后 DB 已更新)
    #    carry_out + 自己 commission + ancestor share = 该成员总 commission
    # ★ 2026-07-17 PR #53: 成员列表 union carry_out + commission + ancestor_share keys
    #   - 旧: 只列 carry_out 涉及的 (root 拿 commission 但 carry=0 会被漏掉)
    #   - 新: union 所有 3 个 set, root 也会显示 (commission $45 拿到)
    member_repo = MemberRepository(db)
    member_details: List[Dict[str, Any]] = []
    _involved_dists = set(result.carry_out_by_dist.keys()) | set(result.commission_by_dist.keys()) | set(result.ancestor_share_by_dist.keys())
    for dist_id in sorted(_involved_dists):
        m = member_repo.get_by_dist_id(dist_id)
        if m is None:
            continue
        # own commission + ancestor share (PR-A 期间已累加到 total_commission)
        own_comm = result.commission_by_dist.get(dist_id, 0.0)
        ancestor_share = result.ancestor_share_by_dist.get(dist_id, 0.0)
        total_comm = own_comm + ancestor_share
        member_details.append({
            "member_dist_id": dist_id,
            "member_name": m.member_name or "",
            "carry_out": int(m.current_pv_balance or 0),
            "own_commission": round(own_comm, 4),
            "ancestor_share": round(ancestor_share, 4),
            "total_commission": round(total_comm, 4),
            "savings": round(result.savings_by_dist.get(dist_id, 0.0), 4),  # ★ 2026-08-06 PR #73
            "savings_balance": round(m.savings_balance or 0.0, 4),  # ★ PR #73 累加后
            "last_period_id": m.last_period_id or "",
        })

    return {
        "period_id": result.period_id,
        "total_commission": round(result.total_commission, 4),
        "total_pv_consumed": result.total_pv_consumed,
        "total_pv_carried": sum(result.carry_out_by_dist.values()),
        # ★ 2026-08-06 PR #73: 储蓄奖金总额 (本期所有节点 savings 累加, USD)
        "total_savings": round(sum(result.savings_by_dist.values()), 4),
        "savings_count": len(result.savings_by_dist),
        "member_count": result.member_count,
        "pairs_log": result.pairs_log,
        # ★ PR #9: 期间成员详情
        "members": member_details,
    }


@app.get("/api/period/{period_id}/summary")
def api_period_summary(period_id: str, db: Session = Depends(get_db)):
    """查指定期结算结果 (未 settle 时返回 pending 状态)

    ★ PR #9 增强: 加上 members 列表 — 供前端展示当期所有成员
      (不论是否 settle, 都列出来)
    """
    period_repo = CommissionPeriodRepository(db)
    ledger_repo = PVLedgerRepository(db)
    member_repo = MemberRepository(db)

    p = period_repo.get(period_id)
    if not p:
        # 自动 init (open 状态)
        get_or_create_period(period_id, db)
        db.commit()
        p = period_repo.get(period_id)

    pending_count = ledger_repo.count_pending(period_id)
    total_member_count = member_repo.count()
    # ★ PR #9: 全部成员列表 (无论是否 settle)
    all_members = member_repo.list_all(limit=500)
    members_data = [
        {
            "member_dist_id": m.member_dist_id,
            "member_name": m.member_name or "",
            "current_pv_balance": m.current_pv_balance or 0,
            "total_commission": m.total_commission or 0.0,
            "savings_balance": m.savings_balance or 0.0,  # ★ 2026-08-06 PR #73
            "created_period_id": m.created_period_id or "",
            "last_period_id": m.last_period_id or "",
        }
        for m in all_members
    ]

    return {
        "period": p.to_dict(),
        "pending_ledger_count": pending_count,
        "total_member_count": total_member_count,
        # ★ PR #9: 成员列表
        "members": members_data,
    }


# ★ PR #65: 持续账单视图 — 列表显示各 member 当前期金额 + 结算前/后 PV
#   跟 /api/period/{id}/summary 区别:
#     - summary: 静态, 只显示 members 累计状态
#     - bill: 算 settle_period(dry_run=True) 拿本期 own_commission + ancestor_share
#       不管 period.status (open/settled/closed 都能算 preview)
#       用于前端"💰 结算本周佣金"持续账单视图
@app.get("/api/period/{period_id}/bill")
def api_period_bill(period_id: str, db: Session = Depends(get_db)):
    """查指定期账单 — 每 member 本期 PV / own / ancestor / carry_out

    ★ PR #65: 用 settle_period(dry_run=True) 算 preview, 不写 DB
    """
    from skills.pair_commission import settle_period

    period_repo = CommissionPeriodRepository(db)
    p = period_repo.get(period_id)
    if not p:
        # 自动 init (open 状态)
        get_or_create_period(period_id, db)
        db.commit()
        p = period_repo.get(period_id)

    # 跑 settle 算 preview (不写 DB, 任何 status 都能跑)
    try:
        result = settle_period(period_id, db, settled_by="preview", dry_run=True)
    except ValueError as e:
        # period_id 不存在等错误
        raise HTTPException(400, str(e))

    # ★ PR #65: 算本期 PV (从 ledger 聚合 status=pending + paired + carried)
    #   跟 dry_run 算法拿的 ledger 范围一致, 业务上 = "结算前 PV"
    from sqlalchemy import func as sqlfunc
    from models import PVLedger
    period_pv_rows = db.query(
        PVLedger.member_dist_id,
        sqlfunc.sum(PVLedger.pv_amount).label("total_pv")
    ).filter(
        PVLedger.period_id == period_id,
        PVLedger.status.in_(["pending", "paired", "carried"])
    ).group_by(PVLedger.member_dist_id).all()
    period_pv_by_dist = {row.member_dist_id: int(row.total_pv or 0) for row in period_pv_rows}

    # 拿所有 member
    member_repo = MemberRepository(db)
    all_members = member_repo.list_all(limit=500)
    member_details: List[Dict[str, Any]] = []
    for m in all_members:
        own_comm = result.commission_by_dist.get(m.member_dist_id, 0.0)
        ancestor_share = result.ancestor_share_by_dist.get(m.member_dist_id, 0.0)
        total_comm = own_comm + ancestor_share
        # carry_out: dry_run 算的是"如果现在 settle 应该 carry 多少"
        # 实际 DB 里 current_pv_balance 是上期 settle 完的, 不是本期
        # 我们用 dry_run 算的 carry_out 当"结算后剩余 PV"展示
        carry_out = result.carry_out_by_dist.get(m.member_dist_id, 0)
        member_details.append({
            "member_dist_id": m.member_dist_id,
            "member_name": m.member_name or "",
            "role": m.role or "consumer",
            "current_pv_balance": int(m.current_pv_balance or 0),  # 上期 settle 后剩余 PV
            "period_pv": period_pv_by_dist.get(m.member_dist_id, 0),  # ★ PR #65: 本期新增 PV
            "own_commission": round(own_comm, 4),
            "ancestor_share": round(ancestor_share, 4),
            "total_commission": round(total_comm, 4),
            "carry_out": int(carry_out),
        })

    return {
        "period": p.to_dict(),
        "members": member_details,
    }


# ★ PR #9 新增: 列出所有成员 + 余额
#   跟 /api/period/{id}/summary 里 members 字段同源, 但只列成员, 不带 period 信息
#   用途: 主页「成员账本」视图 (类似 officev2 后台)
#
# ★ PR #27 (2026-07-16) 加 4 个字段:
#   - parent_dist_id        : 父节点 distId (root 时为 "")
#   - slot_line_id          : 在父节点的第几条线 (1..maxLines)
#   - last_period_remaining_pv : 跟 current_pv_balance 同值, 改用业务语义名
#                                 (上周结算完后剩余的 PV)
#   - last_period_deducted_pv  : 上周结算时本成员被 paired 消耗的 PV 总和
#                                 (从 pv_ledger 聚合: status=paired AND period_id=last_period_id,
#                                  SUM(contribution_pv))
#   - 保留 current_pv_balance 字段, 跟 last_period_remaining_pv 同值, 向后兼容
@app.get("/api/members")
def api_members_list(limit: int = 200, db: Session = Depends(get_db)):
    """列出所有成员 + PV 余额 + 累计 commission + 父节点信息"""
    from sqlalchemy import select, func as sqlfunc

    member_repo = MemberRepository(db)
    members = member_repo.list_all(limit=limit)

    # 一次聚合: 所有成员在各自 last_period_id 的 paired contribution_pv 之和
    #   - 只算 status=paired (被配对消耗的; 不算 carried 跨期带的)
    #   - 没 last_period_id 的成员 → 0
    deducted_map: Dict[str, int] = {}
    if members:
        paired_stmt = (
            select(
                PVLedger.member_dist_id,
                PVLedger.period_id,
                sqlfunc.coalesce(sqlfunc.sum(PVLedger.contribution_pv), 0).label("deducted"),
            )
            .where(PVLedger.status == "paired")
            .group_by(PVLedger.member_dist_id, PVLedger.period_id)
        )
        for row in db.execute(paired_stmt).all():
            # (member_dist_id, period_id) -> deducted
            deducted_map[(row.member_dist_id, row.period_id)] = int(row.deducted or 0)

    # ★ PR #38: 直推人数 (实时聚合, 不存 DB)
    direct_count_map = _compute_direct_count_map(db)

    return {
        "count": len(members),
        "members": [
            {
                "member_dist_id": m.member_dist_id,
                "member_name": m.member_name or "",
                "parent_dist_id": m.parent_dist_id or "",
                "slot_line_id": m.slot_line_id,
                "current_pv_balance": m.current_pv_balance or 0,
                # ★ PR #27 业务语义字段名 (跟 current_pv_balance 同值)
                "last_period_remaining_pv": m.current_pv_balance or 0,
                # ★ PR #27 上周结算时被 paired 消耗的 PV (从 pv_ledger 聚合)
                "last_period_deducted_pv": deducted_map.get(
                    (m.member_dist_id, m.last_period_id or ""), 0
                ),
                # ★ PR #38: 直推人数 (DB members.parent_dist_id 聚合)
                "direct_count": direct_count_map.get(m.member_dist_id, 0),
                "total_commission": m.total_commission or 0.0,
                "savings_balance": m.savings_balance or 0.0,  # ★ 2026-08-06 PR #73
                "role": _normalize_role(getattr(m, "role", None)),
                "business_level": _normalize_business_level(getattr(m, "business_level", None)),  # ★ PR #75
                "created_period_id": m.created_period_id or "",
                "last_period_id": m.last_period_id or "",
                # ★ 2026-07-16 PR #41: 角色 (消费股东/预备合伙人/合伙人员工/初级管理/中级管理/高级管理/Inactive)
                "role": _normalize_role(getattr(m, "role", None)),
            }
            for m in members
        ],
    }


# ============================================================
# PR #31: DB Admin API — 列表/查/改 业务表数据
# ============================================================
# 用途: 提供前端 DB 管理界面用, 让 user 能直接看到表 + 编辑
# 安全: 白名单 (只允许业务表), 主键不能改, 防 SQL 注入用 SQLAlchemy text + bind params
#
# 业务表白名单 (跟业务直接相关):
#   - members: 网体成员
#   - pv_ledger: PV 流水
#   - commission_periods: 结算期
# 不在白名单 (chat 跟 migrations, 跟业务无关, 跳过):
#   - sessions / messages: chat 历史
#   - alembic_version: migrations
from sqlalchemy import text, inspect as sa_inspect

_DB_ADMIN_ALLOWED = frozenset({"members", "pv_ledger", "commission_periods"})


def _db_admin_inspector(db: Session):
    """拿 SQLAlchemy inspector, 跟 bind 解耦"""
    return sa_inspect(db.bind)


def _db_admin_columns(insp, name: str):
    """列元数据: [{name, type(str), nullable, default}]"""
    return [
        {
            "name": c["name"],
            "type": str(c["type"]),
            "nullable": c.get("nullable", True),
            "default": str(c.get("default")) if c.get("default") is not None else None,
        }
        for c in insp.get_columns(name)
    ]


def _db_admin_coerce(value, col_type):
    """按 column type 强转 value (前端传 string 过来, DB 要 native type)

    - INT/INTEGER: int(value) or None
    - FLOAT/REAL/NUMERIC: float(value) or None; ★ PR #49 也接受 datetime 字符串 ("2024-01-15 14:30:00")
    - BOOL/BOOLEAN: bool(value) (前端 'true'/'false' 也能 parse)
    - 其他 (STRING/TEXT/DATETIME): 保持原样
    """
    if value is None or value == "":
        return None
    t = str(col_type).upper() if col_type is not None else ""
    try:
        if "INT" in t:
            return int(value)
        if "FLOAT" in t or "REAL" in t or "NUMERIC" in t or "DECIMAL" in t:
            # ★ 2026-07-16 PR #49: DB admin UI (PR #48) 把 *_at 列格式化成 "YYYY-MM-DD HH:MM:SS"
            #   前端编辑后发回 string, 这里尝试先解析 datetime 再转 timestamp
            #   - 支持 "YYYY-MM-DD HH:MM:SS" / "YYYY-MM-DDTHH:MM:SS" / "YYYY-MM-DD" 三种格式
            #   - 解析失败再 fallback 到 float(value) (允许直接编辑 Unix timestamp)
            if isinstance(value, str):
                import re as _re
                from datetime import datetime as _dt
                _s = value.strip()
                _m = _re.match(
                    r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?)?$",
                    _s,
                )
                if _m:
                    _fmt = "%Y-%m-%d %H:%M:%S" if _m.group(4) else "%Y-%m-%d"
                    try:
                        return _dt.strptime(_s, _fmt).timestamp()
                    except ValueError:
                        pass  # 日期不合法, fall through 到 float()
            return float(value)
        if "BOOL" in t:
            if isinstance(value, bool):
                return value
            return str(value).lower() in ("true", "1", "yes", "on")
        return value
    except (ValueError, TypeError):
        return value  # 转换失败保持原样, 让 DB 报错


@app.get("/api/admin/tables")
def api_admin_tables(db: Session = Depends(get_db)):
    """列出所有业务表 + columns + row count"""
    insp = _db_admin_inspector(db)
    all_tables = sorted(insp.get_table_names())
    tables = []
    for name in all_tables:
        if name not in _DB_ADMIN_ALLOWED:
            continue
        pk = insp.get_pk_constraint(name).get("constrained_columns", []) or []
        try:
            row_count = db.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar() or 0
        except Exception:
            row_count = -1
        tables.append({
            "name": name,
            "row_count": int(row_count),
            "columns": _db_admin_columns(insp, name),
            "primary_key": list(pk),
        })
    return {"tables": tables, "count": len(tables)}


@app.get("/api/admin/tables/{name}")
def api_admin_table_data(
    name: str,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """查表数据 (limit 默认 100, 上限 500)"""
    insp = _db_admin_inspector(db)
    if name not in insp.get_table_names():
        raise HTTPException(404, f"表 {name} 不存在")
    if name not in _DB_ADMIN_ALLOWED:
        raise HTTPException(403, f"表 {name} 不在白名单 (允许: {sorted(_DB_ADMIN_ALLOWED)})")
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    cols = _db_admin_columns(insp, name)
    pk = insp.get_pk_constraint(name).get("constrained_columns", []) or ["id"]
    pk_col = pk[0]
    # 查数据 (按主键排序, 确定性)
    result = db.execute(
        text(f"SELECT * FROM {name} ORDER BY {pk_col} LIMIT :limit OFFSET :offset"),
        {"limit": limit, "offset": offset},
    )
    rows = [dict(r._mapping) for r in result]
    # 全表行数
    total = db.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar() or 0
    return {
        "name": name,
        "columns": cols,
        "primary_key": list(pk),
        "rows": rows,
        "row_count": int(total),
        "limit": limit,
        "offset": offset,
    }


@app.put("/api/admin/tables/{name}/rows/{pk_value}")
def api_admin_table_update_row(
    name: str,
    pk_value: str,
    body: Dict[str, Any],
    db: Session = Depends(get_db),
):
    """更新一行 (主键定位, 不允许改主键)

    - body: {col1: newValue, col2: newValue, ...}
    - 返回: {updated, table, pk, pk_value, fields_changed}
    """
    insp = _db_admin_inspector(db)
    if name not in insp.get_table_names():
        raise HTTPException(404, f"表 {name} 不存在")
    if name not in _DB_ADMIN_ALLOWED:
        raise HTTPException(403, f"表 {name} 不在白名单")
    pk = insp.get_pk_constraint(name).get("constrained_columns", []) or ["id"]
    pk_col = pk[0]
    cols_by_name = {c["name"]: c for c in insp.get_columns(name)}
    # 不允许改主键
    if pk_col in body:
        body.pop(pk_col)
    if not body:
        raise HTTPException(400, "body 为空 (主键不能改)")
    # 强转 + 构造 SET
    set_clauses = []
    set_clauses_keys = []
    params: Dict[str, Any] = {}
    for k, v in body.items():
        if k not in cols_by_name:
            continue  # 未知列忽略 (前端可能多传)
        coerced = _db_admin_coerce(v, cols_by_name[k]["type"])
        set_clauses.append(f"{k} = :{k}")
        set_clauses_keys.append(k)
        params[k] = coerced
    if not set_clauses:
        raise HTTPException(400, "没有可更新字段 (未知列被忽略)")
    params["pk_value"] = pk_value
    sql = f"UPDATE {name} SET {', '.join(set_clauses)} WHERE {pk_col} = :pk_value"
    try:
        result = db.execute(text(sql), params)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"更新失败: {e}")
    if result.rowcount == 0:
        # 主键找不到
        raise HTTPException(404, f"{name} 里找不到主键 {pk_col}={pk_value}")
    return {
        "updated": int(result.rowcount),
        "table": name,
        "pk": pk_col,
        "pk_value": pk_value,
        "fields_changed": [k for k in set_clauses_keys],
    }


@app.delete("/api/admin/tables/{name}/rows/{pk_value}")
def api_admin_table_delete_row(
    name: str,
    pk_value: str,
    db: Session = Depends(get_db),
):
    """★ 2026-07-16 PR #47: 删除一行 (主键定位)

    - 白名单校验 (跟 PUT 一致): 仅 members / pv_ledger / commission_periods 可删
    - 主键找不到 → 404
    - ON DELETE CASCADE: 删 member 会自动清相关 PVLedger 行 (SQLite FK 强制, 见 models.py L257)
    - 返回: {deleted, table, pk, pk_value}

    使用场景: DB admin UI 表格每行 🗑️ 按钮, 确认后调这个端点
    """
    insp = _db_admin_inspector(db)
    if name not in insp.get_table_names():
        raise HTTPException(404, f"表 {name} 不存在")
    if name not in _DB_ADMIN_ALLOWED:
        raise HTTPException(403, f"表 {name} 不在白名单, 不允许删除")
    pk = insp.get_pk_constraint(name).get("constrained_columns", []) or ["id"]
    pk_col = pk[0]
    # 强转 pk_value (主键可能是 int, 但 URL 传的是 string)
    pk_col_meta = next((c for c in insp.get_columns(name) if c["name"] == pk_col), None)
    if pk_col_meta:
        pk_value_coerced = _db_admin_coerce(pk_value, pk_col_meta["type"])
    else:
        pk_value_coerced = pk_value
    sql = f"DELETE FROM {name} WHERE {pk_col} = :pk_value"
    try:
        result = db.execute(text(sql), {"pk_value": pk_value_coerced})
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"删除失败: {e}")
    if result.rowcount == 0:
        raise HTTPException(404, f"{name} 里找不到主键 {pk_col}={pk_value}")
    return {
        "deleted": int(result.rowcount),
        "table": name,
        "pk": pk_col,
        "pk_value": pk_value,
    }


# ============================================================
# ★ 2026-07-20 PR #56: 批量重置测试数据
#   - 目的: 用户反复测试 (加新成员 → 算 commission → 重置), 节点太多难算清
#   - 行为: 删所有非 root members + 全清 pv_ledger + 全清 commission_periods
#           保留 root 成员, 重新 init 当前 commission_period
#   - UI 入口: toolbar "🗑️ 重置测试数据" 按钮 + 二次确认弹窗
#   - 保护: root 永远保留 (即使 DB 异常找不到, 也会重建)
# ============================================================
@app.post("/api/admin/reset_test_data")
def api_admin_reset_test_data(
    confirm: bool = False,
    db: Session = Depends(get_db),
):
    """批量重置测试数据 (清非 root members + 全清 pv_ledger + 全清 commission_periods)

    ★ 2026-07-20 PR #56 新增 (用户 2026-07-20 反馈: "节点加太多了很难算清楚, 帮我加个批量删除")
    业务场景: 测试期间反复加成员试算法, 节点爆满, 一次性重置
    保护机制:
      - confirm=True 才执行 (默认 False, 防误操作)
      - root 永远保留 (parent_dist_id=NULL + slot_line_id=0)
      - 即使 root 不存在 (DB 异常), 也会用 init_root_member 重建
      - 删除顺序: pv_ledger (有 FK) → members (除 root) → commission_periods (最后)
    Returns:
      {ok, deleted: {members, pv_ledger, commission_periods}, root_preserved: bool, current_period_id}
    Raises:
        400: confirm=False 拒绝执行
    """
    if not confirm:
        raise HTTPException(
            400,
            "需要 confirm=true 确认重置操作 (防止误点 UI 按钮删光数据)"
        )

    member_repo = MemberRepository(db)
    ledger_repo = PVLedgerRepository(db)
    period_repo = CommissionPeriodRepository(db)

    # 1. 找 root (parent_dist_id IS NULL + slot_line_id IS NULL/0)
    from sqlalchemy import select as _sa_select
    root_member = db.execute(
        _sa_select(Member).where(
            Member.parent_dist_id.is_(None),
            Member.slot_line_id.is_(None) | (Member.slot_line_id == 0),
        ).limit(1)
    ).scalar_one_or_none()

    # 2. 统计要删的 (返回给 UI 显示)
    stats = {
        "members": 0,
        "pv_ledger": 0,
        "commission_periods": 0,
    }

    # 3. 先清 pv_ledger (有 FK 引用 members, 必须先清)
    #    ★ 注意: 不要按 member_dist_id IN (非 root) 过滤, 一刀切全清
    #       因为 root 的 ledger 也可能存在 (旧测试残留, 不会影响重置)
    pre_ledger_count = db.query(PVLedger).count()
    db.query(PVLedger).delete()
    stats["pv_ledger"] = pre_ledger_count

    # 4. 删非 root members + 重置 root 字段
    #    ★ 业务规则: 重置 = "回到 DB 刚建好的状态"
    #      - root 保留 (不能删, 树根)
    #      - root 的 carry / commission / last_period_id 全部清空
    #      - root 的 created_period_id 保留 (历史信息, 不重置)
    if root_member is not None:
        pre_members_count = db.query(Member).count()
        # 重置 root 字段
        root_member.current_pv_balance = 0
        root_member.total_commission = 0.0
        root_member.last_period_id = None
        # 删非 root
        db.query(Member).filter(Member.id != root_member.id).delete()
        stats["members"] = pre_members_count - 1  # 减去 root
        root_preserved = True
    else:
        # root 不存在 (DB 异常), 全删然后重建
        pre_members_count = db.query(Member).count()
        db.query(Member).delete()
        stats["members"] = pre_members_count
        root_preserved = False

    # 5. 清 commission_periods
    pre_periods_count = db.query(CommissionPeriod).count()
    db.query(CommissionPeriod).delete()
    stats["commission_periods"] = pre_periods_count

    db.commit()

    # 6. 重建 root (如果之前没找到)
    if not root_preserved:
        from models import Member as _Member
        root = _Member(
            member_dist_id="N5637590.1",
            member_name="王常军",
            parent_dist_id=None,
            slot_line_id=0,
            max_lines=5,
            current_pv_balance=0,
            total_commission=0.0,
            created_period_id="2025-12-28_W01",  # 业务 W1 开始日 (新格式)
            last_period_id=None,
        )
        db.add(root)
        log.warning("⚠️ reset_test_data: root 不存在, 已自动重建")

    # 7. 重建当前 commission_period (给 UI toolbar 显示用)
    from skills.period import get_current_period_id
    current_pid = get_current_period_id()
    from skills.pair_commission import get_or_create_period
    get_or_create_period(current_pid, db)
    db.commit()

    log.info(
        f"🧹 reset_test_data: deleted {stats['members']} members, "
        f"{stats['pv_ledger']} pv_ledger, {stats['commission_periods']} commission_periods, "
        f"root_preserved={root_preserved}"
    )

    return {
        "ok": True,
        "deleted": stats,
        "root_preserved": root_preserved,
        "current_period_id": current_pid,
    }


# ============================================================
# ★ 2026-07-27 PR #70: 下单管理 (order_items)
#   - 用户 2026-07-27 反馈: "增加一个下单管理按钮, 里面是一张表, 显示库存 / 准备下单 / 单价"
#   - 业务规则 (PR #70 拍板):
#     - 单品差额 = 当前库存 - 需求总数 (前端实时算, 不存)
#     - 总金额 = 套组 × 套组价格 (前端实时算, 不存)
#     - 合计 = SUM(总金额) (前端算)
#     - 需求增加时, 当前库存自动按差量减少 (用户拍板: 需求增加则库存减少)
#     - 显式「保存」按钮 (用户拍板: 不自动存, 改完手动点保存)
# ============================================================
class OrderItemUpdate(BaseModel):
    """下单管理单条更新"""
    id: int = Field(..., description="order_items.id")
    required_qty: Optional[int] = Field(None, ge=0, description="需求总数")
    current_stock: Optional[int] = Field(None, ge=0, description="当前库存")
    package_count: Optional[int] = Field(None, ge=0, description="套组")
    package_price: Optional[float] = Field(None, ge=0, description="套组价格")


class OrderItemBulkUpdateRequest(BaseModel):
    """下单管理批量更新请求"""
    items: List[OrderItemUpdate] = Field(..., min_length=1, description="要更新的行")


# ★ 2026-07-27 PR #70: 8 个 sample 产品 (用户截图)
_ORDER_ITEMS_SAMPLE = [
    # (name, unit, required_qty, current_stock, package_count, package_price, sort_order)
    ("活性辅酶", "瓶", 18, 17, 1, 1335.0, 0),
    ("辅酶奥米加", "瓶", 15, 0, 5, 1129.0, 1),
    ("钙镁健骨", "瓶", 27, 1, 9, 820.0, 2),
    ("葡萄籽", "瓶", 26, 0, 9, 899.0, 3),
    ("超级水果素", "瓶", 2, 0, 1, 1290.0, 4),
    ("健儿素", "瓶", 13, 0, 5, 766.0, 5),
    ("田园果蔬饮", "袋", 11, 0, 4, 1248.0, 6),
    ("日夜纤", "套", 3, 0, 1, 2599.0, 7),
]


def _ensure_order_items_seeded(db) -> int:
    """幂等 seed 8 个 sample 产品 (PR #70 拍板)
    - 如果表为空, 插入 sample 数据
    - 如果表非空, 跳过 (用户可能已编辑)
    - 返: 插入的行数 (0 = 跳过, 8 = seed 成功)
    """
    if db.query(OrderItem).count() > 0:
        return 0
    for name, unit, req, stock, pkg, price, sort_o in _ORDER_ITEMS_SAMPLE:
        db.add(OrderItem(
            name=name, unit=unit, required_qty=req, current_stock=stock,
            package_count=pkg, package_price=price, sort_order=sort_o,
        ))
    db.commit()
    log.info(f"📦 order_items seed: 插入 {len(_ORDER_ITEMS_SAMPLE)} 个 sample 产品")
    return len(_ORDER_ITEMS_SAMPLE)


@app.get("/api/orders/items")
def api_orders_items_list(db: Session = Depends(get_db)):
    """列出所有下单管理条目 (按 sort_order 排序)

    ★ 2026-07-27 PR #70: 下单管理
    - 返: items list (按 sort_order, id 升序)
    - 单品差额 (unit_diff) + 总金额 (total) 都是实时算的, 不存 DB
    """
    _ensure_order_items_seeded(db)
    items = db.query(OrderItem).order_by(OrderItem.sort_order, OrderItem.id).all()
    return {
        "items": [
            {**it.to_dict(),
             "unit_diff": it.current_stock - it.required_qty,
             "total": it.package_count * it.package_price}
            for it in items
        ],
        "count": len(items),
    }


@app.patch("/api/orders/items/bulk")
def api_orders_items_bulk_update(
    req: OrderItemBulkUpdateRequest,
    db: Session = Depends(get_db),
):
    """批量更新下单管理条目 (前端「保存」按钮一次提交所有改过的行)

    ★ 2026-07-27 PR #70: 用户拍板显式「保存」按钮, 一次 PATCH 所有改过的行
    - body: {items: [{id, required_qty?, current_stock?, package_count?, package_price?}, ...]}
    - 每个 item 只更新提供的字段 (None 跳过)
    - 返: 实际更新的行数 + 各自最新值 (前端刷新表格)
    """
    if not req.items:
        raise HTTPException(400, "items 不能为空")

    updated = []
    for upd in req.items:
        item = db.query(OrderItem).filter(OrderItem.id == upd.id).first()
        if item is None:
            raise HTTPException(404, f"找不到 order_item id={upd.id}")
        if upd.required_qty is not None:
            item.required_qty = int(upd.required_qty)
        if upd.current_stock is not None:
            item.current_stock = int(upd.current_stock)
        if upd.package_count is not None:
            item.package_count = int(upd.package_count)
        if upd.package_price is not None:
            item.package_price = float(upd.package_price)
        # SQLAlchemy onupdate= 会自动更新 updated_at
        updated.append(item)

    db.commit()
    log.info(f"📦 order_items bulk update: 改 {len(updated)} 行")
    return {
        "ok": True,
        "updated_count": len(updated),
        "items": [
            {**it.to_dict(),
             "unit_diff": it.current_stock - it.required_qty,
             "total": it.package_count * it.package_price}
            for it in updated
        ],
    }


# ============================================================
# ★ 2026-07-16 PR #41: 改 member.role 专用 endpoint (/role 命令用)
#   - body: {member_dist_id, role}
#   - 比 PUT /api/admin/tables/members/rows/{id} 更直白, 前端 /role 命令不用走 admin
# ============================================================
class MemberRoleRequest(BaseModel):
    member_dist_id: str = Field(..., description="目标成员 distId")
    role: str = Field(..., description=f"新角色, 可选: {sorted(VALID_ROLES)}")


@app.post("/api/members/role")
def api_member_role_update(
    req: MemberRoleRequest,
    db: DbSession = Depends(get_db),
):
    """改一个 member 的 role 字段 (供 /role 命令 + DB admin 共用)"""
    new_role = _normalize_role(req.role)
    member = db.query(Member).filter_by(member_dist_id=req.member_dist_id).first()
    if member is None:
        raise HTTPException(404, f"找不到 distId={req.member_dist_id} 的成员")
    old_role = _normalize_role(getattr(member, "role", None))
    member.role = new_role
    db.commit()
    log.info(f"🎭 member role 变更: {req.member_dist_id} {old_role} → {new_role}")
    return {
        "ok": True,
        "member_dist_id": req.member_dist_id,
        "member_name": member.member_name or "",
        "old_role": old_role,
        "new_role": new_role,
        # ★ 2026-07-16 PR #42: role_label 跟 new_role 一样 (DB 存全名), 保留字段兼容旧前端
        "role_label": new_role,
    }


# ★ 2026-08-06 PR #75: 改 member.business_level 专用 endpoint (跟 role 独立)
#   - body: {member_dist_id, business_level}
#   - 跟 /api/members/role 平行, 4 档位独立列
#   - 业务定位: 业务档位 (激活/商务/精英/至尊) 跟 role 字段独立
# ============================================================
class MemberBusinessLevelRequest(BaseModel):
    member_dist_id: str = Field(..., description="目标成员 distId")
    business_level: str = Field(..., description=f"新业务档位, 可选: {sorted(VALID_BUSINESS_LEVELS)}")


@app.post("/api/members/business_level")
def api_member_business_level_update(
    req: MemberBusinessLevelRequest,
    db: DbSession = Depends(get_db),
):
    """★ 2026-08-06 PR #75: 改一个 member 的 business_level 字段 (4 档位独立列)"""
    new_level = _normalize_business_level(req.business_level)
    member = db.query(Member).filter_by(member_dist_id=req.member_dist_id).first()
    if member is None:
        raise HTTPException(404, f"找不到 distId={req.member_dist_id} 的成员")
    old_level = _normalize_business_level(getattr(member, "business_level", None))
    member.business_level = new_level
    db.commit()
    log.info(f"💎 member business_level 变更: {req.member_dist_id} {old_level} → {new_level}")
    return {
        "ok": True,
        "member_dist_id": req.member_dist_id,
        "member_name": member.member_name or "",
        "old_business_level": old_level,
        "new_business_level": new_level,
    }


@app.get("/api/members/business_levels")
def api_member_business_levels_list():
    """★ 2026-08-06 PR #75: 列所有可用业务档位 (供下拉 + DB admin 用)"""
    return {
        "business_levels": [
            {
                "key": k,
                "label": k,
                "bg": v["bg"],
                "fg": v["fg"],
                "tier_pv": v["tier_pv"],
            }
            for k, v in MEMBER_BUSINESS_LEVELS.items()
        ],
        "default": DEFAULT_BUSINESS_LEVEL,
    }


@app.get("/api/members/roles")
def api_member_roles_list():
    """列所有可用角色 (供 /role 命令下拉 + DB admin 用)"""
    # ★ 2026-07-16 PR #42: role 字段 = label (key), 直接返
    return {
        "roles": [
            {"key": k, "label": k, "bg": v["bg"], "fg": v["fg"]}
            for k, v in MEMBER_ROLES.items()
        ],
        "default": DEFAULT_ROLE,
    }


# ============================================================
# ★ 2026-08-05: 给已有成员追加本期 PV (/api/members/add_pv)
#   业务背景: 原版网体 (original_tree_nodes, 264 节点) 迁入 members 后,
#   所有成员 current_pv_balance=0, 本期 PV 需要逐个补录 — 这个端点给
#   任意已有成员追加一条 pending PVLedger (跟新成员挂入的 PV 写法一致),
#   不动 current_pv_balance (结算时才落账)
# ============================================================
class MemberAddPvRequest(BaseModel):
    member_dist_id: str = Field(..., description="目标成员 distId")
    pv_amount: int = Field(..., gt=0, description="追加的本期 PV (正整数)")
    note: Optional[str] = Field(None, description="备注 (可选)")


@app.post("/api/members/add_pv")
def api_member_add_pv(
    req: MemberAddPvRequest,
    db: DbSession = Depends(get_db),
):
    """给已有成员追加本期 PV (pending ledger, 不动 current_pv_balance)"""
    member = db.query(Member).filter_by(member_dist_id=req.member_dist_id).first()
    if member is None:
        raise HTTPException(404, f"找不到 distId={req.member_dist_id} 的成员")
    period_id = get_current_period_id()
    ledger = PVLedger(
        member_id=member.id,
        member_dist_id=member.member_dist_id,
        period_id=period_id,
        pv_amount=int(req.pv_amount),
        status="pending",
        note=req.note,
    )
    db.add(ledger)
    db.commit()
    db.refresh(ledger)
    log.info(f"➕ member add_pv: {req.member_dist_id} +{req.pv_amount} PV (period={period_id})")
    return {
        "ok": True,
        "member_dist_id": member.member_dist_id,
        "member_name": member.member_name or "",
        "period_id": period_id,
        "pv_amount": int(req.pv_amount),
        "ledger_id": ledger.id,
    }


# ============== 启动 ==============

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=False)

# ★ 2026-08-07 P1 PR3 Task 4: 接入 scenario_routes 3 个 HTTP 路由
#   - 业务: 客户路演实时调参, 调 POST /api/scenarios 建场景, GET state/overview 查报酬
#   - 不改 main.py 其他代码, 只加 include_router
import scenario_routes  # noqa: E402
app.include_router(scenario_routes.router)
