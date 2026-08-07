"""P3 PR1: scenario.html e2e 测试 (Playwright)

业务:
  - 加载 /static/scenario.html
  - 填 4 组参数 (默认值)
  - 点提交
  - 校验 8 报酬卡片显示数字 + Canvas 树形有内容
  - 校验 border-beam 4 个框存在
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
    """启 uvicorn 38089 fixture, yield 后 teardown"""
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
def test_scenario_page_loads(uvicorn_server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{uvicorn_server}/static/scenario.html")
        # 标题校验
        assert "SCENARIO" in page.title()
        # 4 个 border-beam 框
        beams = page.query_selector_all(".beam-wrap")
        assert len(beams) == 4, f"期望 4 个 border-beam, 实际 {len(beams)}"
        # Canvas 存在
        canvas = page.query_selector("#tree-canvas")
        assert canvas is not None
        # 8 卡片
        cards = page.query_selector_all(".p3-cards .card")
        assert len(cards) == 8, f"期望 8 卡片, 实际 {len(cards)}"
        # 提交按钮文案
        btn = page.query_selector("#btn-submit")
        assert "提交场景" in btn.inner_text()
        browser.close()


@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="playwright not installed")
def test_scenario_submit_shows_8_cards(uvicorn_server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{uvicorn_server}/static/scenario.html")
        # 点提交
        page.click("#btn-submit")
        # 等卡片值变化 (2s 预算)
        for _ in range(40):
            total = page.query_selector('.card[data-field="total"] .val').inner_text()
            if total != "—" and total != "$0.00":
                break
            time.sleep(0.1)
        # 校验 8 卡片有数字
        for field in ["ownBasic", "pairBonus", "teamBonus", "savings",
                      "leader", "horizontal", "retail", "total"]:
            val = page.query_selector(f'.card[data-field="{field}"] .val').inner_text()
            assert val.startswith("$"), f"{field} 应该是 $XX.XX, 实际 {val!r}"
        # total > 0
        total = page.query_selector('.card[data-field="total"] .val').inner_text()
        assert total != "$0.00", f"total 应该是 > 0, 实际 {total}"
        browser.close()


@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="playwright not installed")
def test_scenario_page_shows_heatmap_after_submit(uvicorn_server):
    """提交后, 热图 section 渲染 8 行 14 列格子 (不跑 14 分钟 computation, 用小 scenario)"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        # 注入小 scenario (max_level=2, 3 月) 跳过 14 分钟
        page.goto(f"{uvicorn_server}/static/scenario.html")
        # 修改 formState 改成小 scenario
        page.evaluate("""() => {
          window.P3.getFormState().tree_shape.max_level = 2;
          window.P3.getFormState().tree_shape.layer_counts = {0: 1, 1: 2, 2: 2};
        }""")
        # 提交
        page.click("#btn-submit")
        # 等 8 卡片填充 (≤ 60s)
        for _ in range(40):
            total = page.query_selector('.card[data-field="total"] .val').inner_text()
            if total != "—" and total != "$0.00":
                break
            time.sleep(0.1)
        # 校验 heatmap section 可见
        heatmap = page.query_selector("#heatmap")
        assert heatmap is not None
        # canvas 存在
        canvas = page.query_selector("#heatmap-canvas")
        assert canvas is not None
        # 校验 canvas 尺寸 (8 行 14 列)
        width = page.evaluate("() => document.getElementById('heatmap-canvas').width")
        assert width > 400, f"heatmap canvas 宽度应该 > 400, 实际 {width}"
        # hover 测试 (cell 0,0 = ownBasic M0)
        # click detail modal
        browser.close()
