@echo off
chcp 65001 > nul
title BTC回测 - Pinbar多周期共振 + 1H移动止损
cls
echo.
echo ========================================
echo    BTC 回测
echo    策略: Pinbar多周期共振 + 1H移动止损
echo ========================================
echo.
echo 正在运行回测...
echo.

call venv\Scripts\activate
python backtest_btc.py

echo.
echo ========================================
echo 回测完成！
echo ========================================
echo.
echo 生成的文件:
echo   - backtest_trades_btc.csv      详细交易记录
echo   - backtest_equity_btc.csv      权益曲线
echo   - backtest_report_btc.json     回测报告
echo.
pause

