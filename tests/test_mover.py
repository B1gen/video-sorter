"""移动文件的测试：python tests/test_mover.py 或 pytest 都能跑。"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from video_sorter import mover  # noqa: E402


def _touch(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")
    return path


def test_plan_handles_same_folder_and_batch_duplicates():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        target = root / "target"
        target.mkdir()
        a1 = _touch(root / "one" / "a.mp4")
        a2 = _touch(root / "two" / "a.mp4")
        already = _touch(target / "b.mp4")

        assert mover.find_conflicts([a1, a2, already], target) == [a2]

        plans = mover.plan_moves([a1, a2, already], target, rename_conflicts=True)
        assert [plan.target for plan in plans] == [target / "a.mp4", target / "a (1).mp4", None]
        assert plans[2].skip_reason == mover.SKIP_SAME_FOLDER

        skipped = mover.plan_moves([a1, a2], target, rename_conflicts=False)
        assert skipped[1].target is None and skipped[1].skip_reason == mover.SKIP_CONFLICT


def test_existing_files_are_never_overwritten():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        source = _touch(root / "src" / "clip.mp4", "new")
        existing = _touch(root / "dst" / "clip.mp4", "old")
        _touch(root / "dst" / "clip (1).mp4", "old1")

        assert mover.find_conflicts([source], existing.parent) == [source]
        plan = mover.plan_moves([source], existing.parent, rename_conflicts=True)[0]
        assert plan.target == root / "dst" / "clip (2).mp4"

        assert mover.move_file(source, existing) == mover.SKIP_CONFLICT
        assert existing.read_text("utf-8") == "old" and source.exists()

        assert mover.move_file(source, plan.target) == ""
        assert not source.exists() and plan.target.read_text("utf-8") == "new"
        assert mover.move_file(source, root / "dst" / "x.mp4") == "源文件已不存在"


def test_failed_copy_leaves_source_intact():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        source = _touch(root / "src" / "clip.mp4", "data")
        target = root / "dst" / "clip.mp4"

        def broken_move(src, dst):
            Path(dst).parent.mkdir(parents=True, exist_ok=True)
            Path(dst).write_text("partial", "utf-8")
            raise PermissionError("in use")

        with mock.patch.object(shutil, "move", broken_move):
            error = mover.move_file(source, target)
        assert "占用" in error
        assert source.read_text("utf-8") == "data"
        assert not target.exists()


def test_is_under_roots():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder) / "videos"
        (root / "sub" / "deep").mkdir(parents=True)
        outside = Path(folder) / "videos2"
        outside.mkdir()

        assert mover.is_under_roots(root / "a.mp4", [root], recursive=False)
        assert not mover.is_under_roots(root / "sub" / "a.mp4", [root], recursive=False)
        assert mover.is_under_roots(root / "sub" / "deep" / "a.mp4", [root], recursive=True)
        # 前缀相同但不是子目录
        assert not mover.is_under_roots(outside / "a.mp4", [root], recursive=True)
        # 根是单个文件：只有它自己算在范围内，移走后就不算了
        single = root / "single.mp4"
        assert mover.is_under_roots(single, [single], recursive=True)
        assert not mover.is_under_roots(outside / "single.mp4", [single], recursive=True)


def test_subfolders_sorted_and_hidden_skipped():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        for name in ("b", "A", ".hidden", "$RECYCLE.BIN"):
            (root / name).mkdir()
        _touch(root / "file.mp4")
        assert [path.name for path in mover.subfolders(root)] == ["A", "b"]


if __name__ == "__main__":
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            function()
            print("ok", name)
