"""在系统文件管理器里定位 / 打开文件。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def reveal_in_file_manager(path: Path) -> bool:
    """打开文件所在文件夹并选中该文件。"""
    if not path.exists():
        return False
    try:
        if sys.platform == "win32":
            # 必须整条命令传字符串：路径带空格时 explorer 只认自己加的这对引号。
            command = 'explorer /select,"{}"'.format(os.path.normpath(str(path)))
            subprocess.Popen(command, creationflags=_NO_WINDOW)
            return True
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
            return True
        subprocess.Popen(["xdg-open", str(path.parent)])
        return True
    except OSError:
        return False


def open_file(path: Path) -> bool:
    """用系统默认播放器打开视频。"""
    if not path.exists():
        return False
    if sys.platform == "win32":
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
            return True
        except OSError:
            return False
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
