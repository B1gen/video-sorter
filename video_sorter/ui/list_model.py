"""缩略图列表的数据模型、过滤代理和绘制委托。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QRect,
    QSize,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from .. import classify, config
from ..models import VideoInfo, VideoLabels

ITEM_ROLE = int(Qt.ItemDataRole.UserRole) + 1
SORT_ROLE = int(Qt.ItemDataRole.UserRole) + 2

SORT_FIELDS = (
    ("name", "文件名"),
    ("duration", "时长"),
    ("fps", "帧率"),
    ("resolution", "分辨率"),
    ("size", "文件大小"),
)


@dataclass
class VideoItem:
    info: VideoInfo
    labels: VideoLabels
    image: Optional[QImage] = None
    _pixmaps: Dict[Tuple[int, int], QPixmap] = field(default_factory=dict, repr=False)

    @property
    def meta_text(self) -> str:
        if self.info.error:
            return self.info.error
        parts = [
            classify.format_duration(self.info.duration),
            self.labels.fps,
            self.labels.resolution,
        ]
        if self.labels.orientation in ("竖屏", "方形"):
            parts.append(self.labels.orientation)
        return "  ·  ".join(parts)

    def pixmap(self, width: int, height: int) -> Optional[QPixmap]:
        if self.image is None:
            return None
        key = (width, height)
        cached = self._pixmaps.get(key)
        if cached is None:
            scaled = self.image.scaled(
                width,
                height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            cached = QPixmap.fromImage(scaled)
            self._pixmaps.clear()
            self._pixmaps[key] = cached
        return cached

    def sort_value(self, field_name: str):
        info = self.info
        if field_name == "duration":
            return info.duration or 0.0
        if field_name == "fps":
            return info.fps or 0.0
        if field_name == "resolution":
            return float((info.width or 0) * (info.height or 0))
        if field_name == "size":
            return float(info.size_bytes)
        return info.name.lower()


class VideoListModel(QAbstractListModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: List[VideoItem] = []
        self._sort_field = "name"

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        item = self._items[index.row()]
        if role == ITEM_ROLE:
            return item
        if role == SORT_ROLE:
            return item.sort_value(self._sort_field)
        if role == Qt.ItemDataRole.DisplayRole:
            return item.info.name
        if role == Qt.ItemDataRole.ToolTipRole:
            return _tooltip(item)
        return None

    def add_many(self, items: Sequence[VideoItem]) -> None:
        if not items:
            return
        start = len(self._items)
        self.beginInsertRows(QModelIndex(), start, start + len(items) - 1)
        self._items.extend(items)
        self.endInsertRows()

    def clear(self) -> None:
        self.beginResetModel()
        self._items = []
        self.endResetModel()

    def items(self) -> List[VideoItem]:
        return self._items

    def set_sort_field(self, field_name: str) -> None:
        if field_name == self._sort_field:
            return
        self._sort_field = field_name
        if self._items:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self._items) - 1, 0), [SORT_ROLE]
            )

    def drop_pixmap_cache(self) -> None:
        for item in self._items:
            item._pixmaps.clear()
        if self._items:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._items) - 1, 0),
                [Qt.ItemDataRole.DecorationRole],
            )


class VideoFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSortRole(SORT_ROLE)
        self.setDynamicSortFilter(True)
        self._dimensions: Tuple[str, ...] = ()
        self._group_path: Tuple[str, ...] = ()
        self._text = ""

    def set_group(self, dimensions: Sequence[str], group_path: Sequence[str]) -> None:
        self._dimensions = tuple(dimensions)
        self._group_path = tuple(group_path)
        self.invalidateFilter()

    def set_text(self, text: str) -> None:
        self._text = text.strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:  # noqa: N802
        index = self.sourceModel().index(source_row, 0, source_parent)
        item: Optional[VideoItem] = index.data(ITEM_ROLE)
        if item is None:
            return False
        if self._text and self._text not in item.info.name.lower():
            return False
        if self._group_path:
            actual = classify.group_path(item.labels, self._dimensions)
            if tuple(actual[: len(self._group_path)]) != self._group_path:
                return False
        return True


def item_size(display_size: Tuple[int, int]) -> QSize:
    """网格尺寸和委托的 sizeHint 必须一致，否则文字区会被算窄、文件名被过度省略。"""
    width, height = display_size
    return QSize(
        width + config.ITEM_MARGIN * 2 + 4,
        height + config.TEXT_AREA_HEIGHT + config.ITEM_MARGIN * 2 + 6,
    )


class ThumbnailDelegate(QStyledItemDelegate):
    def __init__(self, display_size: Tuple[int, int], parent=None) -> None:
        super().__init__(parent)
        self.display_size = display_size

    def sizeHint(self, option, index: QModelIndex) -> QSize:  # noqa: N802
        return item_size(self.display_size)

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        item: Optional[VideoItem] = index.data(ITEM_ROLE)
        if item is None:
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = option.rect.adjusted(4, 4, -4, -4)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            painter.setBrush(QColor(56, 118, 214, 60))
            painter.setPen(QPen(QColor(56, 118, 214), 1.5))
        elif hovered:
            painter.setBrush(QColor(127, 127, 127, 32))
            painter.setPen(Qt.PenStyle.NoPen)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 6, 6)

        width, height = self.display_size
        thumb_rect = QRect(rect.left() + 4, rect.top() + 4, rect.width() - 8, height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(24, 24, 27))
        painter.drawRoundedRect(thumb_rect, 4, 4)

        pixmap = item.pixmap(width, height)
        if pixmap is not None and not pixmap.isNull():
            target = QRect(0, 0, pixmap.width(), pixmap.height())
            target.moveCenter(thumb_rect.center())
            painter.drawPixmap(target, pixmap)
        else:
            painter.setPen(QColor(150, 150, 155))
            painter.drawText(
                thumb_rect,
                int(Qt.AlignmentFlag.AlignCenter),
                "无缩略图" if not item.info.error else "读取失败",
            )

        badge = classify.format_duration(item.info.duration)
        if badge != "--:--":
            _draw_badge(painter, thumb_rect, badge)

        text_rect = QRect(
            rect.left() + 4,
            thumb_rect.bottom() + 5,
            rect.width() - 8,
            rect.bottom() - thumb_rect.bottom() - 6,
        )
        name_font = QFont(option.font)
        metrics = QFontMetrics(name_font)
        painter.setFont(name_font)
        painter.setPen(option.palette.text().color())
        name = metrics.elidedText(
            item.info.name, Qt.TextElideMode.ElideMiddle, text_rect.width()
        )
        line_height = metrics.height()
        painter.drawText(
            QRect(text_rect.left(), text_rect.top(), text_rect.width(), line_height),
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
            name,
        )

        meta_font = QFont(option.font)
        meta_font.setPointSizeF(max(7.5, option.font.pointSizeF() - 1.0))
        painter.setFont(meta_font)
        meta_metrics = QFontMetrics(meta_font)
        painter.setPen(QColor(200, 80, 80) if item.info.error else QColor(140, 140, 148))
        meta = meta_metrics.elidedText(
            item.meta_text, Qt.TextElideMode.ElideRight, text_rect.width()
        )
        painter.drawText(
            QRect(
                text_rect.left(),
                text_rect.top() + line_height,
                text_rect.width(),
                meta_metrics.height(),
            ),
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
            meta,
        )
        painter.restore()


def _draw_badge(painter: QPainter, thumb_rect: QRect, text: str) -> None:
    metrics = QFontMetrics(painter.font())
    padding = 5
    badge_width = metrics.horizontalAdvance(text) + padding * 2
    badge_height = metrics.height() + 2
    badge = QRect(
        thumb_rect.right() - badge_width - 5,
        thumb_rect.bottom() - badge_height - 5,
        badge_width,
        badge_height,
    )
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(0, 0, 0, 170))
    painter.drawRoundedRect(badge, 3, 3)
    painter.setPen(QColor(240, 240, 240))
    painter.drawText(badge, int(Qt.AlignmentFlag.AlignCenter), text)


def _tooltip(item: VideoItem) -> str:
    info = item.info
    rows = [
        "<b>{}</b>".format(_escape(info.name)),
        _escape(str(info.path.parent)),
        "",
        "时长：{}（{}）".format(
            classify.format_duration(info.duration), _escape(item.labels.duration)
        ),
        "帧率：{}".format(_escape(item.labels.fps)),
        "分辨率：{} {}".format(
            "{}×{}".format(info.width, info.height) if info.width else "未知",
            _escape(item.labels.orientation),
        ),
        "分类：{}".format(_escape(item.labels.resolution)),
        "大小：{}".format(classify.format_size(info.size_bytes)),
    ]
    if info.codec:
        rows.append("编码：{}".format(_escape(info.codec)))
    if info.error:
        rows.append("<span style='color:#c05050'>{}</span>".format(_escape(info.error)))
    return "<div style='white-space:nowrap'>{}</div>".format("<br>".join(rows))


def _escape(text: str) -> str:
    return (
        str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
