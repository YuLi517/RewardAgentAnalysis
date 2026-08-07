"""Pytest conftest — 把根目录加到 sys.path 让 `from scenario.xxx import ...` 工作
P1 期间必要, PR4 不会删 (适合 long-term)
"""
import sys
from pathlib import Path

# 把项目根目录加到 sys.path, 让 scenario/ skills/ tools/ 等顶层模块可 import
_ROOT = Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
