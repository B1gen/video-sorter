"""目录遍历与拖拽解析的测试：python tests/test_scanner.py 或 pytest 都能跑。"""

from __future__ import annotations

import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QMimeData, QUrl  # noqa: E402

from video_sorter.scanner import _is_video, _WalkThread  # noqa: E402
from video_sorter.ui.drop_area import paths_from_mime  # noqa: E402


def _sample_tree(root: Path) -> None:
    (root / "sub" / "deep").mkdir(parents=True)
    for relative in (
        "a.mp4",
        "B.MOV",
        "c.mkv",
        "note.txt",
        "cover.jpg",
        "sub/d.avi",
        "sub/deep/e.webm",
        ".hidden.mp4",
    ):
        (root / relative).write_bytes(b"")


def test_is_video():
    assert _is_video(Path("a.mp4"))
    assert _is_video(Path("A.MOV"))
    assert not _is_video(Path("a.txt"))
    assert not _is_video(Path("a.mp4.part"))
    # macOS 的 ._xxx 之类隐藏文件不该被当成素材
    assert not _is_video(Path(".hidden.mp4"))


def test_walk_recursive_and_flat():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _sample_tree(root)
        cancel = threading.Event()

        recursive = sorted(
            path.name for path in _WalkThread([root], True, cancel)._iter_videos()
        )
        assert recursive == ["B.MOV", "a.mp4", "c.mkv", "d.avi", "e.webm"]

        flat = sorted(path.name for path in _WalkThread([root], False, cancel)._iter_videos())
        assert flat == ["B.MOV", "a.mp4", "c.mkv"]


def test_walk_accepts_single_files_and_skips_missing():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _sample_tree(root)
        cancel = threading.Event()
        roots = [root / "a.mp4", root / "note.txt", root / "nope.mp4", root / "sub"]
        found = sorted(path.name for path in _WalkThread(roots, True, cancel)._iter_videos())
        assert found == ["a.mp4", "d.avi", "e.webm"]


def test_walk_stops_when_cancelled():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _sample_tree(root)
        cancel = threading.Event()
        cancel.set()
        assert list(_WalkThread([root], True, cancel)._iter_videos()) == []


def test_paths_from_mime_keeps_folders_and_videos():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _sample_tree(root)
        mime = QMimeData()
        mime.setUrls(
            [
                QUrl.fromLocalFile(str(root / "sub")),
                QUrl.fromLocalFile(str(root / "a.mp4")),
                QUrl.fromLocalFile(str(root / "note.txt")),
                QUrl("https://example.com/x.mp4"),
            ]
        )
        names = [path.name for path in paths_from_mime(mime)]
        assert names == ["sub", "a.mp4"]

    empty = QMimeData()
    empty.setText("hello")
    assert paths_from_mime(empty) == []


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
