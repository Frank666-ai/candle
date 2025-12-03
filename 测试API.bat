@echo off
chcp 65001 > nul
title 测试API Key
cls
echo.
echo 测试新的API Key...
echo.

cd backend
call venv\Scripts\activate

python 用官方SDK测试.py

cd ..
echo.
pause

