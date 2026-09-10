@echo off
chcp 65001 >nul
title 飛龍保全 ｜ 雲端排班表自動抓取與 GitHub PWA 同步
cd /d "%~dp0.."

echo ===============================================================
echo   🚀 飛龍保全 ｜ 正在自動抓取 Google 雲端班表最新副本...
echo   網址: https://docs.google.com/spreadsheets/d/18TFnTI-RCjVBnW8vA7L5K0QClhXsguWL8RPUK8gVQsU/edit?gid=1125126855#gid=1125126855
echo ===============================================================
echo.

python pull_from_cloud\pull_and_sync.py

echo.
echo ===============================================================
echo   📌 執行完成！已生成日期副本並自動推送到 GitHub main 分支！
echo   🌐 即時 PWA 班表將在 10 秒內全球自動對齊最新內容。
echo ===============================================================
echo.
pause