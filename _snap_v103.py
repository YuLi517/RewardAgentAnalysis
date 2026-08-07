"""v1.0.3 浅色 beam-content 光带截图验证."""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("logs")
OUT.mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1100, "height": 900})

    # 1. 加载 Vite 页面
    page.goto("http://127.0.0.1:5173/", wait_until="networkidle", timeout=15000)
    page.wait_for_selector(".beam-wrap", timeout=10000)
    page.wait_for_timeout(800)  # 等 BorderBeam bloom 渲染

    # 2. 整页截图
    page.screenshot(path=str(OUT / "v103_full.png"), full_page=True)
    print(f"[1/3] v103_full.png saved")

    # 3. 4 个 beam-wrap 局部 (左侧 4 卡片)
    wraps = page.locator(".beam-wrap")
    n = wraps.count()
    print(f"  beam-wrap count = {n}")

    # 抓每个 wrap 的 bbox + 单独截图
    for i in range(n):
        bb = wraps.nth(i).bounding_box()
        print(f"  wrap[{i}] bbox: x={bb['x']:.0f} y={bb['y']:.0f} w={bb['width']:.0f} h={bb['height']:.0f}")
        wraps.nth(i).screenshot(path=str(OUT / f"v103_wrap_{i}.png"))
    print(f"[2/3] {n} wraps screenshots saved")

    # 4. 跨 4 时间点采 beam 旋转 (验证动画在动)
    for t in range(4):
        page.wait_for_timeout(750)  # 1/4 周期 (3s duration)
        wraps.nth(0).screenshot(path=str(OUT / f"v103_beam_t{t}.png"))
    print(f"[3/3] 4 beam rotation frames saved")

    # 5. 业务 e2e: 改 max_level + 提交 + 验证卡片
    page.locator('.val-input').first.evaluate("el => el.scrollIntoView({block: 'center'})")
    max_lv = page.locator('.val-input').nth(1)  # 第二个 input 是 max_level
    max_lv.fill("6")
    page.wait_for_timeout(200)
    total_target = page.locator('.val-input').nth(2)  # total_target
    print(f"  total_target auto = {total_target.input_value()}")

    initial_pv = page.locator('.val-input').nth(5)  # revenue 第一个
    initial_pv.fill("2000")
    page.wait_for_timeout(200)

    own_rate = page.locator('.val-input').nth(7)  # commission 第一个
    own_rate.fill("0.20")
    page.wait_for_timeout(200)

    page.locator("#btn-submit").click()
    page.wait_for_timeout(3500)  # 等 14 月计算完成

    # 8 报酬卡片截图
    page.screenshot(path=str(OUT / "v103_submitted.png"), full_page=True)
    print(f"[bonus] v103_submitted.png saved (8 报酬卡片)")

    # 抓 8 卡片的 val 文本
    vals = page.locator(".card .val").all_text_contents()
    print(f"  8 卡片 val: {vals}")

    browser.close()
print("\n=== v1.0.3 snap done ===")
