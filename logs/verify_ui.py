"""verify 4 scenario 按钮 UI 改造"""
import requests

r = requests.get("http://127.0.0.1:38080/static/index.html", timeout=5)
print(f"status: {r.status_code}")
text = r.text
print(f"scenario-section 出现次数: {text.count('scenario-section')}")
print(f"scenario-card 出现次数: {text.count('scenario-card')}")
print(f"nav-link 出现次数: {text.count('nav-link')}")
print(f'target="_blank" 出现次数: {text.count(chr(34) + "_blank" + chr(34))}')
print(f"场景工具 出现次数: {text.count('场景工具')}")
print()
# 验证 4 卡片 URL
for url in ["/static/scenario.html", "/static/scenario_compare.html",
            "/static/scenario_library.html", "/static/scenario_pdf.html"]:
    print(f"  {url}: {text.count(url)} 处")
print()
# 验证 topbar .controls 不再有 nav-link
ctrl_start = text.find('class="controls"')
ctrl_end = text.find('</div>', ctrl_start) if ctrl_start > 0 else -1
if ctrl_start > 0 and ctrl_end > 0:
    ctrl = text[ctrl_start:ctrl_end + 6]
    print(f"topbar .controls 内容: {len(ctrl)} chars")
    print(f"  含 nav-link: {'nav-link' in ctrl}")
    print(f"  含 cmdKBtn: {'cmdKBtn' in ctrl}")
    print(f"  含 provider: {'provider' in ctrl}")
    print(f"  含 theme: {'theme' in ctrl}")
