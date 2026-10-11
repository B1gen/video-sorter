"""把视频移动到别的文件夹：规划目标路径、处理重名、执行移动。不含界面代码。"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set

from .models import VIDEO_SUFFIXES

SKIP_SAME_FOLDER = "已经在这个文件夹里"
SKIP_CONFLICT = "目标文件夹里已有同名文件"


@dataclass
class MovePlan:
    source: Path
    target: Optional[Path]  # None 表示跳过
    skip_reason: str = ""


@dataclass
class MoveResult:
    source: Path
    target: Optional[Path]
    error: str = ""
    skip_reason: str = ""

    @property
    def moved(self) -> bool:
        return self.target is not None and not self.error and not self.skip_reason


def path_key(path: Path) -> str:
    """Windows 路径不区分大小写，比较前统一一下。"""
    return os.path.normcase(os.path.abspath(str(path)))


def same_path(left: Path, right: Path) -> bool:
    return path_key(left) == path_key(right)


def find_conflicts(sources: Sequence[Path], folder: Path) -> List[Path]:
    """哪些文件移过去会撞名：目标里已有同名文件，或者这一批里有两个同名文件。"""
    conflicts = []
    taken: Set[str] = set()
    for source in sources:
        if same_path(source.parent, folder):
            continue
        target = folder / source.name
        key = path_key(target)
        if key in taken or target.exists():
            conflicts.append(source)
        taken.add(key)
    return conflicts


def plan_moves(sources: Sequence[Path], folder: Path, rename_conflicts: bool) -> List[MovePlan]:
    plans = []
    taken: Set[str] = set()
    for source in sources:
        if same_path(source.parent, folder):
            plans.append(MovePlan(source, None, SKIP_SAME_FOLDER))
            continue
        target = folder / source.name
        if path_key(target) in taken or target.exists():
            if not rename_conflicts:
                plans.append(MovePlan(source, None, SKIP_CONFLICT))
                continue
            target = unique_target(target, taken)
        taken.add(path_key(target))
        plans.append(MovePlan(source, target))
    return plans


def unique_target(target: Path, taken: Iterable[str] = ()) -> Path:
    """a.mp4 → a (1).mp4 → a (2).mp4 …，直到既不存在、也没被这一批占用。"""
    taken = set(taken)
    index = 1
    while True:
        candidate = target.with_name("{} ({}){}".format(target.stem, index, target.suffix))
        if path_key(candidate) not in taken and not candidate.exists():
            return candidate
        index += 1


def move_file(source: Path, target: Path) -> str:
    """移动一个文件，成功返回空字符串，失败返回原因。绝不覆盖已有文件。"""
    if not source.exists():
        return "源文件已不存在"
    if target.exists():
        return SKIP_CONFLICT
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
    except PermissionError:
        _remove_partial_copy(source, target)
        return "文件正被其他程序占用（比如播放器），或没有权限"
    except OSError as exc:
        _remove_partial_copy(source, target)
        return "移动失败：{}".format(exc.strerror or exc)
    return ""


def _remove_partial_copy(source: Path, target: Path) -> None:
    """跨盘移动是先复制再删除；复制到一半失败时，源文件还在，把残缺的目标删掉。"""
    if source.exists() and target.exists():
        try:
            target.unlink()
        except OSError:
            pass


def is_under_roots(path: Path, roots: Sequence[Path], recursive: bool) -> bool:
    """移动后的文件是否还在当前扫描范围内（决定它是否还留在列表里）。"""
    key = path_key(path)
    for root in roots:
        root_key = path_key(root)
        # 根目录也可能是单个视频文件（拖进来的是文件）；移走后它已不存在，所以按扩展名判断
        if root.is_file() or root.suffix.lower() in VIDEO_SUFFIXES:
            if key == root_key:
                return True
            continue
        if recursive:
            if key.startswith(root_key.rstrip(os.sep) + os.sep):
                return True
        elif path_key(path.parent) == root_key:
            return True
    return False


def subfolders(folder: Path, limit: int = 30) -> List[Path]:
    try:
        entries = [
            entry
            for entry in folder.iterdir()
            if entry.is_dir() and not entry.name.startswith((".", "$"))
        ]
    except OSError:
        return []
    return sorted(entries, key=lambda entry: entry.name.lower())[:limit]
