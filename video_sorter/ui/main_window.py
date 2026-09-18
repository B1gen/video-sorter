"""主窗口：工具栏 + 拖拽框 + 分类树 + 缩略图网格。"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import classify, config, probe, reveal
from ..cache import ThumbnailCache
from ..models import VideoInfo
from ..scanner import ScanController
from .category_tree import CategoryTree
from .drop_area import DropArea, paths_from_mime
from .list_model import (
    ITEM_ROLE,
    SORT_FIELDS,
    ThumbnailDelegate,
    VideoFilterProxy,
    VideoItem,
    VideoListModel,
    item_size,
)

FLUSH_INTERVAL_MS = 150
TREE_REFRESH_MS = 600


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(config.APP_NAME)
        self.resize(1280, 820)
        self.setAcceptDrops(True)

        self._settings = QSettings(config.ORG_NAME, config.APP_NAME)
        self._cache = ThumbnailCache(config.THUMB_WIDTH, config.THUMB_HEIGHT)
        self._scanner = ScanController(self._cache, config.THUMB_WIDTH, config.THUMB_HEIGHT, self)
        self._roots: List[Path] = []
        self._pending: List[Tuple[VideoInfo, object]] = []
        self._error_count = 0
        self._scan_progress: Tuple[int, int] = (0, 0)

        self._build_ui()
        self._build_menu()
        self._connect_signals()
        self._restore_settings()
        self._update_status()

    # ------------------------------------------------------------------ 界面

    def _build_ui(self) -> None:
        central = QWidget(self)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(10, 10, 10, 6)
        root_layout.setSpacing(8)

        self._drop_area = DropArea(central)
        root_layout.addWidget(self._drop_area)

        root_layout.addLayout(self._build_toolbar())

        splitter = QSplitter(Qt.Orientation.Horizontal, central)
        self._tree = CategoryTree(splitter)
        self._tree.setMinimumWidth(200)

        self._model = VideoListModel(self)
        self._proxy = VideoFilterProxy(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.sort(0, Qt.SortOrder.AscendingOrder)

        display_size = config.DISPLAY_SIZES[config.DEFAULT_DISPLAY_INDEX]
        self._delegate = ThumbnailDelegate(display_size, self)
        self._view = QListView(splitter)
        self._view.setModel(self._proxy)
        self._view.setItemDelegate(self._delegate)
        self._view.setViewMode(QListView.ViewMode.IconMode)
        self._view.setResizeMode(QListView.ResizeMode.Adjust)
        self._view.setMovement(QListView.Movement.Static)
        self._view.setFlow(QListView.Flow.LeftToRight)
        self._view.setWrapping(True)
        self._view.setUniformItemSizes(True)
        self._view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._view.viewport().setMouseTracking(True)
        self._apply_display_size(display_size)

        splitter.addWidget(self._tree)
        splitter.addWidget(self._view)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 1000])
        self._splitter = splitter
        root_layout.addWidget(splitter, 1)

        self.setCentralWidget(central)

        self._progress = QProgressBar()
        self._progress.setMaximumWidth(220)
        self._progress.setVisible(False)
        self._status_label = QLabel("请选择或拖入一个文件夹")
        self._detail_label = QLabel("")
        self.statusBar().addWidget(self._status_label, 1)
        self.statusBar().addPermanentWidget(self._detail_label)
        self.statusBar().addPermanentWidget(self._progress)

        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(FLUSH_INTERVAL_MS)
        self._flush_timer.timeout.connect(self._flush_pending)
        self._tree_timer = QTimer(self)
        self._tree_timer.setInterval(TREE_REFRESH_MS)
        self._tree_timer.timeout.connect(self._rebuild_tree)

    def _build_toolbar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(8)

        self._rescan_button = QPushButton("重新扫描")
        self._rescan_button.setEnabled(False)
        self._cancel_button = QPushButton("停止")
        self._cancel_button.setEnabled(False)
        self._recursive_box = QCheckBox("包含子文件夹")
        self._recursive_box.setChecked(True)

        self._group_combo = QComboBox()
        for key, name, _dimensions in classify.GROUP_MODES:
            self._group_combo.addItem(name, key)

        self._sort_combo = QComboBox()
        for key, name in SORT_FIELDS:
            self._sort_combo.addItem(name, key)
        self._desc_box = QCheckBox("倒序")

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("按文件名筛选…")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setMaximumWidth(220)

        self._size_slider = QSlider(Qt.Orientation.Horizontal)
        self._size_slider.setRange(0, len(config.DISPLAY_SIZES) - 1)
        self._size_slider.setValue(config.DEFAULT_DISPLAY_INDEX)
        self._size_slider.setFixedWidth(90)
        self._size_slider.setPageStep(1)

        layout.addWidget(self._rescan_button)
        layout.addWidget(self._cancel_button)
        layout.addWidget(self._recursive_box)
        layout.addSpacing(12)
        layout.addWidget(QLabel("分组："))
        layout.addWidget(self._group_combo)
        layout.addSpacing(8)
        layout.addWidget(QLabel("排序："))
        layout.addWidget(self._sort_combo)
        layout.addWidget(self._desc_box)
        layout.addStretch(1)
        layout.addWidget(self._search_edit)
        layout.addSpacing(8)
        layout.addWidget(QLabel("缩略图"))
        layout.addWidget(self._size_slider)
        return layout

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("文件")
        open_action = QAction("选择文件夹…", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._choose_folder)
        file_menu.addAction(open_action)

        rescan_action = QAction("重新扫描", self)
        rescan_action.setShortcut(QKeySequence.StandardKey.Refresh)
        rescan_action.triggered.connect(self._rescan)
        file_menu.addAction(rescan_action)
        file_menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        tools_menu = self.menuBar().addMenu("工具")
        clear_cache_action = QAction("清空缩略图缓存", self)
        clear_cache_action.triggered.connect(self._clear_cache)
        tools_menu.addAction(clear_cache_action)

        help_menu = self.menuBar().addMenu("帮助")
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _connect_signals(self) -> None:
        self._drop_area.browseRequested.connect(self._choose_folder)
        self._drop_area.pathsDropped.connect(self._start_scan)
        self._rescan_button.clicked.connect(self._rescan)
        self._cancel_button.clicked.connect(self._scanner.cancel)
        self._recursive_box.toggled.connect(self._on_recursive_toggled)
        self._group_combo.currentIndexChanged.connect(self._on_group_changed)
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        self._desc_box.toggled.connect(self._on_sort_changed)
        self._search_edit.textChanged.connect(self._proxy.set_text)
        self._search_edit.textChanged.connect(lambda _text: self._update_status())
        self._size_slider.valueChanged.connect(self._on_size_changed)
        self._tree.categorySelected.connect(self._on_category_selected)
        self._view.doubleClicked.connect(self._on_double_clicked)
        self._view.customContextMenuRequested.connect(self._show_context_menu)
        self._view.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self._proxy.rowsInserted.connect(lambda *_args: self._update_status())
        self._proxy.rowsRemoved.connect(lambda *_args: self._update_status())
        self._proxy.modelReset.connect(self._update_status)
        self._scanner.videoReady.connect(self._on_video_ready)
        self._scanner.progress.connect(self._on_progress)
        self._scanner.scanFinished.connect(self._on_scan_finished)

    # ------------------------------------------------------------------ 扫描

    def open_paths(self, paths: Sequence[Path]) -> None:
        """供命令行参数或把文件夹拖到 exe 图标上时调用。"""
        self._start_scan(paths)

    def _choose_folder(self) -> None:
        start_dir = str(self._roots[0]) if self._roots else self._settings.value("last_dir", "")
        folder = QFileDialog.getExistingDirectory(self, "选择要分类的文件夹", start_dir)
        if folder:
            self._start_scan([Path(folder)])

    def _rescan(self) -> None:
        if self._roots:
            self._start_scan(list(self._roots))

    def _start_scan(self, roots: Sequence[Path]) -> None:
        roots = [Path(root) for root in roots if Path(root).exists()]
        if not roots:
            return
        self._roots = list(roots)
        self._settings.setValue("last_dir", str(roots[0]))
        self._drop_area.set_message(_roots_message(roots))

        self._pending.clear()
        self._error_count = 0
        self._model.clear()
        self._rebuild_tree()
        self._flush_timer.start()
        self._tree_timer.start()
        self._rescan_button.setEnabled(True)
        self._cancel_button.setEnabled(True)
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._scanner.start(roots, self._recursive_box.isChecked())

    def _on_video_ready(self, info: VideoInfo, image) -> None:
        self._pending.append((info, image))
        if info.error:
            self._error_count += 1

    def _flush_pending(self) -> None:
        if not self._pending:
            return
        batch = [
            VideoItem(info=info, labels=classify.labels_for(info), image=image)
            for info, image in self._pending
        ]
        self._pending.clear()
        self._model.add_many(batch)

    def _on_progress(self, done: int, total: int) -> None:
        if total <= 0:
            self._progress.setRange(0, 0)
        else:
            self._progress.setRange(0, total)
            self._progress.setValue(done)
        self._scan_progress = (done, total)
        self._update_status()

    def _on_scan_finished(self, completed: bool) -> None:
        self._flush_timer.stop()
        self._tree_timer.stop()
        self._flush_pending()
        self._rebuild_tree()
        self._cancel_button.setEnabled(False)
        self._progress.setVisible(False)
        self._update_status(finished=True, completed=completed)

    # ------------------------------------------------------------------ 视图

    def _rebuild_tree(self) -> None:
        self._flush_pending()
        dimensions = self._current_dimensions()
        self._tree.rebuild(self._model.items(), dimensions)

    def _current_dimensions(self) -> Tuple[str, ...]:
        return classify.dimensions_for_mode(self._group_combo.currentData())

    def _on_group_changed(self) -> None:
        self._proxy.set_group(self._current_dimensions(), [])
        self._rebuild_tree()
        self._settings.setValue("group_mode", self._group_combo.currentData())

    def _on_category_selected(self, path: List[str]) -> None:
        self._proxy.set_group(self._current_dimensions(), path)
        self._update_status()

    def _on_sort_changed(self) -> None:
        self._model.set_sort_field(self._sort_combo.currentData())
        order = (
            Qt.SortOrder.DescendingOrder
            if self._desc_box.isChecked()
            else Qt.SortOrder.AscendingOrder
        )
        self._proxy.sort(0, order)
        self._settings.setValue("sort_field", self._sort_combo.currentData())
        self._settings.setValue("sort_desc", self._desc_box.isChecked())

    def _on_size_changed(self, index: int) -> None:
        size = config.DISPLAY_SIZES[max(0, min(index, len(config.DISPLAY_SIZES) - 1))]
        self._apply_display_size(size)
        self._model.drop_pixmap_cache()
        self._settings.setValue("thumb_index", index)

    def _apply_display_size(self, size: Tuple[int, int]) -> None:
        self._delegate.display_size = size
        self._view.setGridSize(item_size(size))
        self._view.doItemsLayout()

    def _on_recursive_toggled(self, checked: bool) -> None:
        self._settings.setValue("recursive", checked)
        if self._roots:
            self._rescan()

    # ------------------------------------------------------------------ 交互

    def _on_double_clicked(self, index) -> None:
        item: Optional[VideoItem] = index.data(ITEM_ROLE)
        if item is None:
            return
        if not reveal.reveal_in_file_manager(item.info.path):
            QMessageBox.warning(self, config.APP_NAME, "文件已不存在或无法打开所在文件夹。")

    def _selected_items(self) -> List[VideoItem]:
        items = []
        for index in self._view.selectionModel().selectedIndexes():
            item = index.data(ITEM_ROLE)
            if item is not None:
                items.append(item)
        return items

    def _on_selection_changed(self, *_args) -> None:
        items = self._selected_items()
        if len(items) == 1:
            info = items[0].info
            labels = items[0].labels
            self._detail_label.setText(
                "{}　|　{}　|　{}　|　{}×{} {}　|　{}".format(
                    info.name,
                    classify.format_duration(info.duration),
                    labels.fps,
                    info.width or 0,
                    info.height or 0,
                    labels.orientation,
                    classify.format_size(info.size_bytes),
                )
            )
        elif items:
            total = sum(item.info.size_bytes for item in items)
            self._detail_label.setText(
                "已选 {} 个，共 {}".format(len(items), classify.format_size(total))
            )
        else:
            self._detail_label.setText("")

    def _show_context_menu(self, position) -> None:
        index = self._view.indexAt(position)
        item: Optional[VideoItem] = index.data(ITEM_ROLE) if index.isValid() else None
        menu = QMenu(self)
        locate_action = menu.addAction("定位到文件夹（双击）")
        play_action = menu.addAction("用默认播放器打开")
        menu.addSeparator()
        copy_path_action = menu.addAction("复制完整路径")
        copy_name_action = menu.addAction("复制文件名")
        for action in (locate_action, play_action, copy_path_action, copy_name_action):
            action.setEnabled(item is not None)

        chosen = menu.exec(self._view.viewport().mapToGlobal(position))
        if chosen is None or item is None:
            return
        if chosen is locate_action:
            reveal.reveal_in_file_manager(item.info.path)
        elif chosen is play_action:
            reveal.open_file(item.info.path)
        elif chosen is copy_path_action:
            QGuiApplication.clipboard().setText(str(item.info.path))
        elif chosen is copy_name_action:
            QGuiApplication.clipboard().setText(item.info.name)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if paths_from_mime(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        paths = paths_from_mime(event.mimeData())
        if paths:
            event.acceptProposedAction()
            self._start_scan(paths)

    # ------------------------------------------------------------------ 杂项

    def _update_status(self, finished: bool = False, completed: bool = True) -> None:
        total_items = self._model.rowCount()
        shown = self._proxy.rowCount()
        done, discovered = self._scan_progress
        if self._scanner.is_running:
            prefix = "正在识别… {}/{}".format(done, discovered)
        elif finished:
            prefix = "完成，共 {} 个视频".format(total_items) if completed else "已停止"
        elif total_items:
            prefix = "共 {} 个视频".format(total_items)
        else:
            prefix = "请选择或拖入一个文件夹"
        parts = [prefix]
        if total_items:
            parts.append("当前显示 {} 个".format(shown))
        if self._error_count:
            parts.append("{} 个无法识别".format(self._error_count))
        if not probe.FFPROBE:
            parts.append("未检测到 ffprobe（已使用内置解码器）")
        self._status_label.setText("　·　".join(parts))

    def _clear_cache(self) -> None:
        self._cache.clear()
        QMessageBox.information(self, config.APP_NAME, "缩略图缓存已清空。")

    def _show_about(self) -> None:
        ffprobe_path, ffmpeg_path = probe.backend_summary()
        QMessageBox.information(
            self,
            config.APP_NAME,
            "<b>{}</b><br><br>"
            "按时长 / 帧率 / 分辨率给视频分组，双击缩略图可在文件夹中定位。<br><br>"
            "ffprobe：{}<br>ffmpeg：{}".format(
                config.APP_NAME,
                ffprobe_path or "未安装（使用内置解码器）",
                ffmpeg_path or "未安装",
            ),
        )

    def _restore_settings(self) -> None:
        geometry = self._settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        recursive = self._settings.value("recursive", True, type=bool)
        self._recursive_box.blockSignals(True)
        self._recursive_box.setChecked(recursive)
        self._recursive_box.blockSignals(False)

        group_mode = self._settings.value("group_mode", classify.GROUP_MODES[0][0])
        index = self._group_combo.findData(group_mode)
        self._group_combo.setCurrentIndex(index if index >= 0 else 0)

        sort_field = self._settings.value("sort_field", "name")
        sort_index = self._sort_combo.findData(sort_field)
        self._sort_combo.setCurrentIndex(sort_index if sort_index >= 0 else 0)
        self._desc_box.setChecked(self._settings.value("sort_desc", False, type=bool))

        thumb_index = self._settings.value("thumb_index", config.DEFAULT_DISPLAY_INDEX, type=int)
        self._size_slider.setValue(max(0, min(thumb_index, len(config.DISPLAY_SIZES) - 1)))

        self._proxy.set_group(self._current_dimensions(), [])
        self._model.set_sort_field(self._sort_combo.currentData())
        self._on_sort_changed()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._settings.setValue("geometry", self.saveGeometry())
        self._flush_timer.stop()
        self._tree_timer.stop()
        self._scanner.wait_for_shutdown()
        super().closeEvent(event)


def _roots_message(roots: Sequence[Path]) -> str:
    if len(roots) == 1:
        return "当前文件夹：{}".format(roots[0])
    return "已选择 {} 个位置：{} 等".format(len(roots), roots[0].name)
