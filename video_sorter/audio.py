"""用 PyAV（pip 包自带 FFmpeg 库）识别音轨并判断是否静音，不需要另外装 ffmpeg。

静音的判定看“最响的一小段”的 RMS 音量，而不是单个采样的峰值：
底噪、电流声的峰值常到 -40 dB，但听起来就是没声音。
所有音轨都安静才算静音；有一条音轨有声音就算有声音。
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

try:
    import av
except ImportError:  # 没装 PyAV 时由 probe 退回 ffmpeg / 读文件头
    av = None

# 最响的一段（约 20~40 ms，一个音频帧）RMS 低于这个值就算没声音
SILENCE_THRESHOLD_DB = -45.0
# 时长不超过这个值就从头到尾全部分析；更长的视频均匀抽 SAMPLE_COUNT 段，每段 SAMPLE_SECONDS 秒
FULL_SCAN_SECONDS = 600.0
SAMPLE_COUNT = 60
SAMPLE_SECONDS = 10.0

_THRESHOLD_POWER = 10 ** (SILENCE_THRESHOLD_DB / 10.0)


def available() -> bool:
    return av is not None


def version() -> str:
    return getattr(av, "__version__", "") if av is not None else ""


def inspect(path: Path, duration: Optional[float] = None) -> Tuple[Optional[bool], Optional[bool]]:
    """返回 (有没有音轨, 是否静音)；识别不了的项为 None。"""
    if av is None:
        return None, None
    try:
        container = av.open(str(path))
    except Exception:
        return None, None
    try:
        streams = list(container.streams.audio)
        if not streams:
            return False, None
        try:
            return True, _all_silent(container, streams, duration)
        except Exception:
            return True, None
    finally:
        container.close()


def _all_silent(container, streams, duration: Optional[float]) -> Optional[bool]:
    if not duration or duration <= FULL_SCAN_SECONDS:
        loud, decoded = _scan(container, streams, None)
        return None if not decoded else not loud

    decoded_any = False
    step = duration / SAMPLE_COUNT
    for index in range(SAMPLE_COUNT):
        start = index * step
        try:
            container.seek(int(start * 1_000_000), any_frame=False, backward=True)
        except Exception:
            break
        loud, decoded = _scan(container, streams, start + SAMPLE_SECONDS)
        if loud:
            return False
        decoded_any = decoded_any or decoded
    return None if not decoded_any else True


def _scan(container, streams, stop_at: Optional[float]) -> Tuple[bool, bool]:
    """从当前位置解码到 stop_at（秒）；返回 (是否听到声音, 是否解出过音频)。"""
    decoded = False
    finished: Dict[int, bool] = {}
    for packet in container.demux(*streams):
        index = packet.stream.index
        if finished.get(index):
            continue
        for frame in packet.decode():
            if stop_at is not None and frame.time is not None and frame.time > stop_at:
                finished[index] = True
                break
            power = _mean_power(frame.to_ndarray())
            if power is None:
                continue
            decoded = True
            if power >= _THRESHOLD_POWER:
                return True, True
        if stop_at is not None and len(finished) == len(streams):
            break
    return False, decoded


def _mean_power(samples: np.ndarray) -> Optional[float]:
    if samples.size == 0:
        return None
    kind = samples.dtype.kind
    if kind == "f":
        values = samples.astype(np.float64, copy=False)
    elif kind == "i":
        values = samples.astype(np.float64) / float(2 ** (samples.dtype.itemsize * 8 - 1))
    elif kind == "u":
        half = float(2 ** (samples.dtype.itemsize * 8 - 1))
        values = (samples.astype(np.float64) - half) / half
    else:
        return None
    power = float(np.mean(values * values))
    return power if math.isfinite(power) else None


def level_db(power: float) -> float:
    return 10.0 * math.log10(power) if power > 0 else float("-inf")
