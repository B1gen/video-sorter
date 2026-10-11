"""“移动到文件夹”的菜单、对话框、后台移动线程和撤销。"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from PySide6.QtCore import QEventLoop, QObject, QSettings, Qt, QThread, Signal
from PySide6.QtGui import QAction, QCursor, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QWidget,
)

from .. import config, mover
from ..mover import MovePlan, MoveResult

RECENT_KEY = "move_targets"
MAX_RECENT = 10
_MENU_TEXT_WIDTH = 420
_REPORT_LINES = 12
_INVALID_NAME_CHARS = set('\\/:*?"<>|')

MovedPairs = List[Tuple[Path, Path]]


class _MoveThread(QThread):
    progress = Signal(int, int, str)

    def __init__(self, plans: Sequence[MovePlan]) -> None:
        super().__init__()
        self._plans = list(plans)
        self._cancel = threading.Event()
        self.results: List[MoveResult] = []

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        total = len(self._plans)
        for done, plan in enumerate(self._plans):
            if self._cancel.is_set():
                self.results.append(MoveResult(plan.source, plan.target, skip_reason="已取消"))
                continue
            self.progress.emit(done, total, plan.source.name)
            if plan.target is None:
                self.results.append(MoveResult(plan.source, None, skip_reason=plan.skip_reason))
                continue
            error = mover.move_file(plan.source, plan.target)
            self.results.append(MoveResult(plan.source, plan.target, error=error))
        self.progress.emit(total, total, "")


class MoveController(QObject):
    """主窗口提供“当前选中了哪些文件”等回调，移动成功后通过 filesMoved 通知它更新列表。"""

    filesMoved = Signal(list)
    message = Signal(str)

    def __init__(
        self,
        parent: QWidget,
        settings: QSettings,
        selection: Callable[[], List[Path]],
        roots: Callable[[], List[Path]],
        prepare: Callable[[], bool],
        finish: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self._parent = parent
        self._settings = settings
        self._selection = selection
        self._roots = roots
        self._prepare = prepare
        self._finish = finish
        self._last_batch: MovedPairs = []

        self.menu = QMenu("移动到", parent)
        self.menu.aboutToShow.connect(lambda: self.populate_menu(self.menu))

        self.move_action = QAction("移动到文件夹…", parent)
        self.move_action.setShortcut(QKeySequence("Ctrl+M"))
        self.move_action.triggered.connect(self.popup_menu)

        self.undo_action = QAction("撤销移动", parent)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.setEnabled(False)
        self.undo_action.triggered.connect(self.undo)

    # ------------------------------------------------------------------ 菜单

    def popup_menu(self) -> None:
        self.menu.exec(QCursor.pos())

    def populate_menu(self, menu: QMenu) -> None:
        menu.clear()
        menu.setToolTipsVisible(True)
        count = len(self._selection())
        header = menu.addAction(
            "移动选中的 {} 个视频到：".format(count) if count else "先选中要移动的视频（可多选）"
        )
        header.setEnabled(False)

        recent = self.recent_folders()
        if recent:
            menu.addSection("最近使用")
            for folder in recent:
                self._add_folder_action(menu, folder, str(folder), count > 0)

        root = next((item for item in self._roots() if item.is_dir()), None)
        if root is not None:
            menu.addSection("当前文件夹里的子文件夹")
            self._add_folder_action(menu, root, "{}（根目录）".format(root.name or root), count > 0)
            for folder in mover.subfolders(root):
                self._add_folder_action(menu, folder, "　" + folder.name, count > 0)
            create = menu.addAction("新建子文件夹并移动…")
            create.setEnabled(count > 0)
            create.triggered.connect(lambda _checked=False, base=root: self.create_and_move(base))

        menu.addSeparator()
        browse = menu.addAction("选择其他文件夹…")
        browse.setEnabled(count > 0)
        browse.triggered.connect(self.choose_and_move)
        if recent:
            clear = menu.addAction("清空最近使用列表")
            clear.triggered.connect(self.clear_recent)

    def _add_folder_action(self, menu: QMenu, folder: Path, text: str, enabled: bool) -> None:
        label = menu.fontMetrics().elidedText(text, Qt.TextElideMode.ElideMiddle, _MENU_TEXT_WIDTH)
        action = menu.addAction(label)
        action.setToolTip(str(folder))
        action.setEnabled(enabled)
        action.triggered.connect(lambda _checked=False, target=folder: self.move_to(target))

    # ------------------------------------------------------------------ 最近使用

    def recent_folders(self) -> List[Path]:
        stored = self._settings.value(RECENT_KEY, [])
        if isinstance(stored, str):
            stored = [stored]
        return [Path(item) for item in stored or [] if item and Path(item).is_dir()]

    def _remember(self, folder: Path) -> None:
        folders = [item for item in self.recent_folders() if not mover.same_path(item, folder)]
        folders.insert(0, folder)
        self._settings.setValue(RECENT_KEY, [str(item) for item in folders[:MAX_RECENT]])

    def clear_recent(self) -> None:
        self._settings.setValue(RECENT_KEY, [])

    # ------------------------------------------------------------------ 移动

    def choose_and_move(self) -> None:
        if not self._selection():
            return
        recent = self.recent_folders()
        roots = self._roots()
        start = str(recent[0]) if recent else (str(roots[0]) if roots else "")
        folder = QFileDialog.getExistingDirectory(self._parent, "移动到哪个文件夹？", start)
        if folder:
            self.move_to(Path(folder))

    def create_and_move(self, base: Path) -> None:
        if not self._selection():
            return
        name, ok = QInputDialog.getText(self._parent, "新建子文件夹", "在「{}」里新建：".format(base))
        name = name.strip()
        if not ok or not name:
            return
        if any(char in _INVALID_NAME_CHARS for char in name) or name in (".", ".."):
            QMessageBox.warning(self._parent, config.APP_NAME, '文件夹名不能包含 \\ / : * ? " < > |')
            return
        folder = base / name
        try:
            folder.mkdir(exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self._parent, config.APP_NAME, "无法创建文件夹：{}".format(exc))
            return
        self.move_to(folder)

    def move_to(self, folder: Path) -> None:
        sources = self._selection()
        if not sources:
            return
        if not folder.is_dir():
            QMessageBox.warning(self._parent, config.APP_NAME, "文件夹不存在：{}".format(folder))
            return

        rename = False
        conflicts = mover.find_conflicts(sources, folder)
        if conflicts:
            choice = self._ask_conflicts(conflicts, folder)
            if choice is None:
                return
            rename = choice

        if not self._prepare():
            return
        try:
            self._remember(folder)
            results = self._run(mover.plan_moves(sources, folder, rename), "正在移动…")
        finally:
            self._finish()

        pairs = [(result.source, result.target) for result in results if result.moved]
        if pairs:
            self._last_batch = pairs
            self.undo_action.setEnabled(True)
            self.undo_action.setText("撤销移动（{} 个文件）".format(len(pairs)))
            self.filesMoved.emit(pairs)
        self._report(results, "已移动 {} 个视频到 {}".format(len(pairs), folder))

    def undo(self) -> None:
        if not self._last_batch or not self._prepare():
            return
        try:
            plans = [MovePlan(target, source) for source, target in self._last_batch]
            results = self._run(plans, "正在撤销移动…")
        finally:
            self._finish()
        self._last_batch = []
        self.undo_action.setEnabled(False)
        self.undo_action.setText("撤销移动")
        pairs = [(result.source, result.target) for result in results if result.moved]
        if pairs:
            self.filesMoved.emit(pairs)
        self._report(results, "已撤销，{} 个视频移回原处".format(len(pairs)))

    def _run(self, plans: Sequence[MovePlan], title: str) -> List[MoveResult]:
        dialog = QProgressDialog(title, "停止", 0, max(1, len(plans)), self._parent)
        dialog.setWindowTitle(config.APP_NAME)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(400)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)

        thread = _MoveThread(plans)
        thread.progress.connect(
            lambda done, total, name: (
                dialog.setValue(done),
                dialog.setLabelText("{}　{}/{}\n{}".format(title, done, total, name)),
            )
        )
        dialog.canceled.connect(thread.cancel)
        loop = QEventLoop()
        thread.finished.connect(loop.quit)
        thread.start()
        loop.exec()
        thread.wait()
        dialog.close()
        dialog.deleteLater()
        return thread.results

    def _ask_conflicts(self, conflicts: Sequence[Path], folder: Path) -> Optional[bool]:
        """返回 True = 自动改名，False = 跳过重名的，None = 取消。"""
        names = "\n".join("· " + path.name for path in conflicts[:_REPORT_LINES])
        if len(conflicts) > _REPORT_LINES:
            names += "\n…等 {} 个".format(len(conflicts))
        box = QMessageBox(self._parent)
        box.setWindowTitle(config.APP_NAME)
        box.setIcon(QMessageBox.Icon.Question)
        box.setText("「{}」里已有 {} 个同名文件：".format(folder, len(conflicts)))
        box.setInformativeText(names + "\n\n不会覆盖任何文件。要怎么处理这些重名的视频？")
        rename = box.addButton("自动改名（如 a (1).mp4）", QMessageBox.ButtonRole.AcceptRole)
        skip = box.addButton("跳过重名的", QMessageBox.ButtonRole.ActionRole)
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(rename)
        box.exec()
        clicked = box.clickedButton()
        if clicked is rename:
            return True
        if clicked is skip:
            return False
        return None

    def _report(self, results: Sequence[MoveResult], summary: str) -> None:
        problems = [result for result in results if not result.moved]
        failed = [result for result in problems if result.error]
        skipped = [result for result in problems if not result.error]
        if not problems:
            self.message.emit(summary + "　（Ctrl+Z 可撤销）" if self._last_batch else summary)
            return
        lines = []
        for result in (failed + skipped)[:_REPORT_LINES]:
            lines.append("· {}：{}".format(result.source.name, result.error or result.skip_reason))
        if len(problems) > _REPORT_LINES:
            lines.append("…等 {} 个".format(len(problems)))
        parts = [summary]
        if failed:
            parts.append("{} 个失败".format(len(failed)))
        if skipped:
            parts.append("{} 个跳过".format(len(skipped)))
        box = QMessageBox(
            QMessageBox.Icon.Warning if failed else QMessageBox.Icon.Information,
            config.APP_NAME,
            "，".join(parts) + "。",
            parent=self._parent,
        )
        box.setInformativeText("\n".join(lines))
        box.addButton(QPushButton("好的"), QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        self.message.emit("，".join(parts))
