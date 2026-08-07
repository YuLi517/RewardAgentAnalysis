"""P5 Task 5: scenario_pdf.html e2e 测试 (Playwright)

业务:
  - 加载 /static/scenario_pdf.html
  - 选第 1 个 scenario
  - 校验 9 section 渲染 + 4 副 canvas 存在
  - 点 "📄 生成 PDF" 按钮, 验证 download 事件 (jsPDF blob → .pdf 文件)

依赖:
  - subagent A 的 Task 2 (scenario_pdf.html/css) + Task 3 (scenario_pdf.js) 必须先 commit
  - 端口 38089 (跟 P3 PR1/P2 e2e 共用, fixture 复用)
"""
import subprocess
import time
import socket

import pytest

PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass


def _port_open(host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


@pytest.fixture(scope="module")
def uvicorn_server():
    """启 uvicorn 38089 fixture, yield 后 teardown (跟 P3 PR1/P2 共用)"""
    if _port_open("127.0.0.1", 38089):
        yield "http://127.0.0.1:38089"
        return
    proc = subprocess.Popen(
        ["python", "-m", "uvicorn", "main:app", "--port", "38089", "--host", "127.0.0.1"],
        cwd=r"D:\Projects\Reward\RewardAgentAnalysis",
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # 等 server ready
    for _ in range(30):
        if _port_open("127.0.0.1", 38089):
            break
        time.sleep(0.5)
    yield "http://127.0.0.1:38089"
    proc.terminate()
    proc.wait(timeout=5)


@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="playwright not installed")
def test_scenario_pdf_page_renders(uvicorn_server):
    """测试 1: scenario_pdf.html 渲染 + 选 scenario + 9 section 可见 + 4 副 canvas"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{uvicorn_server}/static/scenario_pdf.html")

        # 等 sidebar 列表加载
        page.wait_for_selector("#scenario-list", timeout=10000)
        page.wait_for_function(
            "document.querySelectorAll('.pdf-sidebar-item').length > 0",
            timeout=10000,
        )

        # 选第 1 个 scenario
        page.locator(".pdf-sidebar-item").first.click()

        # 等 9 section 渲染 (60s, 跟 PR1 一样已知慢: TOP 5 节点 5×60s=5min, 但本测试只校验存在)
        page.wait_for_selector(".pdf-section", timeout=60000)
        sections = page.locator(".pdf-section").count()
        assert sections == 9, f"期望 9 section, 实际 {sections}"

        # 校验 4 副 canvas 存在 (树形/折线/热图/横向条形)
        canvases = page.locator(".pdf-section canvas").count()
        assert canvases >= 4, f"期望 >= 4 副 canvas, 实际 {canvases}"

        # 校验 "生成 PDF" 按钮存在
        btn = page.query_selector("#btn-generate-pdf")
        assert btn is not None, "缺少 #btn-generate-pdf 按钮"

        browser.close()


@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="playwright not installed")
def test_scenario_pdf_download(uvicorn_server):
    """测试 2: 点 "📄 生成 PDF" 触发 download 事件 (filename 以 scenario_ 开头, 以 .pdf 结尾)"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.goto(f"{uvicorn_server}/static/scenario_pdf.html")

        # 等 sidebar + 选第 1 个 + 等 9 section
        page.wait_for_function(
            "document.querySelectorAll('.pdf-sidebar-item').length > 0",
            timeout=10000,
        )
        page.locator(".pdf-sidebar-item").first.click()
        page.wait_for_selector(".pdf-section", timeout=60000)

        # 点生成按钮, 等 download 事件 (180s 上限, 业务接受 60-180s 慢)
        with page.expect_download(timeout=180000) as download_info:
            page.locator("#btn-generate-pdf").click()

        download = download_info.value
        suggested = download.suggested_filename
        assert suggested.startswith("scenario_"), (
            f"download filename 应以 scenario_ 开头, 实际 {suggested!r}"
        )
        assert suggested.endswith(".pdf"), (
            f"download filename 应以 .pdf 结尾, 实际 {suggested!r}"
        )

        browser.close()
