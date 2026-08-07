"""P5 Task 4 — commit static/index.html 加 📄 Scenario PDF 入口

用法: python tools/_commit_p5_t4.py
"""
import subprocess
import sys
import os
import tempfile

REPO = r"D:\Projects\Reward\RewardAgentAnalysis"
MSG = """feat(scenario-ui): P5 Task 4 — static/index.html 主菜单加 📄 Scenario PDF 入口

- 加第 4 个 nav link: <a href="/static/scenario_pdf.html">📄 Scenario PDF</a>
- 位置: 跟 P3 PR1 / P3 PR3 / P4 3 个入口并列, 在 scenario_library.html 后
- 等待 subagent A commit scenario_pdf.html/css/js 后, 浏览器点这个链接可跳

业务: 商业计划书 PDF 导出入口, 招商/路演场景"一方案一文档"标准化
"""


def main():
    os.chdir(REPO)
    # 写 message 到临时文件 (UTF-8, 避免 PowerShell 编码问题)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", prefix="commit_msg_",
        delete=False, encoding="utf-8"
    ) as f:
        f.write(MSG)
        msg_path = f.name

    try:
        # 1) add (tools/_commit_p5_t4.py 被 .gitignore `_*` 误伤, 强制 add)
        r = subprocess.run(
            ["git", "add", "-f", "tools/_commit_p5_t4.py", "static/index.html"],
            capture_output=True, text=True, encoding="utf-8"
        )
        print(f"[add] rc={r.returncode}")
        if r.stdout: print(f"  stdout: {r.stdout}")
        if r.stderr: print(f"  stderr: {r.stderr}")

        # 2) commit
        r = subprocess.run(
            ["git", "commit", "-F", msg_path],
            capture_output=True, text=True, encoding="utf-8"
        )
        print(f"[commit] rc={r.returncode}")
        if r.stdout: print(f"  stdout: {r.stdout}")
        if r.stderr: print(f"  stderr: {r.stderr}")

        # 3) log
        r = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            capture_output=True, text=True, encoding="utf-8"
        )
        print(f"[log] {r.stdout.strip()}")
    finally:
        try:
            os.unlink(msg_path)
        except OSError:
            pass


if __name__ == "__main__":
    main()
