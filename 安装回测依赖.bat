@echo off
chcp 65001 > nul
title 安装回测依赖
cls

echo.
echo ========================================
echo    安装回测所需依赖
echo ========================================
echo.
echo 正在安装以下库:
echo   - matplotlib (图表绘制)
echo   - pandas (数据处理)
echo   - numpy (数值计算)
echo   - ccxt (交易所API)
echo.
echo 请稍候...
echo.

cd backend
call venv\Scripts\activate

echo 升级 pip...
python -m pip install --upgrade pip

echo.
echo 安装依赖包...
pip install matplotlib pandas numpy ccxt>=4.0.0

echo.
echo ========================================
echo 安装完成！
echo.
echo 现在可以运行回测了，请执行:
echo   运行BNB回测.bat
echo ========================================
echo.

pause

