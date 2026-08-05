"""PR #64: 结算结果表字段名修复
- 前端用 m.commission / m.pairing / m.total (错的)
- API 实际返回 m.own_commission / m.ancestor_share / m.total_commission (PR #53 改的)
- 修复: 前端用新字段, 兜底旧字段名 (兼容性)

业务影响: "结算本周佣金" 模态框之前永远全 0, 现在显示真实值
★ PR #65: 改名为持续账单视图 (renderBillHtml), 字段名仍用 m.own_commission / m.ancestor_share / m.total_commission
"""
import sys
from pathlib import Path
import re

# ★ PR #65 修: 用 __file__ 相对路径, 不依赖具体 worktree 路径
# (跟 PR #58 test 一致, AGENTS.md §5.27)
WT = Path(__file__).resolve().parent.parent
INDEX_HTML = WT / "static" / "index.html"
html = INDEX_HTML.read_text(encoding="utf-8")


def _extract_function(name):
    """抽出指定函数体"""
    pattern = rf"function {name}\(.*?^\}}\s*$"
    m = re.search(pattern, html, re.DOTALL | re.MULTILINE)
    if not m:
        # 备选: 找 function name(...) {
        pattern2 = rf"function {name}\(.*?\n\}}\s*\n"
        m = re.search(pattern2, html, re.DOTALL)
    return m.group(0) if m else ""


def test_renderBillHtml_uses_own_commission():
    """前端 renderBillHtml 优先从 m.own_commission 读 commission"""
    fn = _extract_function("renderBillHtml")
    assert fn, "renderBillHtml 函数不存在"
    assert "own_commission" in fn, (
        "renderBillHtml 必须用 m.own_commission 读基本 commission (PR #53 改的字段名)"
    )


def test_renderBillHtml_uses_ancestor_share():
    """前端 renderBillHtml 优先从 m.ancestor_share 读 pairing"""
    fn = _extract_function("renderBillHtml")
    assert fn
    assert "ancestor_share" in fn, (
        "renderBillHtml 必须用 m.ancestor_share 读对等奖金 (PR #53 改的字段名)"
    )


def test_renderBillHtml_uses_total_commission():
    """前端 renderBillHtml 优先从 m.total_commission 读 total"""
    fn = _extract_function("renderBillHtml")
    assert fn
    assert "total_commission" in fn, (
        "renderBillHtml 必须用 m.total_commission 读合计 (PR #53 改的字段名)"
    )


def test_renderBillHtml_uses_member_dist_id():
    """前端 UID 字段: API 没 uid, 显示 member_dist_id"""
    fn = _extract_function("renderBillHtml")
    assert fn
    assert "member_dist_id" in fn, (
        "renderBillHtml UID 列应显示 member_dist_id (API 实际字段)"
    )


def test_api_settle_returns_correct_field_names():
    """API settle 返回的字段名是 own_commission / ancestor_share / total_commission"""
    main_py = (WT / "main.py").read_text(encoding="utf-8")
    assert '"own_commission"' in main_py, (
        "main.py api_period_settle 必须返回 own_commission 字段"
    )
    assert '"ancestor_share"' in main_py, (
        "main.py api_period_settle 必须返回 ancestor_share 字段"
    )
    assert '"total_commission"' in main_py, (
        "main.py api_period_settle 必须返回 total_commission 字段"
    )


def test_PR64_comment_marks_the_fix():
    """PR #64 修复点必须有注释 (跟代码配合后续排查)"""
    assert "PR #64" in html or "PR #65" in html, (
        "index.html 必须有 PR #64 或 PR #65 注释, 说明字段名修复原因"
    )


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
