from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

VIDEO_SUFFIXES = frozenset(
    {
        ".mp4",
        ".m4v",
        ".mov",
        ".mkv",
        ".webm",
        ".avi",
        ".wmv",
        ".flv",
        ".f4v",
        ".mpg",
        ".mpeg",
        ".mpe",
        ".m2v",
        ".ts",
        ".mts",
        ".m2ts",
        ".vob",
        ".3gp",
        ".3g2",
        ".asf",
        ".rm",
        ".rmvb",
        ".ogv",
        ".divx",
        ".mxf",
        ".dv",
    }
)


@dataclass
class VideoInfo:
    """一个视频文件的原始信息，不含任何 Qt 依赖。"""

    path: Path
    size_bytes: int = 0
    duration: Optional[float] = None
    fps: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    codec: str = ""
    error: str = ""
    # None 表示没能识别；audio_silent 只有装了 ffmpeg 才能测出来
    has_audio: Optional[bool] = None
    audio_silent: Optional[bool] = None

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def is_valid(self) -> bool:
        return not self.error and bool(self.duration or self.width)

    def to_dict(self) -> dict:
        return {
            "size_bytes": self.size_bytes,
            "duration": self.duration,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "codec": self.codec,
            "error": self.error,
            "has_audio": self.has_audio,
            "audio_silent": self.audio_silent,
        }

    @classmethod
    def from_dict(cls, path: Path, data: dict) -> "VideoInfo":
        return cls(
            path=path,
            size_bytes=int(data.get("size_bytes") or 0),
            duration=data.get("duration"),
            fps=data.get("fps"),
            width=data.get("width"),
            height=data.get("height"),
            codec=data.get("codec") or "",
            error=data.get("error") or "",
            has_audio=data.get("has_audio"),
            audio_silent=data.get("audio_silent"),
        )


@dataclass
class VideoLabels:
    """分类标签，由 classify 模块根据阈值计算得到。"""

    duration: str = "未知时长"
    fps: str = "未知帧率"
    resolution: str = "未知分辨率"
    orientation: str = ""
    audio: str = "声音未知"
    duration_rank: float = float("inf")
    fps_rank: float = float("inf")
    resolution_rank: float = float("inf")
    audio_rank: float = float("inf")
