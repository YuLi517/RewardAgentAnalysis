# -*- coding: utf-8 -*-
"""Skill 5 内部辅助函数(2026-07-13 抽出)

历史背景
--------
- 原 skills/skill_5_1.py 里有 7 个 helper,被 skill_5_3 直接 `from skill_5_1 import (...)` 调用
- 2026-07-13 下线 skill_5_1 / skill_5_2(业务侧改走 skill_5_3 alone)
- 但 skill_5_3 仍然需要这些 helper(Node5 树加载 / 利润快照 / 祖先链 / 步骤快照)
- 故抽出到这里:`skill_5_helpers.py` — 仅供 skill_5_3 + main.py 内部使用,不是公开 skill
- 不出现在前端 / slash command / TREE_PATHS / _skill_runners 任何地方

对外接口
--------
- `AdditionStep`            : dataclass, simulate_addition 的步骤结构(已含 to_dict)
- `_bfs_all(node)`          : BFS 遍历整树
- `_snapshot_profit(tree, include_pairing)` : 返回 {basic, pairing, total} 快照
- `_ancestor_chain(root, target, dist_id_map)` : root → target 的路径链 dict
- `load_from_jstree_dict(d, ...)` : officev2 jstree dict 递归转 Node5
- `load_tree_from_jstree_file(path)` : 加载 jstree JSON + uid→distId 反向索引
- `history_to_json(history, indent)` : simulate_addition 结果 JSON 序列化
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from skill_5_lib import (
    Node5,
    basic_commission,
    pairing_bonus,
    total_basic,
)


# ===========================================================================
# 1. BFS 遍历
# ===========================================================================

def _bfs_all(node: Node5) -> List[Node5]:
    """BFS 遍历整树, 返回节点列表(顺序: root → L1 → L2 → ...)

    与 skill_5_lib 的 BFS 语义一致: 层内按 children 数组顺序 = 业务 L1..L5 顺序,
    而 node.uid 升序是在「列优先 BFS」填充下天然一致;新合成成员总是 append 到末尾。
    """
    result: List[Node5] = []
    queue: List[Node5] = [node]
    while queue:
        cur = queue.pop(0)
        result.append(cur)
        queue.extend(cur.children)
    return result


# ===========================================================================
# 2. 利润快照
# ===========================================================================

def _snapshot_profit(tree: Node5, include_pairing: bool) -> Dict[str, float]:
    """取整树当前利润快照, 返回 {basic, pairing, total}"""
    b = total_basic(tree)
    p = pairing_bonus(tree) if include_pairing else 0.0
    return {"basic": b, "pairing": p, "total": b + p}


# ===========================================================================
# 3. AdditionStep 步骤结构
# ===========================================================================

@dataclass
class AdditionStep:
    """simulate_addition 每一步的状态(可 .to_dict() 给前端 / Agent 渲染)

    Fields
    ------
    step : int
        步骤序号(1-based)
    uid  : int
        新成员 uid
    pv   : int
        新成员 PV

    parent_basic_before : float
        父节点挂入前的 basic_commission
    parent_basic_after  : float
        父节点挂入后的 basic_commission(用于在 chat 里看父节点自身涨幅)

    basic_before  : float    # 整树 basic(挂入前)
    basic_after   : float    # 整树 basic(挂入后)
    pairing_before: float    # 整树 pairing(挂入前)
    pairing_after : float    # 整树 pairing(挂入后)
    total_before  : float    # 整树 total = basic + pairing(挂入前)
    total_after   : float    # 整树 total(挂入后)

    lift_basic   : float     # 整树增量 basic 涨幅
    lift_pairing : float     # 整树增量 pairing 涨幅
    lift_total   : float     # 整树增量 total 涨幅
    lift_pct     : Optional[float]   # 整树涨幅百分比;total_before=0 时返回 None(避免除零)

    name : str = ""          # 新成员姓名(从 req.members[].name 透传,缺省空串)
    parent_uid : int = 0     # 父节点 uid
    parent_dist_id : str = ""    # 父节点 officev2 distId(highlight 按这个 key)
    ancestor_chain : List[Dict[str, Any]] = field(default_factory=list)  # 完整路径
    member_dist_id : str = ""     # 新成员自己的 distId(PREVIEW-N 或 officev2)
    """

    step: int
    uid: int
    pv: int

    parent_basic_before: float
    parent_basic_after: float

    basic_before: float
    basic_after: float
    pairing_before: float
    pairing_after: float
    total_before: float
    total_after: float

    lift_basic: float
    lift_pairing: float
    lift_total: float
    lift_pct: Optional[float]

    name: str = ""
    parent_uid: int = 0
    parent_dist_id: str = ""
    ancestor_chain: List[Dict[str, Any]] = field(default_factory=list)
    member_dist_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ===========================================================================
# 4. jstree dict 加载 + 文件加载
# ===========================================================================

def load_from_jstree_dict(
    d: Dict[str, Any],
    depth: int = 0,
    line_id: int = 0,
    max_uid: Optional[List[int]] = None,
    uid_to_dist_id_out: Optional[Dict[int, str]] = None,
) -> Node5:
    """把 officev2 风格的 `distId/name/maxLines/level/parentLineId/available`
    jstree dict 递归转成 `Node5` 实例,并填好 uid / is_avail / line_id。

    字段映射
    --------
    - `distId` → uid(去掉 N 前缀再 int 转换;兼容 "N5637590.1" / "N-5637591" / "N-7xxxxxx")
    - `name`   → name
    - `pv`     → pv(int 转换, None/空 → 0)
    - `maxLines` → max_children(默认 5)
    - `available` → is_avail
    - `parentLineId` → line_id(根节点为 0)
    - `level` → (用于 depth 计算)depth = level - 1

    边角
    ----
    - `available=true`(空位占位)的子节点会被跳过(不算 real_children),
      渲染层另算 len(parent.children) < max_children 即可
    """
    # ---- uid ----
    dist_id = str(d.get("distId") or "")
    if dist_id:
        # officev2: "N5637590.1" / "N5637590" / "N-5637591" / "N-7xxxxxx"
        digits = dist_id.lstrip("N").lstrip("n").split(".")[0]
        try:
            uid_v = int(digits)
        except (ValueError, TypeError):
            uid_v = 0
    else:
        uid_v = int(d.get("uid") or 0)

    # 同步 max_uid(便于全局)
    if max_uid is not None and uid_v > max_uid[0]:
        max_uid[0] = uid_v

    # 同步 dist_id → uid 反查(highlight 按 distId 做 key)
    if uid_to_dist_id_out is not None and uid_v and dist_id:
        uid_to_dist_id_out[uid_v] = dist_id

    # ---- pv / max_children / name ----
    pv_raw = d.get("pv")
    try:
        pv_v = int(pv_raw) if pv_raw is not None else 0
    except (TypeError, ValueError):
        pv_v = 0
    max_raw = d.get("maxLines", 5)
    try:
        max_v = int(max_raw) if max_raw is not None else 5
    except (TypeError, ValueError):
        max_v = 5
    if not max_v:
        max_v = 5

    is_avail_v = bool(d.get("available", False))
    name_v = str(d.get("name") or "")

    node = Node5(
        uid=uid_v,
        pv=pv_v,
        depth=depth,
        name=name_v,
        max_children=max_v,
        is_avail=is_avail_v,
        line_id=line_id,
    )

    # ★ 2026-07-15 PR #17: 保留 avail 占位节点在 children 数组里
    #   - 之前跳 avail 会导致算法 BFS 找不到 L1 父(因为 root + 5 L1 avail 加载后 root.children=0)
    #   - 算法需要 avail 节点作为挂入点(按 parentLineId 索引)
    #   - _replace_avail_with_real (commit_preview) 也用 children[parentLineId-1] 找 avail 节点
    # - 渲染层 (前端 _tree_render_children) 按 is_avail 区分渲染
    raw_children = d.get("children") or []
    for i, c in enumerate(raw_children):
        node.children.append(
            load_from_jstree_dict(
                c, depth=depth + 1,
                line_id=c.get("parentLineId") or (i + 1),
                max_uid=max_uid,
                uid_to_dist_id_out=uid_to_dist_id_out,
            )
        )
    return node


def load_tree_from_jstree_file(path: str) -> Optional[Tuple[Node5, Dict[int, str]]]:
    """加载 jstree JSON → (Node5 树, uid → distId 反查表)

    Returns
    -------
    (tree, uid_to_dist_id) 或 None(文件不存在/解析失败 → 调用方 fallback 到空 root)

    uid_to_dist_id 用途
    ------------------
    - 把 officev2 distId ("N5637590.1") 跟 Node5.uid 反向绑定;
    - 写盘 / highlight 时按 distId 找位置,避免 uid 被 -global_rank 替换后丢失原 distId
    """
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as _e:
        print(f"[skill_5_helpers] 加载文件 {os.path.basename(path)} 失败: {_e};fallback 到空 root")
        return None
    if not isinstance(raw, dict):
        return None
    try:
        max_uid_box: List[int] = [0]
        uid_to_dist_id: Dict[int, str] = {}
        tree = load_from_jstree_dict(
            raw, depth=0, line_id=0,
            max_uid=max_uid_box,
            uid_to_dist_id_out=uid_to_dist_id,
        )
        return (tree, uid_to_dist_id)
    except Exception as _e:
        print(f"[skill_5_helpers] 递归构造树失败 {os.path.basename(path)}: {_e};fallback 到空 root")
        return None


# ===========================================================================
# 5. 祖先链
# ===========================================================================

def _ancestor_chain(
    root: Node5,
    target: Node5,
    dist_id_map: Optional[Dict[int, str]] = None,
) -> List[Dict[str, Any]]:
    """DFS 找 root → target 的完整路径(target 是末节点)。

    与 skill_5_lib 的 ancestor_chain 差异: 输出额外带 `is_avail` 和 `dist_id` 字段,
    前端 chat 卡渲染完整路径时方便识别空位占位 / 用 officev2 原 distId。

    Returns
    -------
    List[dict],每项:
        {
            "uid": int,
            "name": str,
            "parent_line_id": int | None,   # 在父节点 children 中的 1-based 位置;root 为 None
            "is_avail": bool,                # True = 空位占位
            "dist_id": str,                  # officev2 distId 或 PREVIEW-N
        }

    边角
    ----
    - 找不到 target 时返回 [root-only] 单元素链(不会抛)
    """
    # DFS 找 root → target 路径
    path: List[Node5] = []

    def _dfs(n: Node5, acc: List[Node5]) -> bool:
        acc.append(n)
        if n is target:
            return True
        for c in n.children:
            if _dfs(c, acc):
                return True
        acc.pop()
        return False

    _dfs(root, path)
    if not path:
        # 兜底:target 找不到(理论上不应发生)→ 返回 root-only 链
        return [{
            "uid": root.uid,
            "name": root.name or "(未知)",
            "parent_line_id": None,
            "is_avail": False,
            "dist_id": (dist_id_map or {}).get(root.uid, ""),
        }]

    chain: List[Dict[str, Any]] = []
    for idx, n in enumerate(path):
        chain.append({
            "uid": n.uid,
            "name": n.name,
            "parent_line_id": None if idx == 0 else n.line_id,
            "is_avail": bool(n.is_avail),
            "dist_id": (dist_id_map or {}).get(n.uid, ""),
        })
    return chain


# ===========================================================================
# 6. history JSON 序列化(给前端 / Agent 用)
# ===========================================================================

def history_to_json(history: List[Dict[str, Any]], indent: int = 2) -> str:
    """把 simulate_addition 返回的 history 数组序列化为 JSON 字符串"""
    return json.dumps(history, indent=indent, ensure_ascii=False)


__all__ = [
    "AdditionStep",
    "_bfs_all",
    "_snapshot_profit",
    "_ancestor_chain",
    "load_from_jstree_dict",
    "load_tree_from_jstree_file",
    "history_to_json",
]
