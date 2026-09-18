"""分类规则的回归测试：python tests/test_classify.py 或 pytest 都能跑。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from video_sorter import classify  # noqa: E402
from video_sorter.models import VideoInfo  # noqa: E402


def test_duration_buckets():
    assert classify.duration_label(3.0)[0] == "≤ 5 秒"
    assert classify.duration_label(10.0)[0] == "5–10 秒"
    # 录制出来的 10 秒常是 10.03 秒，不该掉进下一档
    assert classify.duration_label(10.03)[0] == "5–10 秒"
    assert classify.duration_label(20.4)[0] == "10–20 秒"
    assert classify.duration_label(30.0)[0] == "20–30 秒"
    assert classify.duration_label(59.9)[0] == "30 秒 – 1 分钟"
    assert classify.duration_label(119.0)[0] == "1 – 2 分钟"
    assert classify.duration_label(3600.0)[0] == classify.DURATION_OVERFLOW_LABEL
    assert classify.duration_label(None)[0] == classify.UNKNOWN_DURATION
    assert classify.duration_label(None)[1] == classify.UNKNOWN_RANK


def test_fps_snapping():
    assert classify.fps_label(29.97)[0] == "30 fps"
    assert classify.fps_label(30.0)[0] == "30 fps"
    assert classify.fps_label(23.976)[0] == "24 fps"
    assert classify.fps_label(59.94)[0] == "60 fps"
    assert classify.fps_label(119.88)[0] == "120 fps"
    assert classify.fps_label(43.0)[0] == "43 fps"
    assert classify.fps_label(0)[0] == classify.UNKNOWN_FPS


def test_resolution_labels():
    assert classify.resolution_label(1920, 1080)[0] == "1080p"
    assert classify.resolution_label(1080, 1920)[0] == "1080p"
    assert classify.resolution_label(1080, 1920)[2] == "竖屏"
    assert classify.resolution_label(1920, 1080)[2] == "横屏"
    assert classify.resolution_label(2560, 1440)[0] == "1440p (2K)"
    assert classify.resolution_label(3840, 2160)[0] == "2160p (4K)"
    assert classify.resolution_label(2240, 1260)[0] == "1260p"
    assert classify.resolution_label(1440, 1440)[2] == "方形"
    assert classify.resolution_label(1000, 668)[0] == "668p"
    assert classify.resolution_label(None, None)[0] == classify.UNKNOWN_RESOLUTION


def test_group_path_follows_mode():
    info = VideoInfo(path=Path("a.mp4"), duration=10.0, fps=59.94, width=1920, height=1080)
    labels = classify.labels_for(info)
    assert classify.group_path(labels, ("resolution", "fps", "duration")) == [
        "1080p",
        "60 fps",
        "5–10 秒",
    ]
    assert classify.group_path(labels, ("duration",)) == ["5–10 秒"]
    assert classify.dimensions_for_mode("all") == ("resolution", "fps", "duration")


def test_formatters():
    assert classify.format_duration(65.0) == "1:05"
    assert classify.format_duration(3725.0) == "1:02:05"
    assert classify.format_duration(None) == "--:--"
    assert classify.format_size(1536) == "1.5 KB"
    assert classify.format_size(0) == "0 B"


def _run_all():
    failures = 0
    for name, function in sorted(globals().items()):
        if not name.startswith("test_") or not callable(function):
            continue
        try:
            function()
        except AssertionError as exc:
            failures += 1
            print("FAIL {}: {}".format(name, exc))
        else:
            print("ok   {}".format(name))
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run_all() else 0)
