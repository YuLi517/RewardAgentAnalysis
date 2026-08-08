"""json 树模板加载器 (v1.0.9 2026-08-08, v1.0.18 2026-08-08 bfs_id 偏移修复)

业务: 之前 fork_type 走 builder.py._build_bfs_tree 动态构树 (PR #18 位反转算法)
      现在用户 (2026-08-08) 拍板: fork_type 选不同 JSON 模板 + 取前 N=2144 节点
        - binary (2 叉)     → json/binarytree_4093.json     → 前 2144 节点
        - quaternary (4 叉) → json/quaternarytree_87381.json → 前 2144 节点
        - ternary (3 叉)    → 维持 5_3 兼容 (现有 _build_bfs_tree)

v1.0.18 关键变更 (bfs_id 偏移修复):
  - 之前 (v1.0.9-v1.0.17): 模板 id 1 = root → bfs_id 1 (跟原 builder.py root=0 不一致)
    业务影响: state 端点 bfs_id=0 拿空, PDF TOP5_BFS_IDS=[0,1,2,3,4] 第 1 个不是 root,
             前端默认 bfs_id=0 = root 跟 binary/quaternary 实际不一致
  - 现在 (v1.0.18): bfs_id = template_id - 1 (binary/quaternary root=0, L1 父=1,2,3,4)
    业务上 ternary / binary / quaternary 三种 fork_type 全部统一:
    - root = bfs_id 0
    - L1 父 = bfs_id 1, 2, 3, 4
    - L2+ 节点 bfs_id - 1 跟原 builder.py 一致
  - 业务动机: 用户可以"随时查每个点位", bfs_id 体系跨 fork_type 一致

JSON 树文件结构 (binarytree_4093.json / quaternarytree_87381.json):
  {
    "total": 4093,
    "structure": "L0=1, L1=4, L2-L10=2叉完整",
    "rule": "位反转排列 + 2叉父子 (parent(L_k[i]) = L_{k-1}_tree[i//2])",
    "levels": { "L0": {count, first, last, bit_reverse_bits}, ... },
    "nodes": [
      {"id": 1, "p": null, "c": [2, 3, 4, 5]},
      {"id": 2, "p": 1, "c": [6, 10]},
      ...
    ]
  }

id = 模板 BFS 编号 (位反转算法, root=1), p = parent_id (null=root), c = children_ids 列表
v1.0.18 后: bfs_id = template_id - 1 (业务上 root=0, L1 父=1,2,3,4 跟 ternary 一致)
"""
from __future__ import annotations
import json
import os
from typing import Dict, List, Optional, Tuple


# 模板路径: fork_type → JSON 文件名
# (ternary 不在这里, 走 builder.py._build_bfs_tree 5_3 兼容)
_TEMPLATE_PATHS: Dict[str, str] = {
    "binary":     "binarytree_4093.json",
    "quaternary": "quaternarytree_87381.json",
}


def _get_template_path(fork_type: str) -> str:
    """fork_type → 模板 JSON 路径"""
    if fork_type not in _TEMPLATE_PATHS:
        raise ValueError(
            f"fork_type={fork_type!r} 无对应 JSON 模板 (支持: {list(_TEMPLATE_PATHS.keys())})"
        )
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "json", _TEMPLATE_PATHS[fork_type],
    )


def load_json_tree_template(fork_type: str) -> dict:
    """加载 fork_type 对应 JSON 模板, 返 raw dict (含 levels + nodes 字段)"""
    return json.loads(open(_get_template_path(fork_type), encoding="utf-8").read())


def truncate_to_n_nodes(template: dict, n: int) -> Tuple[List[dict], Dict[int, int]]:
    """取模板前 N 个节点 (id 1~N), 返 (nodes_list, bfs_id 映射)

    业务: 模板是完整 N 层 (binary 4093, quaternary 87381), 用户拍板模拟 2144 节点
          bfs_id 沿用模板 id (位反转 BFS 编号), 1:1 映射

    Returns:
        nodes_list: 截取的 N 个节点 list, 每个含 {id, p, c} (id 已重映射为 1~N)
        id_map: {template_id: bfs_id} (本场景下 1:1, 但保留映射接口)
    """
    all_nodes = template.get("nodes", [])
    truncated = all_nodes[:n]
    # id 1:1 重映射 (模板 id 已经是 1~N 连续)
    id_map = {n_["id"]: n_["id"] for n_ in truncated}
    return truncated, id_map


def build_bfs_nodes_from_template(fork_type: str, n: int) -> Dict[int, dict]:
    """从 JSON 模板构 builder.py 兼容的 bfs_nodes 字典
    (跟 _build_bfs_tree 输出格式完全一致, 直接喂给下游 commission/ 算法)

    Returns:
        {bfs_id: {"bfs_id": int, "level": int, "parent_bfs": int,
                   "slot_line_id": int, "region_id": int, ...}}

    业务:
      - level = bfs_id 在树里的层数 (root=0, L1=1, L2=2, ...)
      - parent_bfs = p (模板 p 字段, root 是 -1)
      - slot_line_id = c 列表里的位置 (1-indexed, 1=line1, 2=line2, ...)
      - region_id = 父的 region_id (L1 父继承 region, L1 root 子继承 root region=0)
      - L1 父 region_id = bfs_id (L1 节点自己就是 region 1-4)
      - join_week/month/color_index: 跟 _build_bfs_tree 一致, 业务无关这里用 0 兜底
    """
    template = load_json_tree_template(fork_type)
    truncated, _ = truncate_to_n_nodes(template, n)

    # 构 {id: node} 索引, 方便查 parent 和 child 关系
    by_id: Dict[int, dict] = {n_["id"]: n_ for n_ in truncated}

    # 1 次 BFS 算 level
    level_map: Dict[int, int] = {}
    region_map: Dict[int, int] = {}
    slot_map: Dict[int, int] = {}

    # root (id=1, p=null, level=0, region=0, slot=0)
    root_id = 1
    level_map[root_id] = 0
    region_map[root_id] = 0
    slot_map[root_id] = 0

    # BFS: queue [(node_id, parent_id, slot_in_parent)]
    # root 没 parent, 子 slot 由 c 列表位置决定
    from collections import deque
    queue = deque()
    queue.append((root_id, -1, 0))
    while queue:
        cur, parent, slot = queue.popleft()
        cur_node = by_id[cur]
        children = cur_node.get("c", [])
        for i, child_id in enumerate(children, start=1):
            if child_id in by_id:
                level_map[child_id] = level_map[cur] + 1
                # L1 父 = region 1-4
                if level_map[cur] == 0:
                    region_map[child_id] = child_id
                else:
                    # L2+ 子继承父 region
                    region_map[child_id] = region_map[cur]
                slot_map[child_id] = i
                queue.append((child_id, cur, i))

    # 构最终 bfs_nodes (v1.0.18: bfs_id = template_id - 1, 跟原 builder.py root=0 一致)
    # 业务上: 跨 binary / quaternary / ternary 三种 fork_type, root 都是 bfs_id 0
    #         L1 父都是 bfs_id 1, 2, 3, 4 (4 大区)
    bfs_nodes: Dict[int, dict] = {}
    for node in truncated:
        template_id = node["id"]
        template_p = node["p"]
        # 关键偏移: 模板 id 1 (root) → bfs_id 0
        bfs_id = template_id - 1
        # 父 bfs_id 同样偏移 (null=root, bfs_id=-1 表示无父)
        parent_bfs = (template_p - 1) if template_p is not None else -1
        bfs_nodes[bfs_id] = {
            "bfs_id": bfs_id,
            "level": level_map.get(template_id, 0),
            "parent_bfs": parent_bfs,
            "slot_line_id": slot_map.get(template_id, 0),
            "region_id": region_map.get(template_id, 0),
            # 兼容 _build_bfs_tree 字段 (业务上 scenario commission/ 不强依赖这 3 个)
            "join_week": 0,
            "join_month": 0,
            "color_index": 0,
        }
    return bfs_nodes


def compute_layer_counts_from_template(fork_type: str, n: int) -> Dict[int, int]:
    """从 JSON 模板前 N 节点构 layer_counts {level: count}
    跟 _build_bfs_tree 计算的 layer_counts 兼容
    """
    bfs_nodes = build_bfs_nodes_from_template(fork_type, n)
    counts: Dict[int, int] = {}
    for n_ in bfs_nodes.values():
        lv = n_["level"]
        counts[lv] = counts.get(lv, 0) + 1
    return counts


def is_template_fork_type(fork_type: str) -> bool:
    """fork_type 是否走 JSON 模板 (binary/quaternary), 还是走 _build_bfs_tree (ternary)"""
    return fork_type in _TEMPLATE_PATHS
