@echo off
title DORIMI 网页控制台
cd /d "%~dp0"
echo ==============================================================
echo   DORIMI 网页控制台
echo ==============================================================
echo.
echo 正在启动本地服务并打开浏览器...
echo 关闭这个窗口即停止服务。
echo.
"C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe" -u gateway.py
pause
