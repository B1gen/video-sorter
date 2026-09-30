"""鼠标悬停时在缩略图位置静音播放视频。

用 OpenCV 在后台线程解码，和缩略图走同一套解码器，不依赖 QtMultimedia。
解码跟不上原速时只 grab 不 retrieve，跳帧保证播放速度正常。
"""

from __future__ import annotations

import threading
import time
from typing import Optional, Tuple

import cv2
from PySide6.QtCore import QObject, Signal

from . import probe
from .imaging import to_qimage
from .models import VideoInfo

MAX_DISPLAY_FPS = 30.0
_DEFAULT_FPS = 25.0


class HoverPreview(QObject):
    """同一时间只播一个视频；start 会顶掉上一个。"""

    # (token, path, QImage, 播放进度 0~1)
    frameReady = Signal(int, object, object, float)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._token = 0
        self._stop: Optional[threading.Event] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def token(self) -> int:
        return self._token

    def start(self, info: VideoInfo, size: Tuple[int, int]) -> int:
        self.stop()
        self._token += 1
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            args=(self._token, info, size, self._stop),
            name="hover-preview",
            daemon=True,
        )
        self._thread.start()
        return self._token

    def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
        self._stop = None
        self._thread = None
        self._token += 1

    def shutdown(self, timeout: float = 1.0) -> None:
        thread = self._thread
        self.stop()
        if thread is not None:
            thread.join(timeout)

    def _run(
        self, token: int, info: VideoInfo, size: Tuple[int, int], stop: threading.Event
    ) -> None:
        capture = probe.open_capture(info.path)
        if capture is None:
            return
        try:
            _play(capture, token, info, size, stop, self.frameReady)
        except Exception:
            pass
        finally:
            capture.release()


def _play(capture, token: int, info: VideoInfo, size: Tuple[int, int], stop, signal) -> None:
    width, height = size
    fps = capture.get(cv2.CAP_PROP_FPS) or info.fps or _DEFAULT_FPS
    if not 1.0 <= fps <= 240.0:
        fps = info.fps or _DEFAULT_FPS
    frame_interval = 1.0 / fps
    display_interval = 1.0 / min(fps, MAX_DISPLAY_FPS)
    duration = info.duration or 0.0

    start_at = probe.thumbnail_timestamp(info.duration)
    if start_at > 0:
        capture.set(cv2.CAP_PROP_POS_MSEC, start_at * 1000.0)

    # due：当前这一帧按原速应该出现的时刻
    due = time.monotonic()
    last_shown = float("-inf")
    looped_without_frame = False
    while not stop.is_set():
        if not capture.grab():
            if looped_without_frame:
                return
            looped_without_frame = True
            capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            due = time.monotonic()
            continue
        looped_without_frame = False

        now = time.monotonic()
        if now - due > 1.0:
            due = now
        late = now - due > frame_interval
        if not late and due - last_shown >= display_interval * 0.99:
            if due > now and stop.wait(due - now):
                return
            _show(capture, token, info, width, height, duration, signal)
            last_shown = due
        elif due > now and stop.wait(due - now):
            return
        due += frame_interval


def _show(capture, token, info: VideoInfo, width, height, duration, signal) -> None:
    ok, frame = capture.retrieve()
    if not ok or frame is None or not frame.size:
        return
    frame = probe.match_orientation(frame, info.width, info.height, 0)
    image = to_qimage(probe.fit(frame, width, height))
    if image is None:
        return
    position = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
    progress = min(1.0, max(0.0, position / duration)) if duration > 0 else 0.0
    signal.emit(token, info.path, image, progress)
