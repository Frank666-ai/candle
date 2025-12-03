@echo off
chcp 65001 > nul
title Candle Auto Trader - 前端界面
cls

echo.
echo ========================================
echo     Candle Auto Trader - 前端界面
echo ========================================
echo.

:: 进入前端目录
cd frontend

:: 启动前端
echo [启动中] 正在启动前端服务...
npm run dev

:: 如果服务停止
echo.
echo 前端服务已停止
pause

