@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 打包 视频分类器
set PYTHONUTF8=1

rem 用法：
rem   build_windows.bat           打包成文件夹（启动快）-> dist\VideoSorter\VideoSorter.exe
rem   build_windows.bat onefile   打包成单个 exe（方便拷走，首次启动慢几秒）-> dist\VideoSorter.exe
rem 打包参数都在 packaging\build.py 里；GitHub 上每次合并到 main 也会自动打包，见 README。

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
"%PY%" -m pip install -r requirements.txt pyinstaller pillow
if errorlevel 1 (
    echo 依赖安装失败。
    pause
    exit /b 1
)

if /i "%1"=="onefile" (
    "%PY%" packaging\build.py --onefile
) else (
    "%PY%" packaging\build.py --zip
)
if errorlevel 1 (
    echo 打包失败。
    pause
    exit /b 1
)

echo.
echo 打包完成，可执行文件在 dist 目录里，双击 VideoSorter.exe 即可运行。
pause
