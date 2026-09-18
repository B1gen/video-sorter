@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 视频分类器

if not exist ".venv\Scripts\pythonw.exe" (
    echo 第一次运行，正在创建虚拟环境并安装依赖，请稍等...
    py -3 -m venv .venv
    if errorlevel 1 python -m venv .venv
    if errorlevel 1 (
        echo.
        echo 没有找到 Python。请先到 https://www.python.org/downloads/windows/ 安装 Python 3.9 以上版本，
        echo 安装时记得勾选 "Add python.exe to PATH"，然后重新双击本文件。
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo 依赖安装失败，请检查网络后重试。
        pause
        exit /b 1
    )
)

start "" ".venv\Scripts\pythonw.exe" main.py
