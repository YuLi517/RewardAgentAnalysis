# -*- coding: utf-8 -*-
"""
Skill 5 内部基础库(原 skill_5.py,2026-07-11 重命名)
==================================================

⚠️ 这不是公开 skill — 它是 `skill_5_1` / `skill_5_2` 共用的底层原语库
(Node5 类 + 业务计算函数)。不要在前端 / slash command 列表里引用本模块名,
也不要 new 一个「/skill_5_lib」路由,会破坏目录语义。

历史背景
--------
    1. 原 skill_5.py 是「5 叉新成员加盟最优布局」的公开 skill(有 /skills/skill_5/run
       + /skills/skill_5/batch/run 路由 + 配套的 json/Tree_5ary.json 数据)
    2. 2026-07-08 起业务侧只跑「列优先 BFS」(skill_5_1) + 「配对优先 BFS」(skill_5_2),
       skill_5 作为"最优点位决策"被两条新派生 skill 完全替代
    3. 但 skill_5.py 里的 Node5 / basic_commission / pairing_bonus / total_basic 等
       是 skill_5_1 / skill_5_2 共享的算法原语,不能物理删除
    4. 故重命名为 skill_5_lib.py,语义从「公开 skill」降级为「内部基础库」

业务规则(沿用 Skill A 的百雅康 5 轨制,与 2 叉版同源):
    动力线 P = MAX(5 个子区分数)               # 分数最高的那条线
    佣金线 L = SUM(其余 4 个子区分数)         # 其余 4 条线的分数之和(不是 MIN)
    单节点基本佣金 = MIN(P, L) × 15%
    单区封顶 = 13,334 分
    对等奖金 = 7 代下线基本佣金的 15% / 10% / 5% × 5

    例:某节点下 L1=1078 / L2=0 / L3=500 / L4=300 / L5=0
       P = 1078(L1), L = 0+500+300+0 = 800
       基本佣金 = MIN(1078, 800) × 0.15 = 120
    ★ 注意:旧版 "L = MIN(5 个子区分数)" 是错的——已修正(2026-06-30)

与 Skill A 的区别:
    - Skill A 假设二叉(left/right)
    - 本库 Node5 支持 N 叉(默认 5,即 max_children=5)
    - 数据结构用 children: list 替代 left/right
    - 算法完全独立,不依赖 optimal_placement.py

对外接口
--------
    1. Node5 类 + 函数式快捷入口
    2. JSON I/O(支持 jsTree 风格和原生 dict 风格)
    3. find_optimal / find_optimal_from_dict / find_optimal_from_json
    4. basic_commission / pairing_bonus / total_basic / total_profit 等佣金计算原语

下游消费者
---------
    - skills/skill_5_1.py (列优先 BFS)
    - skills/skill_5_2.py (配对优先 BFS)
    - main.py (Node5 用在 /skills/skill_5_1/batch/run + /skills/skill_5_2/batch/run 里)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ============================================================
# 业务常量(与 Skill A 保持一致)
# ============================================================
ZONE_CAP: int = 13_334
COMMISSION_RATE: float = 0.15
PAIRING_RATIOS: List[float] = [0.15, 0.10, 0.05, 0.05, 0.05, 0.05, 0.05]
DEFAULT_MAX_CHILDREN: int = 5


# ============================================================
# 数据结构
# ============================================================
@dataclass
class Node5:
    """5 叉树节点(实际可配置 max_children 支持任意 N 叉)

    字段
    ----
    is_avail : bool
        True = 这是 jsTree 中"空位占位节点"(available=true, distId=null),
              不是真实成员,不能作为候选挂载点。
        默认 False,对原生 skill_5 dict 与 dense_demo 等无空位数据完全无影响。
    line_id  : int
        业务 L 编号 (1..max_children), 在父节点 children 数组里的索引 + 1。
        - avail 占位: = jsTree 原始 parentLineId
        - 真实成员  : = 该成员在父 children 数组里的索引 + 1
        - root / 无父: 0
        用于 find_optimal 平局 tiebreak: 按 (depth, line_id) 最小选最优,
        而不是按合成 uid (uid 是 DFS preorder 全局编号, 跟业务 L 编号不一致).
    """
    uid: int
    pv: int = 0
    depth: int = 0
    name: str = ""
    code: str = ""
    children: List["Node5"] = field(default_factory=list)
    max_children: int = DEFAULT_MAX_CHILDREN
    is_avail: bool = False
    line_id: int = 0
    # ★ 2026-07-14 v6: 激活线数 (双轨制业务规则)
    #   - 默认 2: 只 L1+L2 激活, L3-L5 锁定 (非 root 节点渐进解锁)
    #   - 渐进解锁: L1+L2 都被真实成员占满后, 提升到 4 (L3+L4 同时开)
    #   - L3+L4 也满后, 提升到 5 (L5 单独开)
    #   - 2026-08-03 feat-eff-4-root: root 节点在 _build_node5_tree_from_db 显式传 4 (PR 拍板)
    #   - 由 find_optimal 动态计算 + 写回, 业务规则封装在 _compute_active_lines()
    max_active_lines: int = 2

    def effective_max_active_lines(self) -> int:
        """根据当前 children 状态, 算「现在应该激活到几条线」
        业务规则 (2026-07-15 用户拍板 — PR #18 改):
          - 默认 max_active_lines=2 (L1+L2 激活) — 初始激活线数
          - L1+L2 都满足「line max_depth >= 9」(line 下有 9 层子孙)
            → 提升到 4 (L3+L4 同时开)
          - L1-L4 都满足「line max_depth >= 9」
            → 提升到 5 (L5 单独开)
        注: max_active_lines 是「初始值」, 不作为 effective 的硬上限
            (业务规则「渐进解锁」要能升到 5, 受 max_children 限制)

        「line 满」定义: 2026-07-15 用户拍板 — line max_depth >= 9
            (line 父下面 max_depth >= 9, 5 叉树 9 层 = depth 1..9)
        之前 PR #14 的「line 满 = 至少 1 个真实成员」太宽松,
            line 1+2 各 1 个就解锁 line 3+4, 跟「挂满 9 层」业务不符
        """
        # ★ 2026-07-15 PR #18: 改 line 满 = line max_depth >= 9
        FULL_LAYERS = 9  # 业务规则: line 挂满 9 层算「满了」

        def _is_line_filled(line_id: int) -> bool:
            """line 满 = line 父下面 max_depth >= FULL_LAYERS"""
            for c in self.children:
                if not c.is_avail and c.line_id == line_id:
                    if self._max_depth_in_subtree(c) >= FULL_LAYERS:
                        return True
            return False

        effective = self.max_active_lines  # 默认从 max_active_lines 开始
        # L1+L2 都「挂满 9 层」 → 提升到 4
        if _is_line_filled(1) and _is_line_filled(2):
            effective = max(effective, 4)
            if _is_line_filled(3) and _is_line_filled(4):
                effective = max(effective, 5)
        # 上限: max_children (5 叉 → 最大 5)
        return min(effective, self.max_children)

    def _max_depth_in_subtree(self, node: "Node5") -> int:
        """递归算 node 下面 (不含自己) 的子孙深度
        例: node 没子 → 0, node 有 1 层子 → 1, node 有 9 层子孙 → 9
        业务规则「line 满 9 层」= line 父下面有 9 层子孙 (不含 line 自己)
        """
        if not node.children:
            return 0
        return 1 + max(self._max_depth_in_subtree(c) for c in node.children)

    def is_slot_active(self, line_id: int) -> bool:
        """判断某条线 (1..max_children) 是否处于激活状态 (可挂入)
        - 0 = root, 永远 active
        - > effective_max_active_lines() = locked
        """
        if line_id <= 0:
            return True  # root
        return line_id <= self.effective_max_active_lines()

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "uid": self.uid,
            "pv": self.pv,
            "depth": self.depth,
            "name": self.name,
            "code": self.code,
            "max_children": self.max_children,
            "is_avail": self.is_avail,
            "line_id": self.line_id,
            "max_active_lines": self.max_active_lines,
            "effective_max_active_lines": self.effective_max_active_lines(),
            "children": [c.to_dict() for c in self.children],
        }
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any], depth: int = 0, line_id: int = 0) -> "Node5":
        """从 skill_5 原生 dict 构造(uid/pv/depth/children/line_id 字段)
        line_id 留给调用方传入: 通常 = 该节点在父 children 数组里的索引 + 1.
        """
        node = cls(
            uid=int(d.get("uid", 0)),
            pv=int(d.get("pv", 0)),
            depth=int(d.get("depth", depth)),
            name=str(d.get("name", "")),
            code=str(d.get("code", "")),
            max_children=int(d.get("max_children", DEFAULT_MAX_CHILDREN)),
            is_avail=bool(d.get("is_avail", False)),
            line_id=int(d.get("line_id", line_id)),
        )
        for i, c in enumerate(d.get("children", []) or []):
            node.children.append(cls.from_dict(c, depth=depth + 1, line_id=i + 1))
        return node


# ============================================================
# 工具函数
# ============================================================
def clone(node: Node5) -> Node5:
    """深拷贝一棵树"""
    new = Node5(
        uid=node.uid, pv=node.pv, depth=node.depth,
        name=node.name, code=node.code, max_children=node.max_children,
    )
    for c in node.children:
        new.children.append(clone(c))
    return new


def subtree_pv(node: Node5) -> int:
    """节点 + 子孙的总 PV"""
    return node.pv + sum(subtree_pv(c) for c in node.children)


def cap(score: int) -> int:
    """单区封顶: 分数超过 ZONE_CAP 的部分不计入对碰 (与 Skill A 二叉树规则一致)"""
    return min(score, ZONE_CAP)


def find_by_uid(node: Node5, uid: int) -> Optional[Node5]:
    """按 uid 查找节点"""
    if node.uid == uid:
        return node
    for c in node.children:
        hit = find_by_uid(c, uid)
        if hit is not None:
            return hit
    return None


def _find_parent_in_tree(root: Node5, target_uid: int) -> Optional[Node5]:
    """在 root 树里找 target_uid 的父节点(返回父节点 Node5;root 自己不算)
    用于类型 A (avail 升级) 场景: trial_slot 是新成员(avail 升级后),需反向找到父节点算 basic_commission。
    """
    for c in root.children:
        if c.uid == target_uid:
            return root
        r = _find_parent_in_tree(c, target_uid)
        if r is not None:
            return r
    return None


def collect_slots(node: Node5) -> List[Node5]:
    """收集所有可挂载新成员的位置(slot)

    两种 slot 同时支持,覆盖两类数据:

    1. **真实成员有空位**(原生 skill_5 / dense_demo 风格):
       node.is_avail=False 且 len(node.children) < node.max_children.
       挂载 = append 到 children 末尾。

    2. **空位占位**(jsTree 真实导出风格):
       node.is_avail=True. 挂载 = 把这个占位节点**替换**为真实成员节点
       (因为父节点的 children 槽位已被占位填满,只能替换,不能 append)。
    """
    slots: List[Node5] = []
    # 类型 1: 真实成员有空位
    if not node.is_avail and len(node.children) < node.max_children:
        slots.append(node)
    # 类型 2: 空位占位本身就是挂载目标
    if node.is_avail:
        slots.append(node)
    for c in node.children:
        slots.extend(collect_slots(c))
    return slots


def place_pv(node: Node5, uid: int, pv: int, name: str = "", code: str = "") -> bool:
    """把一个新节点挂到指定 uid 的第一个空位上。返回是否成功。"""
    target = find_by_uid(node, uid)
    if target is None:
        return False
    if len(target.children) >= target.max_children:
        return False
    new_uid = max_subtree_uid(node) + 1
    target.children.append(Node5(
        uid=new_uid, pv=pv, depth=target.depth + 1,
        name=name, code=code, max_children=target.max_children,
    ))
    return True


def max_subtree_uid(node: Node5) -> int:
    """整棵树最大的 uid"""
    m = node.uid
    for c in node.children:
        m = max(m, max_subtree_uid(c))
    return m


def _find_avail_by_parent_line(
    node: Any, parent_dist_id: str, line_id: Any
) -> Optional[Dict[str, Any]]:
    """在原始 jsTree dict 中递归定位 (parent_dist_id, parent_line_id) 对应的 avail 占位节点

    注意:jsTree 数据中 avail 节点的 parentId 形如 'N5637590.1' (完整 distId)
    """
    if (
        node.get("available") is True
        and node.get("parentId") == parent_dist_id
        and node.get("parentLineId") == line_id
    ):
        return node
    for c in node.get("children") or []:
        hit = _find_avail_by_parent_line(c, parent_dist_id, line_id)
        if hit is not None:
            return hit
    return None


def _calc_parent_level(raw_node: Any, parent_dist_id: str) -> Optional[int]:
    """根据 distId 在原始 jsTree dict 中找到父节点的 level(字符串数字)"""
    if raw_node.get("distId") == parent_dist_id:
        return int(str(raw_node.get("level", 0)) or 0)
    for c in raw_node.get("children") or []:
        r = _calc_parent_level(c, parent_dist_id)
        if r is not None:
            return r
    return None


def _max_local_dist_id(raw_node: Any) -> int:
    """扫描整棵树所有 N9xxxxxxx.1 形式的本地合成 distId,返回数字最大值

    找不到任何本地合成节点时,返回 9_000_000 作为基线。
    """
    m = 9_000_000  # baseline:所有本地合成 distId 都不低于此

    def is_local_dist_id(did: Any) -> bool:
        """判断是否为本地合成(distId 9 开头,跟真实 officev2 7 位数区分)"""
        if not did:
            return False
        s = str(did)
        # N9xxxxxxx.1 → split 后纯数字部分以 9 开头
        parts = s.split(".")
        if len(parts) < 2:
            return False
        num_str = parts[0].lstrip("N")
        if not num_str.isdigit():
            return False
        # 本地合成特征:数字以 9 开头(officev2 真实数 max ~8_xxx_xxx)
        return num_str.startswith("9")

    def walk(n):
        nonlocal m
        did = n.get("distId")
        if is_local_dist_id(did):
            num = int(str(did).split(".")[0].lstrip("N"))
            m = max(m, num)
        for c in n.get("children") or []:
            walk(c)

    walk(raw_node)
    return m


def commit_to_jstree(
    raw: Dict[str, Any],
    decision: "PlacementDecision5",
    *,
    pv: int,
    name: str = "",
    code: str = "",
    maxLines: int = DEFAULT_MAX_CHILDREN,
) -> Dict[str, Any]:
    """根据 find_optimal_from_jstree 决策,把新成员挂载到 jsTree raw dict 上

    支持两种挂载类型(由 ancestor_chain 末尾节点的 is_avail 字段决定):

    类型 A — avail 升级 (is_avail=True):
        best_uid 是 avail 占位,就地升级为真实成员(不增加树的深度)。
        适用于"补完有 4 个有 PV 子区 + 1 个空位的父节点"等场景。

    类型 B — 成员 append (is_avail=False):
        best_uid 是真实成员有空位,append 新成员到其 children 末尾。
        parent_dist_id = best_uid 自己的 distId,parent_line_id = 下一个可用线号。
        适用于"挂在已有成员下面"等场景。
        ★ 同时为新成员生成 maxLines 个 avail placeholder 作为 children,
          这样后续新人可以挂到它下面,空位总数才能正确累加。

    Parameters
    ----------
    raw       : 原始 jsTree 风格 dict(将被深拷贝,原 dict 不被修改)
    decision  : find_optimal_from_jstree 返回的决策(必须有 ancestor_chain)
    pv        : 新成员 PV
    name      : 新成员姓名(可选;若空字符串,默认 "新成员(<pv>PV)")
    code      : 可选,新成员 distId(officev2 重新导出时会被正式 distId 覆盖)
    maxLines  : 新成员预留子轨数(默认 5)

    Returns
    -------
    新 raw dict(深拷贝,挂载完毕后的 jsTree 风格树)
    """
    import copy

    if not decision.ancestor_chain:
        raise RuntimeError(
            "decision.ancestor_chain 为空 —— 这不是来自 find_optimal_from_jstree 的决策。"
        )

    best_node = decision.ancestor_chain[-1]
    best_uid = best_node["uid"]
    is_avail = bool(best_node.get("is_avail", False))

    new_raw = copy.deepcopy(raw)

    # 合成新成员的 distId
    if code:
        synthesized_dist_id = code
    else:
        local_max = _max_local_dist_id(new_raw)
        synthesized_dist_id = f"N{local_max + 1}.1"
    member_name = name or f"新成员({pv}PV)"

    if is_avail:
        # ============ 类型 A: avail 升级 ============
        meta = decision.best_slot_meta
        if meta is None:
            raise RuntimeError(
                "decision.ancestor_chain[-1].is_avail=True 但 best_slot_meta 为空, "
                "ancestor_chain 与 _avail_ctx_map 不一致 (内部错误)"
            )
        parent_dist_id = meta["parent_dist_id"]
        parent_line_id = meta["parent_line_id"]

        target = _find_avail_by_parent_line(new_raw, parent_dist_id, parent_line_id)
        if target is None:
            raise RuntimeError(
                f"未在原始 JSON 中找到 parent={parent_dist_id} line_id={parent_line_id} "
                f"的空位(可能 JSON 已被并发修改?)"
            )

        parent_level = _calc_parent_level(new_raw, parent_dist_id) or 0
        new_level = parent_level + 1

        # 升级 avail → 真实成员(字段补齐)
        target["available"] = False
        target["pv"] = pv
        target["distId"] = synthesized_dist_id
        target["name"] = member_name
        target["code"] = synthesized_dist_id
        target["level"] = new_level
        target["maxLines"] = maxLines
        target["parentId"] = parent_dist_id
        target["parentLineId"] = parent_line_id
        target["businessLevel"] = target.get("businessLevel") or "MEMBER"
        target["gold"] = target.get("gold") or "NO"
        target["iix"] = target.get("iix") or "NO"
        target["rank"] = target.get("rank") or "MEMBER"
        target["status"] = "0"
        target["status_color"] = target.get("status_color") or "GRAY"
        target["org_pv"] = target.get("org_pv") or "0"
        target["personal_customer_pv"] = target.get("personal_customer_pv") or pv
        target["has_subscription"] = "F"
        target["is_qualified"] = "F"
        target["visibility"] = True
        target["activity_status_id"] = "1"
        # 类型 A: 新成员也带 maxLines 个 avail placeholder (与类型 B 一致, 保持空位总数正确累加)
        target["children"] = [
            _make_avail_placeholder(synthesized_dist_id, line_id, maxLines)
            for line_id in range(1, maxLines + 1)
        ]
    else:
        # ============ 类型 B: 真实成员 append ============
        best_dist_id = best_node.get("dist_id", "")
        target_parent = _find_node_by_dist_id(new_raw, best_dist_id)
        if target_parent is None:
            raise RuntimeError(
                f"未在原始 JSON 中找到 dist_id={best_dist_id} (best_uid={best_uid}, "
                f"可能 JSON 已被并发修改?)"
            )

        # 该父节点下当前 children 数 = 下一个空位的 line_id (jsTree children 顺序对应 parentLineId)
        existing_children = target_parent.get("children") or []
        next_line_id = len(existing_children) + 1
        parent_level = _calc_parent_level(new_raw, best_dist_id) or 0
        new_level = parent_level + 1

        # 构造新成员 jsTree 节点
        new_member: Dict[str, Any] = {
            "id": f"node_{synthesized_dist_id.replace('.', '_')}",
            "distId": synthesized_dist_id,
            "code": synthesized_dist_id,
            "name": member_name,
            "pv": pv,
            "level": str(new_level),
            "maxLines": maxLines,
            "available": False,
            "parentId": best_dist_id,
            "parentLineId": str(next_line_id),
            "businessLevel": "MEMBER",
            "gold": "NO",
            "iix": "NO",
            "rank": "MEMBER",
            "status": "0",
            "status_color": "GRAY",
            "org_pv": "0",
            "personal_customer_pv": str(pv),
            "has_subscription": "F",
            "is_qualified": "F",
            "visibility": True,
            "activity_status_id": "1",
            # ★ 关键: 为新成员生成 maxLines 个 avail placeholder 作为 children
            # 否则空位总数不会累加, batch 跑多次后所有新成员都没法继续挂新人
            "children": [
                _make_avail_placeholder(synthesized_dist_id, line_id, maxLines)
                for line_id in range(1, maxLines + 1)
            ],
        }
        target_parent.setdefault("children", []).append(new_member)

    return new_raw


def _make_avail_placeholder(parent_dist_id: str, parent_line_id: int, max_lines: int) -> Dict[str, Any]:
    """生成 officev2 风格的 avail 占位节点 (字段与 Tree1.json 现有 avail 一致)
    用于类型 B commit 后给新成员填充 children, 保持空位总数正确累加
    """
    return {
        "available": True,
        "businessLevel": None,
        "distId": None,
        "gold": None,
        "iix": None,
        "level": 0,
        "maxLines": 0,
        "parentId": parent_dist_id,
        "parentLineId": parent_line_id,
        "pv": None,
        "rank": None,
        "status": 0,
        "visibility": True,
    }


def _find_node_by_dist_id(raw_node: Any, dist_id: str) -> Optional[Dict[str, Any]]:
    """根据 distId 在原始 jsTree dict 中递归查找节点(供类型 B commit 用)"""
    if raw_node.get("distId") == dist_id:
        return raw_node
    for c in raw_node.get("children") or []:
        hit = _find_node_by_dist_id(c, dist_id)
        if hit is not None:
            return hit
    return None


def save_jstree(path: str, raw: Dict[str, Any], *, indent: int = 2) -> None:
    """把 jsTree 风格 dict 写回磁盘(UTF-8,ensure_ascii=False 保持中文姓名不转义)"""
    import json
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=indent, ensure_ascii=False)
        f.write("\n")


# ============================================================
# 业务计算
# ============================================================
def basic_commission(node: Node5) -> float:
    """节点的基本佣金 = MIN(动力线分数, 佣金线总分) × 15%

    业务规则(用户 2026-06-30 反馈):
        - 5 叉树每个节点最多 5 个子区(L1..L5),每个子区有一个分数(子区 PV 之和,先 cap 封顶)
        - 分数最高的子区称为「动力线」(P)
        - 「佣金线总分」= 其余 4 个子区分数之和
        - 基本佣金 = MIN(P, 佣金线总分) × 15%

    不足 max_children 个子节点的位置,空位算 0 分。
    各子区先经 cap() 封顶 (ZONE_CAP=13334),与 Skill A 二叉树业务规则一致。

    示例:L1=1078, L2=0, L3=500, L4=300, L5=0
         P=L1=1078, L_sum=0+500+300+0=800
         commission = MIN(1078, 800) × 0.15 = 120
    """
    if not node.children:
        return 0.0
    sub_pvs = [cap(subtree_pv(c)) for c in node.children]
    # 补 0 到 max_children(空位算 0 分,跟旧逻辑保持一致)
    while len(sub_pvs) < node.max_children:
        sub_pvs.append(0)
    if not sub_pvs:
        return 0.0

    p_score = max(sub_pvs)              # 动力线 = 最高分的那条
    l_sum = sum(sub_pvs) - p_score      # 佣金线 = 其余 4 条之和

    return min(p_score, l_sum) * COMMISSION_RATE


def total_basic(root: Node5) -> float:
    """整树基本佣金 = SUM(每个节点的基本佣金)"""
    if not root.children:
        return 0.0
    return basic_commission(root) + sum(total_basic(c) for c in root.children)


def pairing_bonus(root: Node5) -> float:
    """对等奖金:对每个非 root 节点 n,basic_commission(n) 沿祖先链最多 7 代按 [0.15, 0.10, 0.05 × 5] 分润"""
    total = 0.0
    ratios = PAIRING_RATIOS

    def walk(node: Node5, ancestors: List[Node5]) -> None:
        nonlocal total
        if ancestors:
            my_bc = basic_commission(node)
            for i, _ in enumerate(reversed(ancestors[: len(ratios)])):
                total += my_bc * ratios[i]
        for c in node.children:
            walk(c, ancestors + [node])

    walk(root, [])
    return total


def total_profit(root: Node5, include_pairing: bool = True) -> float:
    """整树总利润 = 基本佣金 + (可选)对等奖金"""
    return total_basic(root) + (pairing_bonus(root) if include_pairing else 0.0)


def current_profit(root: Node5, include_pairing: bool = True) -> Dict[str, float]:
    """当前树(挂载前)的利润分解"""
    return {
        "basic": round(total_basic(root), 4),
        "pairing": round(pairing_bonus(root), 4) if include_pairing else 0.0,
        "total": round(total_profit(root, include_pairing), 4),
    }


# ============================================================
# 最优挂载决策
# ============================================================
@dataclass
class CandidateResult5:
    """单个候选挂载位置的收益评估"""
    uid: int
    depth: int
    slot_pv: int  # 候选节点当前的整树 PV
    basic_commission: float
    pairing_bonus: float
    total_profit: float
    lift: float
    lift_pct: Optional[float]  # None = 挂前 total=0,百分比无意义(数学上是 +∞)
    line_id: int = 0  # 业务 L 编号 (1..max_children), 用于平局 tiebreak 按 L 顺序填充 (L3 → L4 → L5)
    parent_basic_after: float = 0.0  # ★ 父节点挂入新成员后的 basic_commission(用户视角: "因为新增带来的佣金")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PlacementDecision5:
    """Skill 5 的返回值:最优挂载决策 + 所有候选对比"""
    best_uid: int
    best_depth: int
    best_slot_pv: int
    best_total: float
    best_basic: float
    best_pairing: float
    lift: float
    lift_pct: Optional[float]  # None = 挂前 total=0,百分比无意义
    candidates: List[CandidateResult5]
    current_basic: float = 0.0
    current_pairing: float = 0.0
    current_total: float = 0.0
    max_children: int = DEFAULT_MAX_CHILDREN
    best_slot_meta: Optional[Dict[str, Any]] = None  # 仅 jsTree 适配器填充(avail 占位的 parent 业务信息)
    ancestor_chain: List[Dict[str, Any]] = field(default_factory=list)  # root → best_uid 整条祖先链 (前端画路径图用)
    best_parent_basic: float = 0.0  # ★ best_uid 父节点挂入后的 basic_commission (用户视角的核心数字)
    best_parent_uid: int = 0  # ★ best_uid 父节点 uid (= ancestor_chain[-2].uid, 0 表示 root)

    def to_dict(self) -> Dict[str, Any]:
        best_pos: Dict[str, Any] = {
            "uid": self.best_uid,
            "depth": self.best_depth,
            "slot_pv": self.best_slot_pv,
        }
        if self.best_slot_meta:
            best_pos["slot_meta"] = self.best_slot_meta
        return {
            "best_position": best_pos,
            "best_basic": self.best_basic,
            "best_pairing": self.best_pairing,
            "best_total": self.best_total,
            "best_parent_basic": self.best_parent_basic,
            "best_parent_uid": self.best_parent_uid,
            "lift": round(self.lift, 4),
            "lift_pct": round(self.lift_pct, 2) if self.lift_pct is not None else None,
            "max_children": self.max_children,
            "before": {
                "basic": self.current_basic,
                "pairing": self.current_pairing,
                "total": self.current_total,
            },
            "candidates": [c.to_dict() for c in self.candidates],
            "ancestor_chain": self.ancestor_chain,
        }

    def to_json(self, indent: int = 2, ensure_ascii: bool = False) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=ensure_ascii)


def find_optimal(
    tree: Node5,
    pv: int,
    include_pairing: bool = True,
) -> PlacementDecision5:
    """找最优挂载点(主入口)

    算法:
        1. 收集所有有空位的节点: collect_slots(tree)
        2. 对每个候选:
             a. 深拷贝原树
             b. 在副本上挂载 pv
             c. 重算整树总利润
        3. 比较所有候选的总利润,取 max
    """
    if pv <= 0:
        raise ValueError(f"pv 必须是正整数,得到 {pv}")

    slots = collect_slots(tree)
    if not slots:
        raise ValueError("当前网体已无空位,无法挂载")

    # 当前(挂载前)基线
    cur_basic = total_basic(tree)
    cur_pairing = pairing_bonus(tree) if include_pairing else 0.0
    cur_total = cur_basic + cur_pairing

    candidates: List[CandidateResult5] = []
    best: Optional[CandidateResult5] = None

    for slot in slots:
        # 深拷贝
        trial = clone(tree)
        trial_slot = find_by_uid(trial, slot.uid)
        assert trial_slot is not None

        new_uid = max_subtree_uid(trial) + 1

        if trial_slot.is_avail:
            # 类型 2: 空位占位。挂载 = 占位节点原地升级为真实成员
            # (保留 trial_slot 这个 uid 与位置, 避免重新构造子节点列表)
            trial_slot.is_avail = False
            trial_slot.pv = pv
            trial_slot.name = ""
            trial_slot.code = ""
        else:
            # 类型 1: 真实成员有空位。挂载 = append 到 children 末尾
            trial_slot.children.append(Node5(
                uid=new_uid, pv=pv, depth=trial_slot.depth + 1,
                max_children=trial_slot.max_children,
            ))

        b = basic_commission(trial_slot)
        # pairing 重算整树
        t_basic = total_basic(trial)
        t_pairing = pairing_bonus(trial) if include_pairing else 0.0
        t_total = t_basic + t_pairing
        lift = t_total - cur_total
        # 挂前 total = 0 时百分比无意义(数学上是 +∞),用 None 区分"无法计算"
        lift_pct = (lift / cur_total * 100.0) if cur_total > 0 else None

        # ★ 父节点挂入后的 basic_commission (用户视角: "在父节点上,因为新增带来的佣金")
        # 类型 A (avail 升级): trial_slot = 新成员本身(叶子),父节点需从 trial 里反向找
        # 类型 B (成员 append): trial_slot = 父节点,basic_commission(trial_slot) 已经是父节点的 bc
        # ★ 注意: 用 slot.is_avail 判断(未修改的候选挂载点),不是 trial_slot.is_avail(已被挂载改写)
        parent_node_basic: float = 0.0
        parent_uid_for_cand: int = 0
        if not slot.is_avail:
            # 类型 B: trial_slot 就是父节点,直接算
            parent_node_basic = basic_commission(trial_slot)
            parent_uid_for_cand = trial_slot.uid
        else:
            # 类型 A: 找 trial_slot 的父节点(在 trial 树上递归找 target_uid 的 parent)
            _parent = _find_parent_in_tree(trial, trial_slot.uid)
            if _parent is not None:
                parent_node_basic = basic_commission(_parent)
                parent_uid_for_cand = _parent.uid
            else:
                # 理论上不可能:trial_slot 一定是某个节点的子节点或根,但根的子节点无 parent_uid
                parent_uid_for_cand = 0

        cand = CandidateResult5(
            uid=slot.uid,
            depth=slot.depth,
            slot_pv=subtree_pv(trial_slot),
            basic_commission=round(b, 4),
            pairing_bonus=round(t_pairing, 4),
            total_profit=round(t_total, 4),
            lift=round(lift, 4),
            lift_pct=round(lift_pct, 2) if lift_pct is not None else None,
            line_id=slot.line_id,  # 业务 L 编号 (1..max_children), 用于平局 tiebreak
            parent_basic_after=round(parent_node_basic, 4),
        )
        candidates.append(cand)
        # 平局时按 depth 浅 → line_id 小 的次序取"第一个"。
        # 用业务 L 编号 (line_id) 而非合成 uid, 保证同父节点下按 L1→L2→L3→L4→L5 顺序填充 (符合业务直觉)
        if best is None or cand.lift > best.lift or (
            cand.lift == best.lift and (cand.depth, cand.line_id) < (best.depth, best.line_id)
        ):
            best = cand

    if best is None:
        raise RuntimeError("未找到任何候选(逻辑错误)")

    return PlacementDecision5(
        best_uid=best.uid,
        best_depth=best.depth,
        best_slot_pv=best.slot_pv,
        best_total=best.total_profit,
        best_basic=best.basic_commission,
        best_pairing=best.pairing_bonus,
        lift=best.lift,
        lift_pct=best.lift_pct,
        candidates=candidates,
        current_basic=round(cur_basic, 4),
        current_pairing=round(cur_pairing, 4),
        current_total=round(cur_total, 4),
        max_children=tree.max_children,
        best_parent_basic=best.parent_basic_after,  # ★ 用户视角的核心数字
        best_parent_uid=parent_uid_for_cand,  # ★ 父节点 uid (= ancestor_chain[-2].uid, 0 表示 root)
    )


# ============================================================
# JSON I/O
# ============================================================
def find_optimal_from_dict(
    tree_dict: Dict[str, Any],
    pv: int,
    include_pairing: bool = True,
    default_max_children: int = DEFAULT_MAX_CHILDREN,
) -> PlacementDecision5:
    """从原生 skill_5 dict 树找最优挂载点"""
    if "max_children" not in tree_dict:
        tree_dict = {**tree_dict, "max_children": default_max_children}
    root = Node5.from_dict(tree_dict)
    return find_optimal(root, pv=pv, include_pairing=include_pairing)


def find_optimal_from_json(
    tree_json: str,
    pv: int,
    include_pairing: bool = True,
    default_max_children: int = DEFAULT_MAX_CHILDREN,
) -> PlacementDecision5:
    """从 JSON 字符串找最优挂载点"""
    tree_dict = json.loads(tree_json)
    return find_optimal_from_dict(
        tree_dict, pv=pv, include_pairing=include_pairing,
        default_max_children=default_max_children,
    )


def find_optimal_from_jstree(
    raw: Dict[str, Any],
    pv: int,
    include_pairing: bool = True,
) -> PlacementDecision5:
    """从 jsTree 风格 dict(officev2.chinapartner.co 导出格式)适配后找最优

    jsTree 节点字段:
        distId   = "N5637590.1"  (N + 8 位 + .1) —— 真实成员有值
                = null          —— 空位占位节点(distId 在 jsTree 中是 null)
        name     = "王常军"
        pv       = "0"           (字符串!)
        level    = "1"           (字符串,根 = "1")
        maxLines = "5"
        available= true|false    (空位为 true,真实成员通常为 false)
        children = [...]
        + 一堆业务元数据(distId / parentId / parentLineId / businessLevel / ...)

    适配规则:
        uid     ← 真实成员: int(distId.split('.')[0].lstrip('N'))
                  空位占位: 合成的负数 uid (-1, -2, -3, ...)——确保唯一且不与真实 uid 冲突
        pv      ← 真实成员: int(pv);空位占位: 0
        depth   ← int(level) - 1  (level=1 是 root,depth=0);
                  空位的 level 通常是 0,直接用入参 depth 更稳
        code    ← 真实成员: distId;空位占位: ""
        name    ← name
        max_children ← int(maxLines) if maxLines > 0 else 5
        is_avail    ← node.get("available") is True

    返回的 best_position.slot_meta(仅当最佳位置是空位占位时填充)
        parent_dist_id   ← 该空位的父节点 distId (如 "N5637590.1")
        parent_uid       ← int(distId 解析后的 uid)
        parent_name      ← 父节点成员姓名
        parent_line_id   ← 该空位在父节点的第几条线 (1..max_children)
    """
    # 闭包变量:适配过程中收集每个空位占位的 parent 业务上下文
    _avail_ctx_map: Dict[int, Dict[str, Any]] = {}
    # 全局负数 uid 计数器:avail 占位 + 已挂载本地合成(N9xxxxxx.1 / _LOCAL_)共享同一空间,按 DFS preorder 连续递增
    #   例: 123 个 avail 占位分配 -1..-123,  5 个本地合成成员接续分配 -124..-128
    _neg_uid_ctr = [0]

    def _alloc_neg_uid() -> int:
        """分配下一个负数 uid (-1, -2, -3, ...). 与 avail/已挂载本地合成共享空间,不撞"""
        _neg_uid_ctr[0] += 1
        return -_neg_uid_ctr[0]

    def adapt(node: Dict[str, Any], depth: int = 0,
              parent_ctx: Optional[Dict[str, Any]] = None,
              line_id: int = 0) -> Dict[str, Any]:
        is_avail = node.get("available") is True
        # 用 "or" 而非默认值 "" 防 None 落入 str("None")
        dist_id_raw = node.get("distId")
        dist_id = str(dist_id_raw) if dist_id_raw else ""

        if is_avail:
            # 空位占位节点: distId 一定是 null → 合成唯一负 uid (共享负数空间)
            uid = _alloc_neg_uid()
            pv_v = 0
            try:
                max_ch = int(node.get("maxLines", DEFAULT_MAX_CHILDREN))
                if max_ch <= 0:
                    max_ch = DEFAULT_MAX_CHILDREN
            except (ValueError, TypeError):
                max_ch = DEFAULT_MAX_CHILDREN
            # 记录该空位的 parent 业务上下文
            if parent_ctx is not None:
                _avail_ctx_map[uid] = {
                    "parent_dist_id": parent_ctx.get("dist_id"),
                    "parent_uid": parent_ctx.get("uid_int"),
                    "parent_name": parent_ctx.get("name"),
                    "parent_line_id": node.get("parentLineId"),
                }
            # avail 的 line_id 直接来自 jsTree 原生 parentLineId (1..max_children)
            avail_line_id = node.get("parentLineId") or 0
            return {
                "uid": uid,
                "pv": pv_v,
                "depth": depth,
                "name": "",
                "code": "",
                "max_children": max_ch,
                "is_avail": True,
                "parent_uid": parent_ctx.get("uid_int") if parent_ctx else None,
                "parent_name": parent_ctx.get("name") if parent_ctx else None,
                "parent_line_id": node.get("parentLineId"),
                "line_id": avail_line_id,
                "children": [],
            }

        # 真实成员
        uid_str = dist_id.split(".")[0]
        # 识别"本地合成" 标记:
        #   - 历史格式: N_LOCAL_<n>.1 / N_LOCAL_NEW_<n>.1 (含 _LOCAL_)
        #   - 新格式:   N9xxxxxx.1   (数字部分 >= 9_000_000,_max_local_dist_id 的 baseline)
        # 两种格式都视为"非真实 officev2 成员",分配负数 uid (与 avail 共享空间)
        is_local_synth = False
        if "_LOCAL_" in uid_str:
            is_local_synth = True
        elif uid_str.startswith("N"):
            uid_num_str = uid_str[1:]
            if uid_num_str.isdigit() and int(uid_num_str) >= 9_000_000:
                is_local_synth = True

        if is_local_synth:
            # 本地合成: 分配下一个负数 uid (与 avail 共享,DFS preorder 连续递增)
            uid = _alloc_neg_uid()
        else:
            # 真实 officev2 成员:distId 形如 "N<8 位数字>.1"
            # 真实 distId 一定 N + 数字开头,用 removeprefix 只剥首 N
            uid_str = uid_str.removeprefix("N")
            try:
                uid = int(uid_str) if uid_str else 0
            except ValueError:
                uid = 0
        try:
            pv_v = int(node.get("pv", 0))
        except (ValueError, TypeError):
            pv_v = 0
        try:
            max_ch = int(node.get("maxLines", DEFAULT_MAX_CHILDREN))
            if max_ch <= 0:
                max_ch = DEFAULT_MAX_CHILDREN
        except (ValueError, TypeError):
            max_ch = DEFAULT_MAX_CHILDREN

        my_ctx = {
            "dist_id": dist_id,
            "uid_int": uid,
            "name": str(node.get("name", "")),
        }
        return {
            "uid": uid,
            "pv": pv_v,
            "depth": depth,
            "name": str(node.get("name", "")),
            "code": dist_id,
            "max_children": max_ch,
            "is_avail": False,
            "parent_uid": parent_ctx.get("uid_int") if parent_ctx else None,
            "parent_name": parent_ctx.get("name") if parent_ctx else None,
            "line_id": line_id,  # 业务 L 编号 (1..max_children) - 由调用方从 children 数组索引传入
            "children": [
                adapt(c, depth + 1, my_ctx, line_id=i + 1)
                for i, c in enumerate(node.get("children") or [])
            ],
        }

    adapted = adapt(raw)
    decision = find_optimal_from_dict(
        adapted, pv=pv, include_pairing=include_pairing,
        default_max_children=DEFAULT_MAX_CHILDREN,
    )

    # 构造祖先链: 从 best_uid 沿 parent_uid 走到 root (root → best_uid 顺序)
    # 前端用这个画树状图,commit_to_jstree 用它判断挂载类型
    decision.ancestor_chain = _build_ancestor_chain(decision.best_uid, adapted)

    # 回填 best_slot_meta(供 commit_to_jstree 和 grid 渲染使用)
    # 两种类型统一填:
    #   - 类型 A (avail 升级): 从 _avail_ctx_map 取 (parent_dist_id / parent_uid / parent_name / parent_line_id)
    #   - 类型 B (成员 append): best_uid 自己是 parent, parent_line_id = 下一个可用线号 (children 数 + 1)
    best_node_adapted = _find_dict_by_uid(adapted, decision.best_uid)
    if best_node_adapted is not None:
        if best_node_adapted.get("is_avail"):
            # 类型 A
            decision.best_slot_meta = _avail_ctx_map.get(decision.best_uid)
        else:
            # 类型 B: best_uid 自己是 parent, 新成员 append 到其 children 末尾
            existing_children = best_node_adapted.get("children") or []
            decision.best_slot_meta = {
                "parent_dist_id": best_node_adapted.get("code", ""),  # code 字段 = dist_id
                "parent_uid": decision.best_uid,
                "parent_name": best_node_adapted.get("name", ""),
                "parent_line_id": str(len(existing_children) + 1),
            }
    else:
        decision.best_slot_meta = None

    return decision


def _build_ancestor_chain(best_uid: int, adapted: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 best_uid 沿 parent_uid 走到 root,返回 root → best_uid 顺序的链路
    每节点带 uid/name/dist_id/pv/depth/parent_uid/parent_name/is_avail/parent_line_id
    """
    chain: List[Dict[str, Any]] = []
    cur_uid: Optional[int] = best_uid
    visited: set = set()
    while cur_uid is not None and cur_uid not in visited:
        node = _find_dict_by_uid(adapted, cur_uid)
        if node is None:
            break
        chain.append({
            "uid": cur_uid,
            "name": node.get("name", ""),
            "dist_id": node.get("code", ""),
            "pv": node.get("pv", 0),
            "depth": node.get("depth", 0),
            "line_id": node.get("line_id"),  # 业务 L 编号 (1..max_children), root = 0
            "parent_uid": node.get("parent_uid"),
            "parent_name": node.get("parent_name"),
            "parent_line_id": node.get("parent_line_id"),
            "is_avail": bool(node.get("is_avail", False)),
        })
        visited.add(cur_uid)
        cur_uid = node.get("parent_uid")
    chain.reverse()
    return chain


def _find_dict_by_uid(node: Dict[str, Any], uid: int) -> Optional[Dict[str, Any]]:
    """DFS 查找 uid 匹配的 dict 节点(适配阶段的树结构,不是 Node5)"""
    if node.get("uid") == uid:
        return node
    for c in node.get("children", []) or []:
        hit = _find_dict_by_uid(c, uid)
        if hit is not None:
            return hit
    return None


def tree_to_dict(node: Node5) -> Dict[str, Any]:
    return node.to_dict()


def tree_to_json(node: Node5, indent: int = 2, ensure_ascii: bool = False) -> str:
    return json.dumps(node.to_dict(), indent=indent, ensure_ascii=ensure_ascii)
