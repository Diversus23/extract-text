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


def _stereo_pcm(samples: int) -> np.ndarray:
    """Стерео с разными каналами: левый с сигналом, правый тихий.

    Одинаковые каналы считаются моно-записью, поэтому нули в обоих каналах
    для проверки разметки по каналам не годятся.
    """
    left = (np.arange(samples) % 100).astype(np.int16) * 50
    return np.stack([left, np.zeros(samples, dtype=np.int16)])


def _run(content=b"audio", *, pcm, info, model, labels=None, cancel=None, **kwargs):
    """Вызов transcribe_bytes с подменёнными probe/decode и моделью."""
    transcriber = Transcriber(model_factory=lambda: model)
    with (
        patch("app.transcription.probe_audio", return_value=info),
        patch("app.transcription.decode_audio", return_value=pcm),
    ):
        return transcribe_bytes(
            content,
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
            pcm=_stereo_pcm(16000 * 6),
            info=AudioInfo(duration=6.0, channels=2, format="wav"),
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
            pcm=_stereo_pcm(32000),
            info=AudioInfo(duration=2.0, channels=2, format="wav"),
            model=model,
            labels=["client", "operator"],
        )

        assert result.segments == [Segment(0.5, 2.0, "operator", 1, "Алло")]

    @pytest.mark.parametrize("offset", [0, 1])
    def test_identical_channels_are_recognized_once_as_mono(self, offset):
        """Моно, сохранённое как стерео (каналы совпадают), не даёт дублей реплик."""
        left = (np.arange(32000) % 100).astype(np.int16) * 50
        # ChannelModel с одним элементом: второй вызов recognize упал бы с IndexError
        model = ChannelModel([[(0.5, 2.0, "Алло")]])

        result = _run(
            pcm=np.stack([left, left + offset]),
            info=AudioInfo(duration=2.0, channels=2, format="wav"),
            model=model,
            labels=["client", "operator"],
        )

        assert model.calls == 1
        assert result.channels == 2
        assert result.segments == [Segment(0.5, 2.0, None, None, "Алло")]

    def test_clearly_different_channels_stay_stereo(self):
        """Каналы, различающиеся заметно, остаются стерео с разметкой говорящих."""
        model = ChannelModel([[(0.0, 1.0, "а")], [(2.0, 3.0, "б")]])

        result = _run(
            pcm=_stereo_pcm(16000 * 4),
            info=AudioInfo(duration=4.0, channels=2, format="wav"),
            model=model,
            labels=["client", "operator"],
        )

        assert model.calls == 2
        assert [s.speaker for s in result.segments] == ["client", "operator"]

    @pytest.mark.parametrize("samples", [1, 16000 * 10])
    def test_total_silence_gives_empty_segments(self, samples):
        """Тишина и сверхкороткий файл: пустой результат, а не ошибка."""
        model = ChannelModel([[], []])

        result = _run(
            pcm=np.zeros((2, samples), dtype=np.int16),
            info=AudioInfo(duration=None, channels=2, format="wav"),
            model=model,
        )

        assert result.segments == []
        assert result.duration == pytest.approx(samples / 16000)

    def test_mono_has_null_speaker(self):
        """Моно: speaker и channel равны None."""
        model = ChannelModel([[(0.0, 1.0, "Привет")]])

        result = _run(
            pcm=np.zeros((1, 16000), dtype=np.int16),
            info=AudioInfo(duration=1.0, channels=1, format="wav"),
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
            info=AudioInfo(duration=1.0, channels=6, format="wav"),
            model=model,
        )

        assert result.channels == 6
        assert result.segments[0].speaker is None

    def test_upload_is_written_under_fixed_name_without_extension(self):
        """Файл пишется как input без расширения и не зависит от имени клиента."""
        seen = {}

        def fake_probe(path, **kwargs):
            seen["name"] = path.name
            seen["content"] = Path(path).read_bytes()
            return AudioInfo(1.0, 1, "wav")

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
                channel_labels=[],
                cancel_event=threading.Event(),
                deadline=time.monotonic() + 60,
                transcriber=transcriber,
            )

        assert seen == {"name": "input", "content": b"RIFFdata"}

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
            info=AudioInfo(1.0, 1, "wav"),
            model=ChannelModel([[]]),
        )

        assert list(tmp_path.iterdir()) == []

    def test_slot_released_after_cancel(self):
        """После отмены слот свободен для следующего запроса."""
        cancel = threading.Event()
        cancel.set()
        transcriber = Transcriber(model_factory=lambda: ChannelModel([[]]))
        args = dict(
            channel_labels=[],
            deadline=time.monotonic() + 60,
            transcriber=transcriber,
        )

        with (
            patch(
                "app.transcription.probe_audio", return_value=AudioInfo(1.0, 1, "wav")
            ),
            patch(
                "app.transcription.decode_audio",
                return_value=np.zeros((1, 16000), dtype=np.int16),
            ),
        ):
            with pytest.raises(TranscriptionCancelled):
                transcribe_bytes(b"x", cancel_event=cancel, **args)

            with transcriber.slot(0.05):
                pass

    @pytest.mark.parametrize("expired", [False, True])
    def test_cancelled_job_never_starts_media_tools(self, expired):
        cancel = threading.Event()
        if not expired:
            cancel.set()
        transcriber = Transcriber(model_factory=lambda: ChannelModel([]))
        with (
            patch("app.transcription.probe_audio", side_effect=AssertionError("probe")),
            patch(
                "app.transcription.decode_audio", side_effect=AssertionError("decode")
            ),
        ):
            with pytest.raises(TranscriptionCancelled):
                transcribe_bytes(
                    b"audio",
                    channel_labels=[],
                    cancel_event=cancel,
                    deadline=time.monotonic() + (-1 if expired else 60),
                    transcriber=transcriber,
                )

    def test_cancel_during_probe_prevents_decoding(self):
        cancel = threading.Event()

        def probe(*args, **kwargs):
            cancel.set()
            return AudioInfo(1.0, 1, "wav")

        transcriber = Transcriber(model_factory=lambda: ChannelModel([]))
        with (
            patch("app.transcription.probe_audio", side_effect=probe),
            patch(
                "app.transcription.decode_audio", side_effect=AssertionError("decode")
            ),
        ):
            with pytest.raises(TranscriptionCancelled):
                transcribe_bytes(
                    b"audio",
                    channel_labels=[],
                    cancel_event=cancel,
                    deadline=time.monotonic() + 60,
                    transcriber=transcriber,
                )

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
                        channel_labels=[],
                        cancel_event=threading.Event(),
                        deadline=time.monotonic() + 60,
                        transcriber=transcriber,
                    )

        probe.assert_not_called()
        decode.assert_not_called()
