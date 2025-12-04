@echo off
chcp 65001 > nul
title 查看回测图表
cls

echo.
echo ========================================
echo    回测结果可视化
echo ========================================
echo.

call backend\venv\Scripts\activate.bat
python visualize_backtest.py

echo.
echo 正在打开图表...
echo.

REM 打开生成的图片
if exist backtest_report_summary.png start backtest_report_summary.png
if exist backtest_equity_curve.png start backtest_equity_curve.png
if exist backtest_trade_distribution.png start backtest_trade_distribution.png
if exist backtest_monthly_returns.png start backtest_monthly_returns.png

echo.
pause

