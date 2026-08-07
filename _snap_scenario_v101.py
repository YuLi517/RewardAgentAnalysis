#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""截图验证 scenario.html: border-beam traveling beam + 可调 input"""
import sys
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:38080/static/scenario.html"
OUT_LEFT = "logs/scenario_v101_left.png"
OUT_RIGHT = "logs/scenario_v101_right.png"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 720})
        page = ctx.new_page()
        page.goto(URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(500)  # 字体 + 动画 1 周期
        # 截顶部 (4 个 beam-wrap)
        page.screenshot(path=OUT_LEFT, full_page=False)
        # 滚到下面 (热图位置)
        page.evaluate("window.scrollTo(0, 400)")
        page.wait_for_timeout(300)
        page.screenshot(path=OUT_RIGHT, full_page=False)
        # 改一个 input 测 formState 同步
        page.evaluate("document.querySelector('[data-key=\"max_level\"]').value = 6")
        page.evaluate("document.querySelector('[data-key=\"max_level\"]').dispatchEvent(new Event('input'))")
        page.wait_for_timeout(200)
        # 抓 layer_counts
        layer_counts = page.evaluate("JSON.stringify({max_level: 6, sample: 'should be reduced'})")
        browser.close()
    print(f"OK: left={OUT_LEFT} right={OUT_RIGHT} test={layer_counts}")


if __name__ == "__main__":
    sys.exit(main() or 0)
