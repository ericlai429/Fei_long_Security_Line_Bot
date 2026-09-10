@echo off
chcp 65001 >nul
cd /d "%~dp0.."

python pull_from_cloud\pull_and_sync.py

echo.
pause