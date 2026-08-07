"""P5 Task 5 — commit tests/test_scenario_pdf_e2e.py (Playwright 2 测试)

用法: python tools/_commit_p5_t5.py
"""
import subprocess
import os
import tempfile

REPO = r"D:\Projects\Reward\RewardAgentAnalysis"
MSG = """test(scenario-ui): P5 Task 5 — Playwright e2e (scenario_pdf.html 渲染验证 + PDF 下载验证)

2 个测试:
- test_scenario_pdf_page_renders: 加载页 → 选第 1 scenario → 校验 9 section + ≥4 canvas + 生成按钮
- test_scenario_pdf_download: 点 "📄 生成 PDF" → 等 download 事件 (≤180s) → 校验 filename

依赖:
- subagent A Task 2+3 (scenario_pdf.html/css/js) 必须先 commit
- 端口 38089 (跟 P3 PR1/P2 e2e 共用, fixture 复用)
- 业务接受 60-180s 慢 (跟 PR1 已知慢一样, 9 section 截图 + 5 节点 canvas)

风险:
- 60-180s 测试时长, 业务接受, 跟 PR1 风格一致
- download 走 jsPDF blob + a.click(), Playwright accept_downloads=True 捕获
"""


def main():
    os.chdir(REPO)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", prefix="commit_msg_",
        delete=False, encoding="utf-8"
    ) as f:
        f.write(MSG)
        msg_path = f.name

    try:
        # 1) add
        r = subprocess.run(
            ["git", "add", "tests/test_scenario_pdf_e2e.py", "tools/_commit_p5_t5.py"],
            capture_output=True, text=True, encoding="utf-8"
        )
        # 强制 add 工具脚本 (被 .gitignore _* 误伤)
        r2 = subprocess.run(
            ["git", "add", "-f", "tools/_commit_p5_t5.py"],
            capture_output=True, text=True, encoding="utf-8"
        )

        # 2) commit
        r = subprocess.run(
            ["git", "commit", "-F", msg_path],
            capture_output=True, text=True, encoding="utf-8"
        )
        with open(r"C:\Users\rainc\AppData\Local\Temp\commit_t5_out.txt", "w", encoding="utf-8") as fo:
            fo.write(f"[add1] rc={r.returncode}\n  stdout: {r.stdout}\n  stderr: {r.stderr}\n")
            fo.write(f"[add2] rc={r2.returncode}\n  stdout: {r2.stdout}\n  stderr: {r2.stderr}\n")
            fo.write(f"[commit] rc={r.returncode}\n  stdout: {r.stdout}\n  stderr: {r.stderr}\n")

        # 3) log
        r = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            capture_output=True, text=True, encoding="utf-8"
        )
        with open(r"C:\Users\rainc\AppData\Local\Temp\commit_t5_out.txt", "a", encoding="utf-8") as fo:
            fo.write(f"[log] {r.stdout}\n")
    finally:
        try:
            os.unlink(msg_path)
        except OSError:
            pass


if __name__ == "__main__":
    main()
