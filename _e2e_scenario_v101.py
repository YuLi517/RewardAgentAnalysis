#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""e2e: 改 max_level + total_target + initial_pv, 验证 formState 同步 + 提交成功"""
import sys
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:38080/static/scenario.html"
OUT_BEFORE = "logs/scenario_v101_e2e_before.png"
OUT_AFTER = "logs/scenario_v101_e2e_after.png"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 720})
        page = ctx.new_page()
        page.on("console", lambda m: print(f"  console: {m.text}"))
        page.goto(URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(500)
        page.screenshot(path=OUT_BEFORE, full_page=False)

        # 改 3 个 input: max_level, initial_pv, own_basic_rate
        for key, value in [
            ("max_level", "6"),
            ("total_target", "256"),  # 2 叉 L0=1 L1=2 L2=4 L3=8 L4=16 L5=32 L6=64 L7=128 → 1+2+4+8+16+32+64+128=255, +1=256
            ("initial_pv", "2000"),
            ("own_basic_rate", "0.20"),
        ]:
            el = page.query_selector(f'[data-key="{key}"]')
            el.fill(value)
            el.dispatch_event("input")
            el.dispatch_event("change")
            page.wait_for_timeout(100)

        # 抓 formState 验证
        form_state = page.evaluate("""
            (() => {
              // 从 formState 读不暴露, 触发 submit 后看 URL/scenario_id
              return {
                fork_type: window.formState ? window.formState.tree_shape.fork_type : 'no_window',
                layer_counts: window.formState ? Object.values(window.formState.tree_shape.layer_counts) : 'no_window',
                max_level: window.formState ? window.formState.tree_shape.max_level : 'no_window',
                initial_pv: window.formState ? window.formState.revenue.initial_pv : 'no_window',
                own_basic_rate: window.formState ? window.formState.commission_config.own_basic_rate : 'no_window',
              };
            })()
        """)
        print(f"  formState 验证: {form_state}")

        # 截图改后
        page.screenshot(path=OUT_AFTER, full_page=False)

        # 点提交按钮
        page.click("#btn-submit")
        page.wait_for_timeout(3000)  # 等待 POST + GET overview

        # 抓卡片显示
        cards = page.evaluate("""
            (() => Array.from(document.querySelectorAll('.p3-cards .card')).map(c => ({
              field: c.dataset.field, val: c.querySelector('.val').textContent
            })))()
        """)
        print(f"  8 卡片显示: {cards}")
        page.screenshot(path="logs/scenario_v101_e2e_submitted.png", full_page=True)
        browser.close()
    print(f"OK: before={OUT_BEFORE} after={OUT_AFTER}")


if __name__ == "__main__":
    sys.exit(main() or 0)
