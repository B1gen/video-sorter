"""移动相关对话框的测试：每个弹窗都必须能用按钮或右上角 × 关掉。"""

from __future__ import annotations

import gc
import os
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget  # noqa: E402

from video_sorter import mover  # noqa: E402
from video_sorter.mover import MoveResult  # noqa: E402
from video_sorter.ui.move_controller import MoveController  # noqa: E402

_app = QApplication.instance() or QApplication([])


def _controller():
    parent = QWidget()
    settings = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, "test", "move")
    controller = MoveController(
        parent, settings, lambda: [], lambda: [], lambda: True, lambda: None
    )
    return parent, controller


def _capture_boxes():
    """把 exec 换掉，记录弹窗在“显示时”的按钮状态（先回收垃圾，模拟真实运行一段时间后）。"""
    seen = []

    def fake_exec(box):
        gc.collect()
        _app.processEvents()
        seen.append(
            {
                "buttons": [button.text() for button in box.buttons()],
                "escape": box.escapeButton().text() if box.escapeButton() else None,
            }
        )
        return 0

    return seen, mock.patch.object(QMessageBox, "exec", fake_exec)


def test_failure_report_can_be_closed():
    parent, controller = _controller()
    messages = []
    controller.message.connect(messages.append)
    results = [
        MoveResult(Path("a.mp4"), Path("x/a.mp4"), error="文件正被其他程序占用"),
        MoveResult(Path("b.mp4"), None, skip_reason=mover.SKIP_SAME_FOLDER),
    ]
    seen, patch = _capture_boxes()
    with patch:
        controller._report(results, "已移动 0 个视频到 x")
    assert len(seen) == 1
    assert seen[0]["buttons"] == ["好的"]
    assert seen[0]["escape"] == "好的"
    assert "1 个失败" in messages[-1] and "1 个跳过" in messages[-1]
    parent.deleteLater()


def test_skips_only_go_to_status_bar():
    parent, controller = _controller()
    messages = []
    controller.message.connect(messages.append)
    results = [
        MoveResult(Path("a.mp4"), Path("x/a.mp4")),
        MoveResult(Path("b.mp4"), None, skip_reason=mover.SKIP_SAME_FOLDER),
        MoveResult(Path("c.mp4"), None, skip_reason=mover.SKIP_SAME_FOLDER),
    ]
    seen, patch = _capture_boxes()
    with patch:
        controller._report(results, "已移动 1 个视频到 x")
    assert seen == []
    assert messages == ["已移动 1 个视频到 x，2 个跳过（{} 2 个）".format(mover.SKIP_SAME_FOLDER)]
    parent.deleteLater()


def test_conflict_question_can_be_closed():
    parent, controller = _controller()
    seen, patch = _capture_boxes()
    with patch:
        choice = controller._ask_conflicts([Path("a.mp4")], Path("x"))
    assert choice is None
    assert len(seen[0]["buttons"]) == 3
    assert seen[0]["escape"] == "取消"
    parent.deleteLater()


if __name__ == "__main__":
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            function()
            print("ok", name)
