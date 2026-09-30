"""不依赖 ffprobe，直接读容器头判断有没有音轨。

只支持最常见的两类容器：
* MP4 / MOV / M4V / 3GP（ISO BMFF）：moov → trak → mdia → hdlr 的 handler 为 ``soun``；
* MKV / WebM（EBML）：Segment → Tracks → TrackEntry 的 TrackType 为 2。
其他格式返回 None（未知）。
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import BinaryIO, Iterator, Optional, Tuple

ISO_SUFFIXES = frozenset({".mp4", ".m4v", ".mov", ".3gp", ".3g2", ".f4v"})
MATROSKA_SUFFIXES = frozenset({".mkv", ".webm"})

# moov 通常只有几百 KB，超过这个大小就不读了，免得坏文件吃光内存
_MAX_MOOV_BYTES = 64 * 1024 * 1024
_ISO_CONTAINER_BOXES = (b"trak", b"mdia")

_EBML_SEGMENT = 0x18538067
_EBML_TRACKS = 0x1654AE6B
_EBML_TRACK_ENTRY = 0xAE
_EBML_TRACK_TYPE = 0x83
_EBML_CLUSTER = 0x1F43B675
_MATROSKA_AUDIO = 2


def has_audio_track(path: Path) -> Optional[bool]:
    suffix = path.suffix.lower()
    try:
        with path.open("rb") as handle:
            if suffix in ISO_SUFFIXES:
                return _iso_has_audio(handle)
            if suffix in MATROSKA_SUFFIXES:
                return _matroska_has_audio(handle)
    except (OSError, ValueError, struct.error):
        return None
    return None


# --------------------------------------------------------------------------- #
# ISO BMFF
# --------------------------------------------------------------------------- #


def _iso_has_audio(handle: BinaryIO) -> Optional[bool]:
    moov = _read_top_level_box(handle, b"moov")
    if moov is None:
        return None
    found_track = False
    for box_type, payload in _iter_boxes(moov):
        if box_type != b"trak":
            continue
        found_track = True
        if _handler_type(payload) == b"soun":
            return True
    return False if found_track else None


def _read_top_level_box(handle: BinaryIO, wanted: bytes) -> Optional[bytes]:
    handle.seek(0, 2)
    file_size = handle.tell()
    offset = 0
    while offset + 8 <= file_size:
        handle.seek(offset)
        header = handle.read(16)
        if len(header) < 8:
            return None
        size, box_type = struct.unpack(">I4s", header[:8])
        header_size = 8
        if size == 1:
            if len(header) < 16:
                return None
            size = struct.unpack(">Q", header[8:16])[0]
            header_size = 16
        elif size == 0:
            size = file_size - offset
        if size < header_size:
            return None
        if box_type == wanted:
            body_size = size - header_size
            if body_size > _MAX_MOOV_BYTES:
                return None
            handle.seek(offset + header_size)
            return handle.read(body_size)
        offset += size
    return None


def _iter_boxes(data: bytes) -> Iterator[Tuple[bytes, bytes]]:
    offset = 0
    while offset + 8 <= len(data):
        size, box_type = struct.unpack(">I4s", data[offset : offset + 8])
        header_size = 8
        if size == 1:
            if offset + 16 > len(data):
                return
            size = struct.unpack(">Q", data[offset + 8 : offset + 16])[0]
            header_size = 16
        elif size == 0:
            size = len(data) - offset
        if size < header_size or offset + size > len(data):
            return
        yield box_type, data[offset + header_size : offset + size]
        offset += size


def _handler_type(trak: bytes) -> Optional[bytes]:
    for box_type, payload in _iter_boxes(trak):
        if box_type == b"hdlr" and len(payload) >= 12:
            # version/flags(4) + pre_defined(4) + handler_type(4)
            return payload[8:12]
        if box_type in _ISO_CONTAINER_BOXES:
            found = _handler_type(payload)
            if found is not None:
                return found
    return None


# --------------------------------------------------------------------------- #
# Matroska / WebM
# --------------------------------------------------------------------------- #


def _matroska_has_audio(handle: BinaryIO) -> Optional[bool]:
    handle.seek(0, 2)
    file_size = handle.tell()
    handle.seek(0)
    position = 0
    while position < file_size:
        element_id, size, position = _read_element_header(handle, position)
        if element_id == _EBML_SEGMENT:
            end = file_size if size is None else min(file_size, position + size)
            return _segment_has_audio(handle, position, end)
        if size is None:
            return None
        position += size
    return None


def _segment_has_audio(handle: BinaryIO, position: int, end: int) -> Optional[bool]:
    while position < end:
        element_id, size, position = _read_element_header(handle, position)
        if element_id == _EBML_TRACKS:
            if size is None or size > _MAX_MOOV_BYTES:
                return None
            handle.seek(position)
            return _tracks_have_audio(handle.read(size))
        if element_id == _EBML_CLUSTER or size is None:
            return None
        position += size
    return None


def _tracks_have_audio(data: bytes) -> Optional[bool]:
    found_track = False
    for element_id, payload in _iter_ebml(data):
        if element_id != _EBML_TRACK_ENTRY:
            continue
        found_track = True
        for child_id, value in _iter_ebml(payload):
            if child_id == _EBML_TRACK_TYPE and int.from_bytes(value, "big") == _MATROSKA_AUDIO:
                return True
    return False if found_track else None


def _read_element_header(handle: BinaryIO, position: int) -> Tuple[int, Optional[int], int]:
    handle.seek(position)
    head = handle.read(12)
    element_id, id_length = _read_vint(head, 0, keep_marker=True)
    size, size_length = _read_vint(head, id_length, keep_marker=False)
    return element_id, size, position + id_length + size_length


def _iter_ebml(data: bytes) -> Iterator[Tuple[int, bytes]]:
    offset = 0
    while offset < len(data):
        element_id, id_length = _read_vint(data, offset, keep_marker=True)
        size, size_length = _read_vint(data, offset + id_length, keep_marker=False)
        start = offset + id_length + size_length
        if size is None or start + size > len(data):
            return
        yield element_id, data[start : start + size]
        offset = start + size


def _read_vint(data: bytes, offset: int, keep_marker: bool) -> Tuple[Optional[int], int]:
    """EBML 变长整数；size 全 1 表示“未知长度”，返回 None。"""
    if offset >= len(data):
        raise ValueError("truncated EBML")
    first = data[offset]
    length = 1
    mask = 0x80
    while length <= 8 and not first & mask:
        length += 1
        mask >>= 1
    if length > 8 or offset + length > len(data):
        raise ValueError("bad EBML vint")
    value = first if keep_marker else first & (mask - 1)
    for byte in data[offset + 1 : offset + length]:
        value = (value << 8) | byte
    if not keep_marker and value == (1 << (7 * length)) - 1:
        return None, length
    return value, length
