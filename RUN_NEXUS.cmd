@echo off
cd /d %~dp0
title NEXUS v0.9.20 Stabilization & Reliability
echo Starting MT5 lifecycle monitor...
start "NEXUS MT5 MONITOR" /min cmd /k "cd /d %~dp0 && python MT5_MONITOR.py"
timeout /t 2 /nobreak >nul
echo Starting NEXUS Command Center...
python -m streamlit run Dashboard\app.py
pause
