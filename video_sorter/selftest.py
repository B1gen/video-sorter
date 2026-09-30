"""``VideoSorter.exe --self-test 报告路径``：检查打包后的程序能不能正常干活。

打包漏掉某个库或插件时，程序往往能启动，但一扫描就出错。这里把关键路径都走一遍：
解码视频、抽缩略图、识别音轨与静音、写 JPG 缓存、创建主窗口。
窗口程序没有控制台，结果写到报告文件里，退出码 0 表示全部通过。
"""

from __future__ import annotations

import sys
import tempfile
import traceback
from fractions import Fraction
from pathlib import Path
from typing import Callable, List, Tuple

import numpy as np

_FRAME_RATE = 25
_SECONDS = 2
_AUDIO_RATE = 48000


def run(report_path: str) -> int:
    lines: List[str] = []
    failures = 0

    def check(name: str, function: Callable[[], str]) -> None:
        nonlocal failures
        try:
            detail = function()
            lines.append("OK    {}  {}".format(name, detail or ""))
        except Exception:
            failures += 1
            lines.append("FAIL  {}\n{}".format(name, traceback.format_exc()))

    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        check("imports", _check_imports)
        check("qt", _check_qt)
        check("icon", _check_icon)
        check("probe_sound", lambda: _check_probe(root / "有声音.mp4", tone=True))
        check("probe_silent", lambda: _check_probe(root / "静音.mp4", tone=False))
        check("probe_no_audio", lambda: _check_probe(root / "无音轨.mp4", tone=None))
        check("thumbnail_cache", lambda: _check_cache(root / "有声音.mp4"))
        check("main_window", _check_window)

    lines.append("RESULT {}".format("PASS" if failures == 0 else "FAIL ({})".format(failures)))
    text = "\n".join(lines) + "\n"
    try:
        Path(report_path).write_text(text, "utf-8")
    except OSError:
        pass
    try:
        sys.stdout.write(text)
    except Exception:
        pass
    return 0 if failures == 0 else 1


def _check_imports() -> str:
    import av
    import cv2

    from . import __version__

    return "app {} / OpenCV {} / PyAV {} / numpy {}".format(
        __version__, cv2.__version__, av.__version__, np.__version__
    )


def _check_qt() -> str:
    from PySide6.QtGui import QImageWriter

    formats = {bytes(item).decode().lower() for item in QImageWriter.supportedImageFormats()}
    missing = {"jpg", "png"} - formats
    if missing:
        raise RuntimeError("缺少 Qt 图片插件：{}".format(", ".join(sorted(missing))))
    return "image formats ok"


def _check_icon() -> str:
    from .icon import app_icon

    icon = app_icon()
    if icon.isNull():
        raise RuntimeError("图标为空")
    return "{} sizes".format(len(icon.availableSizes()))


def _check_probe(path: Path, tone) -> str:
    from . import classify, probe

    _write_sample(path, tone)
    result = probe.probe(path)
    info = result.info
    if info.error:
        raise RuntimeError(info.error)
    if result.thumbnail is None:
        raise RuntimeError("没有抽出缩略图")
    if not info.duration or abs(info.duration - _SECONDS) > 0.5:
        raise RuntimeError("时长不对：{}".format(info.duration))
    if (info.width, info.height) != (320, 180):
        raise RuntimeError("分辨率不对：{}x{}".format(info.width, info.height))
    expected = {
        True: classify.AUDIO_PRESENT,
        False: classify.AUDIO_SILENT,
        None: classify.AUDIO_NONE,
    }[tone]
    label = classify.labels_for(info).audio
    if label != expected:
        raise RuntimeError("声音识别为「{}」，应为「{}」".format(label, expected))
    return "{:.2f}s {}x{} {}".format(info.duration, info.width, info.height, label)


def _check_cache(path: Path) -> str:
    from . import probe
    from .cache import ThumbnailCache
    from .imaging import to_qimage

    cache = ThumbnailCache(352, 198)
    cache.root = path.parent / "cache"
    result = probe.probe(path)
    cache.store(result.info, to_qimage(result.thumbnail))
    loaded = cache.load(path)
    if loaded is None or loaded[1] is None or loaded[1].isNull():
        raise RuntimeError("缩略图缓存读写失败")
    return "jpg ok"


def _check_window() -> str:
    from PySide6.QtWidgets import QApplication

    from .ui.main_window import MainWindow

    if QApplication.instance() is None:
        raise RuntimeError("没有 QApplication")
    window = MainWindow()
    window.close()
    window.deleteLater()
    return "created"


def _write_sample(path: Path, tone) -> None:
    """用 PyAV 自带的编码器写一个 320x180、2 秒的小视频。"""
    import av

    container = av.open(str(path), "w")
    video = container.add_stream("mpeg4", rate=_FRAME_RATE)
    video.width, video.height, video.pix_fmt = 320, 180, "yuv420p"
    audio = None
    if tone is not None:
        audio = container.add_stream("aac", rate=_AUDIO_RATE, layout="mono")

    for index in range(_FRAME_RATE * _SECONDS):
        pixels = np.zeros((180, 320, 3), dtype=np.uint8)
        pixels[:, : (index * 4) % 320] = (40, 160, 230)
        frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
        frame.pts = index
        frame.time_base = Fraction(1, _FRAME_RATE)
        for packet in video.encode(frame):
            container.mux(packet)

    if audio is not None:
        chunk = 1024
        total = _AUDIO_RATE * _SECONDS
        for start in range(0, total, chunk):
            count = min(chunk, total - start)
            if tone:
                times = np.arange(start, start + count) / _AUDIO_RATE
                samples = 0.3 * np.sin(2 * np.pi * 440 * times)
            else:
                samples = np.zeros(count)
            frame = av.AudioFrame.from_ndarray(
                samples.astype(np.float32)[None, :], format="fltp", layout="mono"
            )
            frame.sample_rate = _AUDIO_RATE
            frame.pts = start
            for packet in audio.encode(frame):
                container.mux(packet)

    for stream in (video, audio):
        if stream is not None:
            for packet in stream.encode(None):
                container.mux(packet)
    container.close()


def parse_args(argv: List[str]) -> Tuple[bool, str]:
    if "--self-test" not in argv:
        return False, ""
    position = argv.index("--self-test")
    report = argv[position + 1] if position + 1 < len(argv) else "selftest-report.txt"
    return True, report
