"""音轨识别的测试：python tests/test_audio.py 或 pytest 都能跑。"""

from __future__ import annotations

import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from video_sorter import classify  # noqa: E402
from video_sorter.containers import has_audio_track  # noqa: E402
from video_sorter.models import VideoInfo  # noqa: E402
from video_sorter.probe import parse_max_volume  # noqa: E402


def _box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def _iso_track(handler: bytes) -> bytes:
    hdlr = _box(b"hdlr", b"\x00" * 8 + handler + b"\x00" * 12 + b"\x00")
    return _box(b"trak", _box(b"tkhd", b"\x00" * 84) + _box(b"mdia", hdlr))


def _iso_file(handlers, moov_last: bool = False) -> bytes:
    ftyp = _box(b"ftyp", b"isom\x00\x00\x02\x00isomiso2mp41")
    moov = _box(b"moov", _box(b"mvhd", b"\x00" * 100) + b"".join(_iso_track(h) for h in handlers))
    mdat = _box(b"mdat", b"\x00" * 64)
    return ftyp + (mdat + moov if moov_last else moov + mdat)


def _ebml(element_id: int, payload: bytes) -> bytes:
    id_bytes = element_id.to_bytes((element_id.bit_length() + 7) // 8, "big")
    return id_bytes + bytes([0x80 | len(payload)]) + payload if len(payload) < 127 else (
        id_bytes + (0x4000 | len(payload)).to_bytes(2, "big") + payload
    )


def _mkv_file(track_types) -> bytes:
    header = _ebml(0x1A45DFA3, _ebml(0x4282, b"matroska"))
    entries = b"".join(
        _ebml(0xAE, _ebml(0xD7, bytes([index + 1])) + _ebml(0x83, bytes([kind])))
        for index, kind in enumerate(track_types)
    )
    segment_body = _ebml(0x1549A966, _ebml(0x2AD7B1, b"\x0f\x42\x40")) + _ebml(
        0x1654AE6B, entries
    ) + _ebml(0x1F43B675, b"\x00" * 8)
    segment = bytes.fromhex("18538067") + bytes([0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
    return header + segment + segment_body


def _check(name: str, data: bytes):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / name
        path.write_bytes(data)
        return has_audio_track(path)


def test_iso_audio_detection():
    assert _check("a.mp4", _iso_file([b"vide", b"soun"])) is True
    assert _check("a.mp4", _iso_file([b"vide"])) is False
    assert _check("a.mov", _iso_file([b"vide", b"soun"], moov_last=True)) is True
    assert _check("a.mp4", b"not a video") is None


def test_matroska_audio_detection():
    assert _check("a.mkv", _mkv_file([1, 2])) is True
    assert _check("a.webm", _mkv_file([1])) is False
    assert _check("a.mkv", b"\x00\x01garbage") is None


def test_unsupported_container_is_unknown():
    assert _check("a.avi", b"RIFF....AVI ") is None


def test_parse_max_volume():
    log = "[Parsed_volumedetect_0 @ 0x1] mean_volume: -20.5 dB\n[Parsed_volumedetect_0 @ 0x1] max_volume: -3.2 dB\n"
    assert parse_max_volume(log) == -3.2
    assert parse_max_volume("max_volume: -91.0 dB") == -91.0
    assert parse_max_volume("max_volume: -inf dB") == float("-inf")
    assert parse_max_volume("no audio here") is None


def test_audio_labels_and_grouping():
    assert classify.audio_label(True, False)[0] == classify.AUDIO_PRESENT
    assert classify.audio_label(True, None)[0] == classify.AUDIO_PRESENT
    assert classify.audio_label(True, True)[0] == classify.AUDIO_SILENT
    assert classify.audio_label(False, None)[0] == classify.AUDIO_NONE
    assert classify.audio_label(None, None)[0] == classify.AUDIO_UNKNOWN

    info = VideoInfo(path=Path("a.mp4"), duration=8.0, width=1920, height=1080, has_audio=False)
    labels = classify.labels_for(info)
    assert classify.is_muted(labels)
    assert classify.group_path(labels, classify.dimensions_for_mode("audio_duration")) == [
        classify.AUDIO_NONE,
        "5–10 秒",
    ]


def test_audio_fields_round_trip_through_cache_dict():
    info = VideoInfo(path=Path("a.mp4"), has_audio=True, audio_silent=True)
    restored = VideoInfo.from_dict(info.path, info.to_dict())
    assert restored.has_audio is True and restored.audio_silent is True


if __name__ == "__main__":
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            function()
            print("ok", name)
