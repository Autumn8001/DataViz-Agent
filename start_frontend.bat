@echo off
chcp 65001 > nul
:: 声明编码为 UTF-8 防止中文乱码

echo ===================================================
echo   DataViz Agent 前端开发服务器正在启动中...
echo ===================================================

cd frontend
npm run dev
pause
