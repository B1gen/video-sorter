"""程序图标：用代码画出来，运行时当窗口图标，打包时导出成 exe 图标。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPixmap

ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale(size / 256.0, size / 256.0)

    gradient = QLinearGradient(0, 0, 256, 256)
    gradient.setColorAt(0.0, QColor(66, 133, 244))
    gradient.setColorAt(1.0, QColor(38, 76, 170))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(QRectF(12, 12, 232, 232), 52, 52)

    # 三条长短不一的“分组”横条
    painter.setBrush(QColor(255, 255, 255, 110))
    for index, width in enumerate((150, 110, 70)):
        painter.drawRoundedRect(QRectF(46, 150 + index * 26, width, 14), 7, 7)

    play = QPainterPath()
    play.moveTo(QPointF(104, 50))
    play.lineTo(QPointF(104, 128))
    play.lineTo(QPointF(170, 89))
    play.closeSubpath()
    painter.setBrush(QColor(255, 255, 255))
    painter.drawPath(play)
    painter.end()
    return image


def app_icon() -> QIcon:
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(QPixmap.fromImage(render(size)))
    return icon
