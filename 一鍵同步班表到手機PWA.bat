@echo off
chcp 65001 >nul
cd /d "D:\GitHub\Line_bot"

python sync_wheel.py --push

echo.
pause