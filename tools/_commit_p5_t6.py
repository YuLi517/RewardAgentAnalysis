"""P5 Task 6 — commit AGENTS.md §6.9 P5 状态记录

用法: python tools/_commit_p5_t6.py
"""
import subprocess
import os
import tempfile

REPO = r"D:\Projects\Reward\RewardAgentAnalysis"
OUT = r"C:\Users\rainc\AppData\Local\Temp\commit_t6_out.txt"


def main():
    os.chdir(REPO)
    MSG = """docs(agents): §6.9 P5 状态记录 (商业计划书 PDF 导出 + 独立 scenario_pdf.html + jsPDF + html2canvas)

- 业务: 招商/路演场景, 1 键导出 9 页完整版 PDF
- 关键文件: scenario_pdf.html/css/js + 主菜单入口 + e2e 测试 + spec/plan
- 验收: 6 task 全过 (spec + HTML+CSS + JS + 主菜单 + e2e + 本 commit)
- 业务定位: 大重构 P1 阶段 5 子项目全部收尾 (P1+P2+P3+P4+P5)
- 后续 (P5.1+): 多 scenario 拼 PDF / 服务端 reportlab / PDF 编辑 / 短链接 QR

业务价值:
- 对外交付物 (邮件附件 / 印刷品), 招商路演"一方案一文档"标准化
- 0 后端改动, 0 npm 装包, 2 个 CDN script 引入
- 4 副 Canvas 复 P3 PR1/PR2/PR3, 9 section 截图 + jsPDF 拼 9 页
"""

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", prefix="commit_msg_",
        delete=False, encoding="utf-8"
    ) as f:
        f.write(MSG)
        msg_path = f.name

    try:
        # 1) add
        r = subprocess.run(
            ["git", "add", "AGENTS.md"],
            capture_output=True, text=True, encoding="utf-8"
        )
        r2 = subprocess.run(
            ["git", "add", "-f", "tools/_commit_p5_t6.py"],
            capture_output=True, text=True, encoding="utf-8"
        )

        # 2) commit
        r = subprocess.run(
            ["git", "commit", "-F", msg_path],
            capture_output=True, text=True, encoding="utf-8"
        )

        with open(OUT, "w", encoding="utf-8") as fo:
            fo.write(f"[add1] rc={r.returncode}\n  stderr: {r.stderr}\n")
            fo.write(f"[add2] rc={r2.returncode}\n  stderr: {r2.stderr}\n")
            fo.write(f"[commit] rc={r.returncode}\n  stdout: {r.stdout}\n  stderr: {r.stderr}\n")

        # 3) log
        r = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            capture_output=True, text=True, encoding="utf-8"
        )
        with open(OUT, "a", encoding="utf-8") as fo:
            fo.write(f"[log] {r.stdout}\n")
    finally:
        try:
            os.unlink(msg_path)
        except OSError:
            pass


if __name__ == "__main__":
    main()
