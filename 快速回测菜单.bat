@echo off
chcp 65001 > nul
title 快速回测工具
cls

echo.
echo ╔════════════════════════════════════════╗
echo ║      快速回测工具 v1.0                ║
echo ║   Pinbar多周期共振策略                 ║
echo ╚════════════════════════════════════════╝
echo.

call backend\venv\Scripts\activate.bat
python 快速回测.py

pause

