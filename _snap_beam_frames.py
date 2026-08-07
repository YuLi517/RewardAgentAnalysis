#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""抓拍 4 帧: 0s / 0.75s / 1.5s / 2.25s 看光带位置 (3s 一圈, 每 0.75s = 90°)
   目的: 验证 mask 限制光带到 2px border 通道 (而不是像之前失败那样整个 conic 摊出)"""
import sys
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:38080/static/scenario.html"
FRAMES = [(0, "logs/beam_t0.png"), (0.75, "logs/beam_t1.png"),
          (1.5, "logs/beam_t2.png"), (2.25, "logs/beam_t3.png")]


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 480, "height": 1100})
        page = ctx.new_page()
        page.goto(URL, wait_until="networkidle", timeout=30000)
        # 滚到 4 卡片清晰可见
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(300)
        for delay, path in FRAMES:
            page.wait_for_timeout(int(delay * 1000) if delay > 0 else 100)
            page.screenshot(path=path, full_page=False, clip={"x": 0, "y": 0, "width": 480, "height": 1100})
            print(f"  t={delay}s -> {path}")
        browser.close()
    print("OK: 4 frames captured")


if __name__ == "__main__":
    sys.exit(main() or 0)
