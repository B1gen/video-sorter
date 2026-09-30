"""打包成可双击运行的程序：python packaging/build.py [--onefile] [--zip]

build_windows.bat 和 GitHub Actions 都调用这个脚本，打包参数只维护这一份。
  默认       文件夹版：dist/VideoSorter/VideoSorter.exe，启动快
  --onefile  单文件版：dist/VideoSorter.exe，方便拷走，每次启动要先解压，慢几秒
  --zip      额外把文件夹版压缩成 dist/VideoSorter-<版本>-windows.zip
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from video_sorter import __version__  # noqa: E402

NAME = "VideoSorter"
BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist"

# 用不到的大模块，排除掉能让体积小一大截
EXCLUDED_MODULES = (
    "tkinter",
    "matplotlib",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtQuick",
    "PySide6.QtQml",
    "PySide6.Qt3DCore",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia",
    "PySide6.QtPdf",
)


def make_icon() -> Path:
    from PySide6.QtGui import QGuiApplication

    from video_sorter.icon import render

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication.instance() or QGuiApplication([])
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    target = BUILD_DIR / "icon.png"
    if not render(256).save(str(target), "PNG"):
        raise SystemExit("图标生成失败")
    del app
    return target


def write_version_file() -> Path:
    """Windows 资源管理器里「属性 → 详细信息」显示的版本号。"""
    parts = [int(part) for part in __version__.split(".")[:3]] + [0]
    parts += [0] * (4 - len(parts))
    numbers = tuple(parts[:4])
    target = BUILD_DIR / "version_info.txt"
    target.write_text(
        _VERSION_TEMPLATE.format(numbers=numbers, text=__version__, name=NAME),
        "utf-8",
    )
    return target


def build(onefile: bool) -> Path:
    import PyInstaller.__main__

    icon = make_icon()
    arguments = [
        str(ROOT / "main.py"),
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onefile" if onefile else "--onedir",
        "--name",
        NAME,
        "--icon",
        str(icon),
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR / ("onefile" if onefile else "onedir")),
        "--specpath",
        str(BUILD_DIR),
        "--collect-all",
        "av",
    ]
    if sys.platform == "win32":
        arguments += ["--version-file", str(write_version_file())]
    for module in EXCLUDED_MODULES:
        arguments += ["--exclude-module", module]
    PyInstaller.__main__.run(arguments)

    suffix = ".exe" if sys.platform == "win32" else ""
    output = DIST_DIR / (NAME + suffix) if onefile else DIST_DIR / NAME / (NAME + suffix)
    if not output.exists():
        raise SystemExit("打包失败，没有生成 {}".format(output))
    return output


def zip_folder() -> Path:
    base = DIST_DIR / "{}-{}-windows".format(NAME, __version__)
    archive = shutil.make_archive(str(base), "zip", root_dir=str(DIST_DIR), base_dir=NAME)
    return Path(archive)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--onefile", action="store_true", help="打包成单个 exe")
    parser.add_argument("--zip", action="store_true", help="把文件夹版压缩成 zip")
    args = parser.parse_args()

    output = build(args.onefile)
    print("生成：{}".format(output))
    if args.zip and not args.onefile:
        print("压缩包：{}".format(zip_folder()))
    return 0


_VERSION_TEMPLATE = """VSVersionInfo(
  ffi=FixedFileInfo(filevers={numbers}, prodvers={numbers}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('080404b0', [
      StringStruct('CompanyName', '{name}'),
      StringStruct('FileDescription', '视频分类器'),
      StringStruct('FileVersion', '{text}'),
      StringStruct('InternalName', '{name}'),
      StringStruct('OriginalFilename', '{name}.exe'),
      StringStruct('ProductName', '视频分类器'),
      StringStruct('ProductVersion', '{text}')])]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""


if __name__ == "__main__":
    raise SystemExit(main())
