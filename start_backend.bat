@echo off
chcp 65001 > nul
:: 声明编码为 UTF-8 防止中文乱码

echo ===================================================
echo   DataViz Agent 后端服务正在启动中...
echo ===================================================

:: 自动检测虚拟环境
if exist .venv\Scripts\python.exe (
    set PYTHON_EXEC=.venv\Scripts\python.exe
) else if exist venv\Scripts\python.exe (
    set PYTHON_EXEC=venv\Scripts\python.exe
) else (
    set PYTHON_EXEC=python
)

echo 使用 Python 执行器: %PYTHON_EXEC%

:: 执行后端服务
%PYTHON_EXEC% main.py
pause
