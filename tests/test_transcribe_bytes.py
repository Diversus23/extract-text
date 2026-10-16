"""Тесты оркестрации transcribe_bytes (ffmpeg и модель подменены)."""

import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from app.config import settings
from app.transcription import (
    AudioFormatError,
    AudioInfo,
    Segment,
    Transcriber,
    TranscriberBusyError,
    TranscriptionCancelled,
    transcribe_bytes,
)


class ChannelModel:
    """Заглушка модели: каждый вызов recognize отдаёт сегменты следующего канала."""

    def __init__(self, per_call):
        self.per_call = list(per_call)
        self.calls = 0

    def recognize(self, waveform, *, sample_rate=16000):
        segments = self.per_call[self.calls]
        self.calls += 1
        return iter([SimpleNamespace(start=s, end=e, text=t) for s, e, t in segments])


def _run(content=b"audio", *, pcm, info, model, labels=None, cancel=None, **kwargs):
    """Вызов transcribe_bytes с подменёнными probe/decode и моделью."""
    transcriber = Transcriber(model_factory=lambda: model)
    with (
        patch("app.transcription.probe_audio", return_value=info),
        patch("app.transcription.decode_audio", return_value=pcm),
    ):
        return transcribe_bytes(
            content,
            extension=kwargs.pop("extension", "mp3"),
            channel_labels=labels or [],
            cancel_event=cancel or threading.Event(),
            deadline=time.monotonic() + 3600,
            transcriber=transcriber,
        )


@pytest.mark.unit
class TestTranscribeBytes:
    """Тесты сквозной обработки одного файла."""

    def test_stereo_result_has_labeled_segments(self):
        """Стерео: сегменты обоих каналов в хронологическом порядке с метками."""
        model = ChannelModel(
            [[(3.4, 5.85, "Здравствуйте")], [(0.5, 3.1, "Добрый день")]]
        )

        result = _run(
            pcm=np.zeros((2, 16000 * 6), dtype=np.int16),
            info=AudioInfo(duration=6.0, channels=2),
            model=model,
            labels=["client", "operator"],
        )

        assert result.channels == 2
        assert result.duration == pytest.approx(6.0)
        assert [(s.speaker, s.channel, s.text) for s in result.segments] == [
            ("operator", 1, "Добрый день"),
            ("client", 0, "Здравствуйте"),
        ]

    def test_one_silent_channel(self):
        """Один канал без речи: остаются сегменты другого канала, без ошибок."""
        model = ChannelModel([[], [(0.5, 2.0, "Алло")]])

        result = _run(
            pcm=np.zeros((2, 32000), dtype=np.int16),
            info=AudioInfo(duration=2.0, channels=2),
            model=model,
            labels=["client", "operator"],
        )

        assert result.segments == [Segment(0.5, 2.0, "operator", 1, "Алло")]

    @pytest.mark.parametrize("samples", [1, 16000 * 10])
    def test_total_silence_gives_empty_segments(self, samples):
        """Тишина и сверхкороткий файл: пустой результат, а не ошибка."""
        model = ChannelModel([[], []])

        result = _run(
            pcm=np.zeros((2, samples), dtype=np.int16),
            info=AudioInfo(duration=None, channels=2),
            model=model,
        )

        assert result.segments == []
        assert result.duration == pytest.approx(samples / 16000)

    def test_mono_has_null_speaker(self):
        """Моно: speaker и channel равны None."""
        model = ChannelModel([[(0.0, 1.0, "Привет")]])

        result = _run(
            pcm=np.zeros((1, 16000), dtype=np.int16),
            info=AudioInfo(duration=1.0, channels=1),
            model=model,
            labels=["client"],
        )

        assert result.channels == 1
        assert result.segments == [Segment(0.0, 1.0, None, None, "Привет")]

    def test_multichannel_source_reports_original_channel_count(self):
        """5.1 сводится в моно, но channels отражает исходный файл."""
        model = ChannelModel([[(0.0, 1.0, "текст")]])

        result = _run(
            pcm=np.zeros((1, 16000), dtype=np.int16),
            info=AudioInfo(duration=1.0, channels=6),
            model=model,
        )

        assert result.channels == 6
        assert result.segments[0].speaker is None

    def test_upload_is_written_under_fixed_name_with_extension(self):
        """Файл пишется во временный каталог как input.<расширение>."""
        seen = {}

        def fake_probe(path, extension):
            seen["name"] = path.name
            seen["content"] = Path(path).read_bytes()
            seen["extension"] = extension
            return AudioInfo(1.0, 1)

        transcriber = Transcriber(model_factory=lambda: ChannelModel([[]]))
        with (
            patch("app.transcription.probe_audio", side_effect=fake_probe),
            patch(
                "app.transcription.decode_audio",
                return_value=np.zeros((1, 16000), dtype=np.int16),
            ),
        ):
            transcribe_bytes(
                b"RIFFdata",
                extension="wav",
                channel_labels=[],
                cancel_event=threading.Event(),
                deadline=time.monotonic() + 60,
                transcriber=transcriber,
            )

        assert seen == {"name": "input.wav", "content": b"RIFFdata", "extension": "wav"}

    def test_temp_dir_removed_on_error(self, tmp_path, monkeypatch):
        """После ошибки временный каталог удалён."""
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
        transcriber = Transcriber(model_factory=lambda: ChannelModel([]))

        with patch(
            "app.transcription.probe_audio", side_effect=AudioFormatError("битый")
        ):
            with pytest.raises(AudioFormatError):
                transcribe_bytes(
                    b"x",
                    extension="mp3",
                    channel_labels=[],
                    cancel_event=threading.Event(),
                    deadline=time.monotonic() + 60,
                    transcriber=transcriber,
                )

        assert list(tmp_path.iterdir()) == []

    def test_temp_dir_removed_on_success(self, tmp_path, monkeypatch):
        """После успеха временный каталог тоже удалён."""
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

        _run(
            pcm=np.zeros((1, 16000), dtype=np.int16),
            info=AudioInfo(1.0, 1),
            model=ChannelModel([[]]),
        )

        assert list(tmp_path.iterdir()) == []

    def test_slot_released_after_cancel(self):
        """После отмены слот свободен для следующего запроса."""
        cancel = threading.Event()
        cancel.set()
        transcriber = Transcriber(model_factory=lambda: ChannelModel([[]]))
        args = dict(
            extension="mp3",
            channel_labels=[],
            deadline=time.monotonic() + 60,
            transcriber=transcriber,
        )

        with (
            patch("app.transcription.probe_audio", return_value=AudioInfo(1.0, 1)),
            patch(
                "app.transcription.decode_audio",
                return_value=np.zeros((1, 16000), dtype=np.int16),
            ),
        ):
            with pytest.raises(TranscriptionCancelled):
                transcribe_bytes(b"x", cancel_event=cancel, **args)

            with transcriber.slot(0.05):
                pass

    def test_busy_slot_rejects_before_decoding(self, monkeypatch):
        """Занятый слот отклоняет запрос до зондирования и декодирования."""
        monkeypatch.setattr(settings, "TRANSCRIPTION_MAX_CONCURRENCY", 1)
        monkeypatch.setattr(settings, "TRANSCRIPTION_QUEUE_WAIT_SECONDS", 0.05)
        transcriber = Transcriber(model_factory=lambda: ChannelModel([[]]))

        with (
            patch("app.transcription.probe_audio") as probe,
            patch("app.transcription.decode_audio") as decode,
        ):
            with transcriber.slot(0.05):
                with pytest.raises(TranscriberBusyError):
                    transcribe_bytes(
                        b"x",
                        extension="mp3",
                        channel_labels=[],
                        cancel_event=threading.Event(),
                        deadline=time.monotonic() + 60,
                        transcriber=transcriber,
                    )

        probe.assert_not_called()
        decode.assert_not_called()
