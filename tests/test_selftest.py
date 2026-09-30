"""打包自检在源码环境下也要能通过：python tests/test_selftest.py 或 pytest 都能跑。"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from video_sorter import selftest  # noqa: E402


def test_self_test_passes():
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as folder:
        report = Path(folder) / "report.txt"
        code = selftest.run(str(report))
        text = report.read_text("utf-8")
    assert code == 0, text
    assert "RESULT PASS" in text
    del app


def test_parse_args():
    assert selftest.parse_args(["app.exe"]) == (False, "")
    assert selftest.parse_args(["app.exe", "--self-test", "r.txt"]) == (True, "r.txt")
    assert selftest.parse_args(["app.exe", "--self-test"]) == (True, "selftest-report.txt")


if __name__ == "__main__":
    test_self_test_passes()
    test_parse_args()
    print("ok")
