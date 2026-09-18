"""元信息 + 缩略图的磁盘缓存，让第二次扫描同一个文件夹几乎瞬间完成。"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtCore import QStandardPaths
from PySide6.QtGui import QImage

from .models import VideoInfo

CACHE_VERSION = 1


class ThumbnailCache:
    def __init__(self, thumb_width: int, thumb_height: int, enabled: bool = True) -> None:
        self.thumb_width = thumb_width
        self.thumb_height = thumb_height
        self.enabled = enabled
        self.root = _cache_root()

    def load(self, path: Path) -> Optional[Tuple[VideoInfo, Optional[QImage]]]:
        if not self.enabled:
            return None
        key = self._key(path)
        if key is None:
            return None
        meta_file = self._file(key, "json")
        if not meta_file.is_file():
            return None
        try:
            data = json.loads(meta_file.read_text("utf-8"))
        except (OSError, ValueError):
            return None
        info = VideoInfo.from_dict(path, data)
        image = None
        thumb_file = self._file(key, "jpg")
        if thumb_file.is_file():
            loaded = QImage(str(thumb_file))
            if not loaded.isNull():
                image = loaded
        return info, image

    def store(self, info: VideoInfo, image: Optional[QImage]) -> None:
        if not self.enabled:
            return
        key = self._key(info.path)
        if key is None:
            return
        meta_file = self._file(key, "json")
        try:
            meta_file.parent.mkdir(parents=True, exist_ok=True)
            meta_file.write_text(json.dumps(info.to_dict()), "utf-8")
        except OSError:
            return
        if image is not None and not image.isNull():
            image.save(str(self._file(key, "jpg")), "JPG", 85)

    def clear(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def size_bytes(self) -> int:
        total = 0
        for item in self.root.rglob("*"):
            if item.is_file():
                try:
                    total += item.stat().st_size
                except OSError:
                    continue
        return total

    def _key(self, path: Path) -> Optional[str]:
        try:
            stat = path.stat()
        except OSError:
            return None
        raw = "{}|{}|{}|{}x{}|v{}".format(
            str(path.resolve()).lower(),
            int(stat.st_mtime),
            stat.st_size,
            self.thumb_width,
            self.thumb_height,
            CACHE_VERSION,
        )
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _file(self, key: str, suffix: str) -> Path:
        return self.root / key[:2] / "{}.{}".format(key, suffix)


def _cache_root() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.CacheLocation)
    root = Path(base) if base else Path.home() / ".video_sorter_cache"
    return root / "thumbnails"
