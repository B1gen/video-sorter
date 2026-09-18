@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 打包 视频分类器

rem 用法：
rem   build_windows.bat           打包成文件夹（启动快，推荐）-> dist\VideoSorter\VideoSorter.exe
rem   build_windows.bat onefile   打包成单个 exe（方便拷走，首次启动慢几秒）-> dist\VideoSorter.exe

if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 python -m venv .venv
    if errorlevel 1 (
        echo 没有找到 Python，请先安装 Python 3.9 以上版本。
        pause
        exit /b 1
    )
)

set PY=.venv\Scripts\python.exe
"%PY%" -m pip install --upgrade pip
"%PY%" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo 依赖安装失败。
    pause
    exit /b 1
)

set MODE=--onedir
if /i "%1"=="onefile" set MODE=--onefile

"%PY%" -m PyInstaller --noconfirm --clean --windowed %MODE% --name VideoSorter ^
    --exclude-module tkinter ^
    --exclude-module PySide6.QtWebEngineCore ^
    --exclude-module PySide6.QtQuick ^
    --exclude-module PySide6.QtQml ^
    --exclude-module PySide6.Qt3DCore ^
    --exclude-module PySide6.QtCharts ^
    --exclude-module PySide6.QtDataVisualization ^
    --exclude-module PySide6.QtMultimedia ^
    --exclude-module matplotlib ^
    main.py
if errorlevel 1 (
    echo 打包失败。
    pause
    exit /b 1
)

echo.
echo 打包完成，可执行文件在 dist 目录里。
echo 如果想让程序识别得更准（可变帧率、特殊编码），把 ffmpeg 的 ffprobe.exe 和 ffmpeg.exe
echo 放到 exe 同目录，或放进同目录的 bin 文件夹，程序会自动识别。
pause
