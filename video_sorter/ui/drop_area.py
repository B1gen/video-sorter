"""拖拽识别框：把文件夹拖进来即可开始分类。"""

from __future__ import annotations

from pathlib import Path
from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from ..models import VIDEO_SUFFIXES

IDLE_STYLE = """
QFrame#DropArea {
    border: 2px dashed rgba(128, 128, 140, 140);
    border-radius: 8px;
    background: rgba(128, 128, 140, 18);
}
"""

ACTIVE_STYLE = """
QFrame#DropArea {
    border: 2px dashed #3876d6;
    border-radius: 8px;
    background: rgba(56, 118, 214, 45);
}
"""


class DropArea(QFrame):
    pathsDropped = Signal(list)
    browseRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("DropArea")
        self.setAcceptDrops(True)
        self.setStyleSheet(IDLE_STYLE)
        self.setMinimumHeight(64)

        self._label = QLabel("把文件夹拖到这里，或点击右侧按钮选择文件夹")
        self._label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._label.setWordWrap(True)

        self._button = QPushButton("选择文件夹…")
        self._button.setMinimumWidth(120)
        self._button.clicked.connect(self.browseRequested.emit)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 12, 10)
        layout.setSpacing(12)
        layout.addWidget(self._label, 1)
        layout.addWidget(self._button, 0)

    def set_message(self, text: str) -> None:
        self._label.setText(text)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if paths_from_mime(event.mimeData()):
            event.acceptProposedAction()
            self.setStyleSheet(ACTIVE_STYLE)
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if paths_from_mime(event.mimeData()):
            event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802
        self.setStyleSheet(IDLE_STYLE)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self.setStyleSheet(IDLE_STYLE)
        paths = paths_from_mime(event.mimeData())
        if paths:
            event.acceptProposedAction()
            self.pathsDropped.emit(paths)
        else:
            event.ignore()


def paths_from_mime(mime) -> List[Path]:
    if not mime.hasUrls():
        return []
    paths: List[Path] = []
    for url in mime.urls():
        if not url.isLocalFile():
            continue
        path = Path(url.toLocalFile())
        if path.is_dir() or path.suffix.lower() in VIDEO_SUFFIXES:
            paths.append(path)
    return paths
