"""读取视频元信息并抽取缩略图。

优先用 ffprobe（若系统里有），它对可变帧率、旋转标记的处理最准；
没有 ffprobe 时退回 OpenCV 自带的解码器，功能不受影响。
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .models import VideoInfo

# Windows 下用 subprocess 调外部程序会闪一下黑框，加这个标志可以避免。
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_SUBPROCESS_TIMEOUT = 30


def _tool_path(name: str) -> str:
    """在程序目录、PyInstaller 解包目录和 PATH 里找 ffprobe / ffmpeg。"""
    exe = name + (".exe" if os.name == "nt" else "")
    roots: List[Path] = []
    bundle = getattr(sys, "_MEIPASS", "")
    if bundle:
        roots.append(Path(bundle))
    roots.append(Path(sys.argv[0]).resolve().parent if sys.argv and sys.argv[0] else Path.cwd())
    roots.append(Path(__file__).resolve().parent.parent)
    for root in roots:
        for candidate in (root / exe, root / "bin" / exe, root / "ffmpeg" / "bin" / exe):
            if candidate.is_file():
                return str(candidate)
    return shutil.which(name) or ""


FFPROBE = _tool_path("ffprobe")
FFMPEG = _tool_path("ffmpeg")

try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
except Exception:
    pass


@dataclass
class ProbeResult:
    info: VideoInfo
    thumbnail: Optional[np.ndarray] = None  # BGR，已按最大尺寸缩放


def probe(path: Path, thumb_width: int = 320, thumb_height: int = 180) -> ProbeResult:
    try:
        size_bytes = path.stat().st_size
    except OSError as exc:
        return ProbeResult(VideoInfo(path=path, error="无法读取文件：{}".format(exc)))

    info = VideoInfo(path=path, size_bytes=size_bytes)
    meta = _ffprobe(path) if FFPROBE else None
    frame = None

    capture = _open_capture(path)
    if capture is not None:
        try:
            if meta is None:
                meta = _capture_metadata(capture)
            frame = _grab_frame(capture, meta.get("duration") if meta else None)
        finally:
            capture.release()

    if meta is None and frame is None:
        info.error = "无法解码，可能缺少解码器或文件损坏"
        return ProbeResult(info)

    meta = meta or {}
    info.duration = meta.get("duration")
    info.fps = meta.get("fps")
    info.width = meta.get("width")
    info.height = meta.get("height")
    info.codec = meta.get("codec") or ""

    if frame is not None:
        frame = _match_orientation(frame, info.width, info.height, meta.get("rotation", 0))
        if not info.width or not info.height:
            info.height, info.width = frame.shape[0], frame.shape[1]

    if not info.duration and not info.width:
        info.error = "无法识别时长和分辨率"

    thumbnail = _fit(frame, thumb_width, thumb_height) if frame is not None else None
    if thumbnail is None and FFMPEG:
        fallback = _ffmpeg_frame(path, info.duration, thumb_width, thumb_height)
        thumbnail = _fit(fallback, thumb_width, thumb_height) if fallback is not None else None
    return ProbeResult(info, thumbnail)


# --------------------------------------------------------------------------- #
# ffprobe
# --------------------------------------------------------------------------- #


def _ffprobe(path: Path) -> Optional[dict]:
    command = [
        FFPROBE,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=_SUBPROCESS_TIMEOUT,
            creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0 or not completed.stdout:
        return None
    try:
        payload = json.loads(completed.stdout.decode("utf-8", "replace"))
    except ValueError:
        return None

    streams = payload.get("streams") or []
    if not streams:
        return None
    stream = streams[0]

    width = _as_int(stream.get("width"))
    height = _as_int(stream.get("height"))
    fps = _ratio(stream.get("avg_frame_rate")) or _ratio(stream.get("r_frame_rate"))
    duration = _as_float(stream.get("duration")) or _as_float(
        (payload.get("format") or {}).get("duration")
    )
    if not duration:
        frames = _as_int(stream.get("nb_frames"))
        if frames and fps:
            duration = frames / fps

    rotation = _rotation(stream)
    if rotation in (90, 270) and width and height:
        width, height = height, width

    return {
        "width": width,
        "height": height,
        "fps": fps,
        "duration": duration,
        "codec": stream.get("codec_name") or "",
        "rotation": rotation,
    }


def _rotation(stream: dict) -> int:
    for side_data in stream.get("side_data_list") or []:
        if "rotation" in side_data:
            return int(round(float(side_data["rotation"]))) % 360
    tags = stream.get("tags") or {}
    if "rotate" in tags:
        try:
            return int(round(float(tags["rotate"]))) % 360
        except (TypeError, ValueError):
            return 0
    return 0


def _ffmpeg_frame(
    path: Path, duration: Optional[float], width: int, height: int
) -> Optional[np.ndarray]:
    timestamp = _thumbnail_timestamp(duration)
    command = [
        FFMPEG,
        "-v",
        "error",
        "-ss",
        "{:.3f}".format(timestamp),
        "-i",
        str(path),
        "-frames:v",
        "1",
        "-vf",
        "scale={}:{}:force_original_aspect_ratio=decrease".format(width, height),
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "-",
    ]
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=_SUBPROCESS_TIMEOUT,
            creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0 or not completed.stdout:
        return None
    buffer = np.frombuffer(completed.stdout, dtype=np.uint8)
    return cv2.imdecode(buffer, cv2.IMREAD_COLOR)


# --------------------------------------------------------------------------- #
# OpenCV
# --------------------------------------------------------------------------- #


def _open_capture(path: Path):
    for candidate in _candidate_paths(path):
        capture = cv2.VideoCapture(candidate)
        if capture.isOpened():
            try:
                capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
            except Exception:
                pass
            return capture
        capture.release()
    return None


def _candidate_paths(path: Path) -> List[str]:
    """OpenCV 在 Windows 上对中文路径和超长路径支持不稳，额外准备几个备选写法。"""
    text = str(path)
    candidates = [text]
    if os.name != "nt":
        return candidates
    if any(ord(char) > 127 for char in text):
        short = _short_path(text)
        if short and short != text:
            candidates.append(short)
    if len(text) > 250 and not text.startswith("\\\\?\\"):
        candidates.append("\\\\?\\" + os.path.abspath(text))
    return candidates


def _short_path(text: str) -> str:
    try:
        buffer = ctypes.create_unicode_buffer(len(text) + 300)
        length = ctypes.windll.kernel32.GetShortPathNameW(text, buffer, len(buffer))
    except Exception:
        return ""
    return buffer.value if length else ""


def _capture_metadata(capture) -> dict:
    fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
    frames = capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
    width = _as_int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = _as_int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = frames / fps if fps > 0 and frames > 0 else None
    if fps <= 0 or fps > 1000:
        fps = None
    return {
        "width": width,
        "height": height,
        "fps": fps,
        "duration": duration,
        "codec": "",
        "rotation": 0,
    }


def _grab_frame(capture, duration: Optional[float]) -> Optional[np.ndarray]:
    timestamp = _thumbnail_timestamp(duration)
    if timestamp > 0:
        capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
        ok, frame = capture.read()
        if ok and frame is not None and frame.size:
            return frame
        capture.set(cv2.CAP_PROP_POS_MSEC, 0)
    for _ in range(5):
        ok, frame = capture.read()
        if ok and frame is not None and frame.size:
            return frame
    return None


def _thumbnail_timestamp(duration: Optional[float]) -> float:
    if not duration or duration <= 1.0:
        return 0.0
    return min(duration * 0.1, 10.0)


# --------------------------------------------------------------------------- #
# 图像处理
# --------------------------------------------------------------------------- #


def _match_orientation(
    frame: np.ndarray, width: Optional[int], height: Optional[int], rotation: int
) -> np.ndarray:
    """解码器有时不会应用旋转标记，这里让画面方向和元信息保持一致。"""
    if not width or not height:
        return frame
    frame_landscape = frame.shape[1] >= frame.shape[0]
    meta_landscape = width >= height
    if frame_landscape == meta_landscape:
        return frame
    if rotation in (270, -90):
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)


def _fit(frame: Optional[np.ndarray], max_width: int, max_height: int) -> Optional[np.ndarray]:
    if frame is None or not frame.size:
        return None
    height, width = frame.shape[:2]
    scale = min(max_width / float(width), max_height / float(height), 1.0)
    if scale >= 1.0:
        return frame
    target = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    return cv2.resize(frame, target, interpolation=cv2.INTER_AREA)


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #


def _as_int(value) -> Optional[int]:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _as_float(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _ratio(value) -> Optional[float]:
    if not value or not isinstance(value, str) or "/" not in value:
        return _as_float(value)
    try:
        fraction = Fraction(value)
    except (ValueError, ZeroDivisionError):
        return None
    return float(fraction) if fraction > 0 else None


def backend_summary() -> Tuple[str, str]:
    return (FFPROBE or "", FFMPEG or "")
