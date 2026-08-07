#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""截图验证 scenario-section 移到底部后的 welcome 屏布局。"""
import sys
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:38080/static/index.html"
OUT_TOP = "logs/ui_top.png"
OUT_FULL = "logs/ui_full.png"
OUT_BOTTOM = "logs/ui_bottom.png"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.goto(URL, wait_until="networkidle", timeout=30000)
        # 强制显示 welcome (chat 是空,默认就是 welcome)
        page.wait_for_selector("#welcomeScreen:not(.hidden)", timeout=5000)
        page.wait_for_timeout(800)  # 等字体 + 渐入动画
        # 顶部
        page.screenshot(path=OUT_TOP, full_page=False)
        # 整页
        page.screenshot(path=OUT_FULL, full_page=True)
        # 滚到底部
        page.evaluate("document.getElementById('welcomeScreen').scrollTo(0, 99999)")
        page.wait_for_timeout(400)
        page.screenshot(path=OUT_BOTTOM, full_page=False)
        browser.close()
    print(f"OK: top={OUT_TOP} full={OUT_FULL} bottom={OUT_BOTTOM}")


if __name__ == "__main__":
    sys.exit(main() or 0)
