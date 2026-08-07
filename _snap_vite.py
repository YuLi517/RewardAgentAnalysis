#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""截图验证 BorderBeam 在 React 化的 scenario 页渲染效果"""
import sys
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:5173/"
OUT_TOP = "logs/vite_top.png"
OUT_AFTER = "logs/vite_after.png"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        page.on("pageerror", lambda e: print(f"  page error: {e}"))
        page.on("console", lambda m: print(f"  console: {m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.goto(URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)  # 等 React 渲染 + 字体
        page.screenshot(path=OUT_TOP, full_page=False)
        # 改 max_level input 验证 React state
        el = page.query_selector('input[value="10"]')
        if el:
            el.fill('6')
            page.wait_for_timeout(300)
        # 提交
        try:
            page.click("#btn-submit", timeout=5000)
            page.wait_for_timeout(4000)
        except Exception as e:
            print(f"  submit ERR: {e}")
        page.screenshot(path=OUT_AFTER, full_page=True)
        browser.close()
    print(f"OK: {OUT_TOP} {OUT_AFTER}")


if __name__ == "__main__":
    sys.exit(main() or 0)
