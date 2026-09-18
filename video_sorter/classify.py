"""分类规则：时长 / 帧率 / 分辨率的分档逻辑。

想改分类档位，直接改本文件顶部的三张表即可，界面会自动跟着变。
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from .models import VideoInfo, VideoLabels

# (上限秒数, 档位名称)：时长小于等于上限即归入该档。
DURATION_BUCKETS: Sequence[Tuple[float, str]] = (
    (5, "≤ 5 秒"),
    (10, "5–10 秒"),
    (20, "10–20 秒"),
    (30, "20–30 秒"),
    (60, "30 秒 – 1 分钟"),
    (120, "1 – 2 分钟"),
    (300, "2 – 5 分钟"),
    (600, "5 – 10 分钟"),
    (1800, "10 – 30 分钟"),
)
DURATION_OVERFLOW_LABEL = "> 30 分钟"

# 实际时长常有 10.03 秒这类误差，允许略微超过档位上限仍算同一档。
DURATION_SNAP_SECONDS = 0.6

# 标准帧率；实测帧率落在 ±2% 内就归到这些整数值上（29.97 → 30，59.94 → 60）。
STANDARD_FPS: Sequence[int] = (12, 15, 24, 25, 30, 48, 50, 60, 75, 90, 100, 120, 144, 165, 200, 240)
FPS_TOLERANCE = 0.02

# 以短边像素判定分辨率档位，±3% 内归到标准档。
RESOLUTION_STEPS: Sequence[Tuple[int, str]] = (
    (144, "144p"),
    (240, "240p"),
    (360, "360p"),
    (480, "480p"),
    (540, "540p"),
    (576, "576p"),
    (720, "720p"),
    (900, "900p"),
    (1080, "1080p"),
    (1200, "1200p"),
    (1260, "1260p"),
    (1440, "1440p (2K)"),
    (1600, "1600p"),
    (2160, "2160p (4K)"),
    (2880, "2880p (5K)"),
    (3384, "3384p (6K)"),
    (4320, "4320p (8K)"),
)
RESOLUTION_TOLERANCE = 0.03

UNKNOWN_DURATION = "未知时长"
UNKNOWN_FPS = "未知帧率"
UNKNOWN_RESOLUTION = "未知分辨率"

# 未知档位在分类树里排到最后。
UNKNOWN_RANK = float("inf")

# 界面上的分组方式：(标识, 显示名, 使用的维度顺序)
GROUP_MODES: Sequence[Tuple[str, str, Tuple[str, ...]]] = (
    ("duration", "时长", ("duration",)),
    ("fps", "帧率", ("fps",)),
    ("resolution", "分辨率", ("resolution",)),
    ("resolution_fps", "分辨率 → 帧率", ("resolution", "fps")),
    ("resolution_duration", "分辨率 → 时长", ("resolution", "duration")),
    ("duration_fps", "时长 → 帧率", ("duration", "fps")),
    ("all", "分辨率 → 帧率 → 时长", ("resolution", "fps", "duration")),
)


def duration_label(seconds: Optional[float]) -> Tuple[str, float]:
    if not seconds or seconds <= 0:
        return UNKNOWN_DURATION, UNKNOWN_RANK
    for index, (limit, label) in enumerate(DURATION_BUCKETS):
        if seconds <= limit + DURATION_SNAP_SECONDS:
            return label, float(index)
    return DURATION_OVERFLOW_LABEL, float(len(DURATION_BUCKETS))


def fps_label(fps: Optional[float]) -> Tuple[str, float]:
    if not fps or fps <= 0:
        return UNKNOWN_FPS, UNKNOWN_RANK
    for standard in STANDARD_FPS:
        if abs(fps - standard) <= standard * FPS_TOLERANCE:
            return "{} fps".format(standard), float(standard)
    return "{:g} fps".format(round(fps, 2)), float(fps)


def resolution_label(width: Optional[int], height: Optional[int]) -> Tuple[str, float, str]:
    if not width or not height:
        return UNKNOWN_RESOLUTION, UNKNOWN_RANK, ""
    short_side = min(width, height)
    if width > height:
        orientation = "横屏"
    elif width < height:
        orientation = "竖屏"
    else:
        orientation = "方形"
    for step, label in RESOLUTION_STEPS:
        if abs(short_side - step) <= step * RESOLUTION_TOLERANCE:
            return label, float(step), orientation
    return "{}p".format(short_side), float(short_side), orientation


def labels_for(info: VideoInfo) -> VideoLabels:
    duration_text, duration_rank = duration_label(info.duration)
    fps_text, fps_rank = fps_label(info.fps)
    resolution_text, resolution_rank, orientation = resolution_label(info.width, info.height)
    return VideoLabels(
        duration=duration_text,
        fps=fps_text,
        resolution=resolution_text,
        orientation=orientation,
        duration_rank=duration_rank,
        fps_rank=fps_rank,
        resolution_rank=resolution_rank,
    )


def group_path(labels: VideoLabels, dimensions: Sequence[str]) -> List[str]:
    """返回该视频在分类树中的层级路径，例如 ["1080p", "60 fps"]。"""
    values = {
        "duration": labels.duration,
        "fps": labels.fps,
        "resolution": labels.resolution,
    }
    return [values[dimension] for dimension in dimensions]


def rank_of(labels: VideoLabels, dimension: str) -> float:
    ranks = {
        "duration": labels.duration_rank,
        "fps": labels.fps_rank,
        "resolution": labels.resolution_rank,
    }
    return ranks[dimension]


def dimensions_for_mode(mode: str) -> Tuple[str, ...]:
    for key, _name, dimensions in GROUP_MODES:
        if key == mode:
            return dimensions
    return GROUP_MODES[0][2]


def format_duration(seconds: Optional[float]) -> str:
    if not seconds or seconds <= 0:
        return "--:--"
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return "{}:{:02d}:{:02d}".format(hours, minutes, secs)
    return "{}:{:02d}".format(minutes, secs)


def format_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return "{:.1f} {}".format(size, unit) if unit != "B" else "{:.0f} B".format(size)
        size /= 1024
    return "{:.1f} TB".format(size)
