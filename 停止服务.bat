@echo off
chcp 65001 > nul
title Candle Auto Trader - 停止所有服务
cls
echo.
echo ========================================
echo   正在停止 Candle Auto Trader 所有服务
echo ========================================
echo.

:: 关闭端口 8000 的进程（后端）
echo [1/2] 关闭后端服务（端口 8000）...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000"') do (
    taskkill /F /PID %%a > nul 2>&1
)

:: 关闭端口 5173 的进程（前端）
echo [2/2] 关闭前端服务（端口 5173）...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173"') do (
    taskkill /F /PID %%a > nul 2>&1
)

echo.
echo ========================================
echo           所有服务已停止！
echo ========================================
echo.
echo [提示] 如需重新启动，请分别运行：
echo   - 后端启动.bat
echo   - 前端启动.bat
echo.

timeout /t 3 /nobreak > nul
exit

