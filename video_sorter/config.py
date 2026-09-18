from __future__ import annotations

APP_NAME = "视频分类器"
ORG_NAME = "VideoSorter"

# 缓存里保存的缩略图尺寸；界面显示尺寸不超过它，缩放时才不会发虚。
THUMB_WIDTH = 352
THUMB_HEIGHT = 198

# 缩略图滑杆的档位（宽, 高）
DISPLAY_SIZES = ((160, 90), (224, 126), (288, 162), (352, 198))
DEFAULT_DISPLAY_INDEX = 1

TEXT_AREA_HEIGHT = 44
ITEM_MARGIN = 8
