"""音轨识别的测试：python tests/test_audio.py 或 pytest 都能跑。"""

from __future__ import annotations

import struct
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from video_sorter import audio, classify, probe  # noqa: E402

av = audio.av
from video_sorter.containers import has_audio_track  # noqa: E402
from video_sorter.models import VideoInfo  # noqa: E402


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


def test_parse_loudest_rms():
    log = (
        "frame:0    pts:0       pts_time:0\n"
        "lavfi.astats.Overall.RMS_level=-60.5\n"
        "lavfi.astats.Overall.RMS_level=-31.2\n"
        "lavfi.astats.Overall.RMS_level=-inf\n"
        "lavfi.astats.Overall.RMS_level=nan\n"
    )
    assert probe.parse_loudest_rms(log) == -31.2
    assert probe.parse_loudest_rms("lavfi.astats.Overall.RMS_level=-inf") == float("-inf")
    assert probe.parse_loudest_rms("no audio here") is None


_RATE = 16000


def _silence(count: int) -> np.ndarray:
    return np.zeros(count)


def _hiss(count: int) -> np.ndarray:
    # 约 -50 dBFS 的白噪声：峰值能到 -40 dB 左右，但听起来就是没声音
    return np.random.default_rng(0).uniform(-0.0055, 0.0055, count)


def _tone(count: int) -> np.ndarray:
    return 0.05 * np.sin(np.arange(count) * 2 * np.pi * 440 / _RATE)


def _beep_at_end(count: int) -> np.ndarray:
    samples = np.zeros(count)
    samples[-800:] = 0.3
    return samples


def _write_audio(path: Path, tracks, seconds: float = 2.0) -> None:
    total = int(seconds * _RATE)
    container = av.open(str(path), "w")
    streams = [container.add_stream("pcm_s16le", rate=_RATE, layout="mono") for _ in tracks]
    chunk = 1600
    for start in range(0, total, chunk):
        for stream, make in zip(streams, tracks):
            samples = make(total)[start : start + chunk]
            frame = av.AudioFrame.from_ndarray(
                (samples * 32767).astype(np.int16)[None, :], format="s16", layout="mono"
            )
            frame.sample_rate = _RATE
            frame.pts = start
            for packet in stream.encode(frame):
                container.mux(packet)
    for stream in streams:
        for packet in stream.encode(None):
            container.mux(packet)
    container.close()


def _inspect(tracks):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "a.mkv"
        _write_audio(path, tracks)
        return audio.inspect(path)


def test_silence_detection_with_pyav():
    if not audio.available():
        return
    assert _inspect([_silence]) == (True, True)
    assert _inspect([_hiss]) == (True, True)
    assert _inspect([_tone]) == (True, False)
    assert _inspect([_beep_at_end]) == (True, False)
    # 有一条音轨有声音就算有声音
    assert _inspect([_silence, _tone]) == (True, False)
    assert _inspect([_silence, _hiss]) == (True, True)


def test_audio_labels_and_grouping():
    assert classify.audio_label(True, False)[0] == classify.AUDIO_PRESENT
    assert classify.audio_label(True, None)[0] == classify.AUDIO_UNMEASURED
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
