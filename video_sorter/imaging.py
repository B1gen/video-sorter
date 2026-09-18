from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtGui import QImage


def to_qimage(frame: Optional[np.ndarray]) -> Optional[QImage]:
    """把 OpenCV 的 BGR 数组转成 QImage（拷贝一份，避免引用已释放的缓冲区）。"""
    if frame is None or not frame.size:
        return None
    if frame.ndim == 2:
        frame = np.repeat(frame[:, :, np.newaxis], 3, axis=2)
    if frame.shape[2] == 4:
        frame = frame[:, :, :3]
    frame = np.ascontiguousarray(frame)
    height, width = frame.shape[:2]
    image = QImage(frame.data, width, height, 3 * width, QImage.Format.Format_BGR888)
    return image.copy()
