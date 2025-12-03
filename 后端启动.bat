@echo off
chcp 65001 > nul
title Candle Auto Trader - 后端服务
cls

echo.
echo ========================================
echo     Candle Auto Trader - 后端服务
echo ========================================
echo.

:: 设置代理
set HTTP_PROXY=http://127.0.0.1:7890
set HTTPS_PROXY=http://127.0.0.1:7890

:: 进入后端目录
cd backend

:: 激活虚拟环境并启动
echo [启动中] 正在启动后端服务...
call venv\Scripts\activate
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

:: 如果服务停止
echo.
echo 后端服务已停止
pause

