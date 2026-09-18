"""扫描调度：一个线程负责遍历目录，一个线程池负责解码元信息和缩略图。"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from PySide6.QtCore import QObject, QRunnable, QThread, QThreadPool, Signal

from . import probe as probe_module
from .cache import ThumbnailCache
from .imaging import to_qimage
from .models import VIDEO_SUFFIXES, VideoInfo

BATCH_SIZE = 40
BATCH_INTERVAL = 0.2


class _WalkThread(QThread):
    batch = Signal(list)
    walkFinished = Signal(int)

    def __init__(self, roots: Sequence[Path], recursive: bool, cancel: threading.Event) -> None:
        super().__init__()
        self._roots = list(roots)
        self._recursive = recursive
        self._cancel = cancel

    def run(self) -> None:
        total = 0
        pending: List[Path] = []
        last_flush = time.monotonic()
        seen = set()

        for path in self._iter_videos():
            if self._cancel.is_set():
                break
            key = str(path).lower()
            if key in seen:
                continue
            seen.add(key)
            pending.append(path)
            total += 1
            now = time.monotonic()
            if len(pending) >= BATCH_SIZE or now - last_flush >= BATCH_INTERVAL:
                self.batch.emit(pending)
                pending = []
                last_flush = now

        if pending and not self._cancel.is_set():
            self.batch.emit(pending)
        self.walkFinished.emit(total)

    def _iter_videos(self) -> Iterable[Path]:
        for root in self._roots:
            if self._cancel.is_set():
                return
            if root.is_file():
                if _is_video(root):
                    yield root
                continue
            if not root.is_dir():
                continue
            for directory, subdirs, files in os.walk(str(root)):
                if self._cancel.is_set():
                    return
                subdirs[:] = [] if not self._recursive else [
                    name for name in subdirs if not name.startswith("$")
                ]
                for name in files:
                    candidate = Path(directory) / name
                    if _is_video(candidate):
                        yield candidate


class _ProbeSignals(QObject):
    ready = Signal(object, object)


class _ProbeTask(QRunnable):
    def __init__(
        self,
        path: Path,
        cache: ThumbnailCache,
        signals: _ProbeSignals,
        cancel: threading.Event,
        thumb_width: int,
        thumb_height: int,
    ) -> None:
        super().__init__()
        self._path = path
        self._cache = cache
        self._signals = signals
        self._cancel = cancel
        self._thumb_width = thumb_width
        self._thumb_height = thumb_height

    def run(self) -> None:
        if self._cancel.is_set():
            return
        try:
            cached = self._cache.load(self._path)
            if cached is not None:
                info, image = cached
                if not self._cancel.is_set():
                    self._signals.ready.emit(info, image)
                return
            result = probe_module.probe(self._path, self._thumb_width, self._thumb_height)
            image = to_qimage(result.thumbnail)
            info = result.info
        except Exception as exc:  # 单个坏文件不该影响整次扫描
            info = VideoInfo(path=self._path, error="解析失败：{}".format(exc))
            image = None
        self._cache.store(info, image)
        if not self._cancel.is_set():
            self._signals.ready.emit(info, image)


class ScanController(QObject):
    """把遍历、解码、进度汇总成界面可以直接消费的几个信号。"""

    videoReady = Signal(object, object)
    progress = Signal(int, int)
    started = Signal()
    scanFinished = Signal(bool)

    def __init__(
        self,
        cache: ThumbnailCache,
        thumb_width: int,
        thumb_height: int,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._cache = cache
        self._thumb_width = thumb_width
        self._thumb_height = thumb_height
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max(2, min(8, (os.cpu_count() or 4))))
        self._signals = _ProbeSignals(self)
        self._signals.ready.connect(self._on_probe_ready)
        self._cancel = threading.Event()
        self._walker: Optional[_WalkThread] = None
        self._total = 0
        self._done = 0
        self._walk_complete = False
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self, roots: Sequence[Path], recursive: bool) -> None:
        self.cancel()
        self._cancel = threading.Event()
        self._total = 0
        self._done = 0
        self._walk_complete = False
        self._running = True
        self.started.emit()
        self.progress.emit(0, 0)

        self._walker = _WalkThread(roots, recursive, self._cancel)
        self._walker.batch.connect(self._on_batch)
        self._walker.walkFinished.connect(self._on_walk_finished)
        self._walker.start()

    def cancel(self) -> None:
        if not self._running:
            return
        self._cancel.set()
        if self._walker is not None:
            self._walker.wait(3000)
            self._walker = None
        self._pool.clear()
        self._running = False
        self.scanFinished.emit(False)

    def wait_for_shutdown(self) -> None:
        self._cancel.set()
        if self._walker is not None:
            self._walker.wait(3000)
        self._pool.clear()
        self._pool.waitForDone(3000)

    def _on_batch(self, paths: List[Path]) -> None:
        if self._cancel.is_set():
            return
        self._total += len(paths)
        self.progress.emit(self._done, self._total)
        for path in paths:
            task = _ProbeTask(
                path,
                self._cache,
                self._signals,
                self._cancel,
                self._thumb_width,
                self._thumb_height,
            )
            self._pool.start(task)

    def _on_walk_finished(self, total: int) -> None:
        self._walk_complete = True
        self._total = total
        self.progress.emit(self._done, self._total)
        self._maybe_finish()

    def _on_probe_ready(self, info: VideoInfo, image) -> None:
        if self._cancel.is_set():
            return
        self._done += 1
        self.videoReady.emit(info, image)
        self.progress.emit(self._done, self._total)
        self._maybe_finish()

    def _maybe_finish(self) -> None:
        if self._running and self._walk_complete and self._done >= self._total:
            self._running = False
            self.scanFinished.emit(True)


def _is_video(path: Path) -> bool:
    if path.name.startswith("."):
        return False
    return path.suffix.lower() in VIDEO_SUFFIXES
