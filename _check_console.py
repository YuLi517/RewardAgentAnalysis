#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""抓取 page console error 看 BorderBeam 是否加载成功"""
import sys
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:5173/"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        page.on("pageerror", lambda e: print(f"  PAGE ERROR: {e}"))
        page.on("console", lambda m: print(f"  CONSOLE {m.type}: {m.text}"))
        page.on("requestfailed", lambda r: print(f"  REQ FAILED: {r.url} - {r.failure}"))
        page.goto(URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)

        # 检查 BorderBeam 内部 DOM 结构
        beam_info = page.evaluate("""
            (() => {
              const wraps = document.querySelectorAll('.beam-wrap');
              if (!wraps.length) return { count: 0 };
              const w = wraps[0];
              const bloom = w.querySelector('[data-beam-bloom]');
              const allDivs = w.querySelectorAll('div');
              return {
                wrapCount: wraps.length,
                allDivsCount: allDivs.length,
                bloomFound: !!bloom,
                bloomStyle: bloom ? bloom.style.cssText.slice(0, 200) : 'none',
                bloomComputed: bloom ? {
                  position: getComputedStyle(bloom).position,
                  width: bloom.offsetWidth,
                  height: bloom.offsetHeight,
                  bg: getComputedStyle(bloom).background.slice(0, 200),
                  opacity: getComputedStyle(bloom).opacity,
                  filter: getComputedStyle(bloom).filter,
                  zIndex: getComputedStyle(bloom).zIndex,
                } : null,
                w_overflow: getComputedStyle(w).overflow,
              };
            })()
        """)
        print("  DOM: " + repr(beam_info)[:2000])
        browser.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
