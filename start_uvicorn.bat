@echo off
REM ============================================================
REM RewardAgentAnalysis UAT 启动脚本 (Windows)
REM 双击即可, 跟脚本所在目录无关
REM ============================================================
cd /d "%~dp0"
REM 第一次启动会自动创建 data/rewarddb.db
REM 业务侧 (commission / 树视图) 不需要 LLM key, .env 不配也能跑
REM chat 端点要 LLM key 才能用 (LLM_PROVIDERS=xxx 配 .env 即可启用)
python main.py --reload --host 0.0.0.0 --port 38080
pause
