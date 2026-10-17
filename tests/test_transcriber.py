"""Тесты Transcriber: загрузка модели, распознавание с отменой, слоты."""

import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app import transcription
from app.config import settings
from app.transcription import (
    ModelUnavailableError,
    RawSegment,
    Transcriber,
    TranscriberBusyError,
    TranscriptionCancelled,
    get_transcriber,
    model_dir,
    vad_dir,
)


def _segment(start: float, end: float, text: str) -> SimpleNamespace:
    """Сегмент в формате onnx-asr (SegmentResult)."""
    return SimpleNamespace(start=start, end=end, text=text)


class StubModel:
    """Заглушка адаптера onnx-asr: recognize отдаёт итератор сегментов."""

    def __init__(self, segments=None, on_first_segment=None):
        self.segments = segments or []
        self.on_first_segment = on_first_segment
        self.calls = []
        self.pulled = 0

    def recognize(self, waveform, *, sample_rate=16000):
        self.calls.append((waveform, sample_rate))
        return self._iterate()

    def _iterate(self):
        for index, segment in enumerate(self.segments):
            if index == 0 and self.on_first_segment:
                self.on_first_segment()
            self.pulled += 1
            yield segment


def _transcriber(model: StubModel) -> Transcriber:
    """Transcriber, который отдаёт готовую заглушку вместо загрузки модели."""
    return Transcriber(model_factory=lambda: model)


def _audio(samples: int = 1600) -> np.ndarray:
    """Тишина достаточной длины (от 0.1 с): более короткий вход модели не отдаётся."""
    return np.zeros(samples, dtype=np.int16)


def _far_deadline() -> float:
    """Дедлайн, до которого точно ничего не истечёт."""
    return time.monotonic() + 3600


@pytest.mark.unit
class TestRecognize:
    """Тесты распознавания одного канала."""

    def test_recognize_converts_int16_to_float32(self):
        """Модель получает float32 в диапазоне [-1, 1] и частоту 16 кГц."""
        model = StubModel()
        samples = _audio()
        samples[:4] = [0, 16384, -32768, 32767]

        _transcriber(model).recognize(samples, threading.Event(), _far_deadline())

        waveform, sample_rate = model.calls[0]
        assert waveform.dtype == np.float32
        assert waveform[:4].tolist() == pytest.approx([0.0, 0.5, -1.0, 32767 / 32768])
        assert sample_rate == 16000

    def test_recognize_maps_segments(self):
        """Сегменты onnx-asr превращаются в RawSegment."""
        model = StubModel([_segment(0.5, 2.0, "привет"), _segment(3, 4, "мир")])

        result = _transcriber(model).recognize(
            _audio(), threading.Event(), _far_deadline()
        )

        assert result == [RawSegment(0.5, 2.0, "привет"), RawSegment(3.0, 4.0, "мир")]

    def test_recognize_stops_on_cancel_event(self):
        """Выставленный флаг отмены останавливает чтение следующих сегментов."""
        cancel = threading.Event()
        model = StubModel(
            [_segment(0, 1, "а"), _segment(1, 2, "б"), _segment(2, 3, "в")],
            on_first_segment=cancel.set,
        )

        with pytest.raises(TranscriptionCancelled):
            _transcriber(model).recognize(_audio(), cancel, _far_deadline())

        assert model.pulled == 1

    def test_recognize_stops_on_deadline(self):
        """Истёкший дедлайн — отмена без обращения к модели."""
        model = StubModel([_segment(0, 1, "а")])

        with pytest.raises(TranscriptionCancelled):
            _transcriber(model).recognize(
                _audio(),
                threading.Event(),
                time.monotonic() - 1,
            )

        assert model.calls == []

    @pytest.mark.parametrize("samples", [1, 300, 1599])
    def test_recognize_too_short_audio_skips_model(self, samples):
        """Короче 0.1 с в модель не уходит: silero падает на слишком коротком входе."""
        model = StubModel([_segment(0, 1, "а")])

        result = _transcriber(model).recognize(
            np.zeros(samples, dtype=np.int16), threading.Event(), _far_deadline()
        )

        assert result == []
        assert model.calls == []

    def test_recognize_minimum_length_audio_reaches_model(self):
        """Ровно 0.1 с (1600 отсчётов) уже передаётся в модель."""
        model = StubModel([])

        _transcriber(model).recognize(
            np.zeros(1600, dtype=np.int16), threading.Event(), _far_deadline()
        )

        assert len(model.calls) == 1

    def test_recognize_empty_audio_gives_no_segments(self):
        """Беззвучный канал — пустой список, не ошибка."""
        model = StubModel([])

        result = _transcriber(model).recognize(
            np.zeros(1, dtype=np.int16), threading.Event(), _far_deadline()
        )

        assert result == []


@pytest.mark.unit
class TestModelLoading:
    """Тесты ленивой загрузки модели."""

    def test_model_loaded_once(self):
        """Фабрика вызывается один раз на несколько распознаваний."""
        factory = MagicMock(return_value=StubModel())
        transcriber = Transcriber(model_factory=factory)
        samples = _audio()

        transcriber.recognize(samples, threading.Event(), _far_deadline())
        transcriber.recognize(samples, threading.Event(), _far_deadline())

        assert factory.call_count == 1

    def test_model_loaded_once_under_concurrency(self):
        """Параллельные первые запросы не грузят модель дважды."""
        calls = []

        def slow_factory():
            calls.append(1)
            time.sleep(0.05)
            return StubModel()

        transcriber = Transcriber(model_factory=slow_factory)
        samples = _audio()
        threads = [
            threading.Thread(
                target=transcriber.recognize,
                args=(samples, threading.Event(), _far_deadline()),
            )
            for _ in range(4)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(calls) == 1

    def test_factory_failure_is_model_unavailable(self):
        """Ошибка загрузки модели превращается в ModelUnavailableError (503)."""
        transcriber = Transcriber(
            model_factory=MagicMock(side_effect=RuntimeError("x"))
        )

        with pytest.raises(ModelUnavailableError) as error:
            transcriber.recognize(_audio(), threading.Event(), _far_deadline())

        assert error.value.status_code == 503

    def test_failed_load_is_retried(self):
        """Неудачная загрузка не кэшируется: следующий запрос пробует снова."""
        factory = MagicMock(side_effect=[RuntimeError("x"), StubModel()])
        transcriber = Transcriber(model_factory=factory)
        samples = _audio()

        with pytest.raises(ModelUnavailableError):
            transcriber.recognize(samples, threading.Event(), _far_deadline())

        assert transcriber.recognize(samples, threading.Event(), _far_deadline()) == []

    def test_model_and_vad_directories(self):
        """Раскладка каталогов с весами внутри MODELS_DIR."""
        assert model_dir("/opt/models", "gigaam-v3-e2e-rnnt") == Path(
            "/opt/models/gigaam-v3-e2e-rnnt"
        )
        assert vad_dir("/opt/models") == Path("/opt/models/silero-vad")


@pytest.mark.unit
class TestWarmUp:
    """Тесты прогрева модели и статуса готовности."""

    def test_status_not_loaded_initially(self):
        """До первого обращения модель не загружена."""
        assert Transcriber(model_factory=StubModel).status == "not_loaded"

    def test_warm_up_loads_model_once(self):
        """Прогрев загружает модель; следующее распознавание её не перезагружает."""
        factory = MagicMock(return_value=StubModel())
        transcriber = Transcriber(model_factory=factory)

        transcriber.warm_up()
        transcriber.recognize(_audio(), threading.Event(), _far_deadline())

        assert transcriber.status == "ready"
        assert factory.call_count == 1

    def test_warm_up_failure_marks_unavailable(self):
        """Ошибка загрузки: ModelUnavailableError и статус unavailable."""
        transcriber = Transcriber(
            model_factory=MagicMock(side_effect=RuntimeError("x"))
        )

        with pytest.raises(ModelUnavailableError):
            transcriber.warm_up()

        assert transcriber.status == "unavailable"

    def test_status_recovers_after_successful_retry(self):
        """Повторный успешный прогрев возвращает статус ready."""
        factory = MagicMock(side_effect=[RuntimeError("x"), StubModel()])
        transcriber = Transcriber(model_factory=factory)

        with pytest.raises(ModelUnavailableError):
            transcriber.warm_up()
        transcriber.warm_up()

        assert transcriber.status == "ready"


@pytest.mark.unit
class TestDefaultModelLoader:
    """Тесты загрузчика по умолчанию (onnx-asr подменён)."""

    def test_missing_directories_raise_unavailable_without_download(
        self, tmp_path, monkeypatch
    ):
        """Нет каталога с весами — 503 и никаких попыток скачать модель."""
        monkeypatch.setattr(settings, "MODELS_DIR", str(tmp_path))

        with patch("onnx_asr.load_model") as load_model:
            with pytest.raises(ModelUnavailableError):
                transcription._load_default_model()

        load_model.assert_not_called()

    @pytest.mark.parametrize("quantization,expected", [("", None), ("int8", "int8")])
    def test_loader_passes_local_paths_and_options(
        self, tmp_path, monkeypatch, quantization, expected
    ):
        """Модель и VAD грузятся из локальных каталогов с нужными опциями."""
        monkeypatch.setattr(settings, "MODELS_DIR", str(tmp_path))
        monkeypatch.setattr(settings, "TRANSCRIPTION_QUANTIZATION", quantization)
        monkeypatch.setattr(settings, "TRANSCRIPTION_THREADS", 3)
        monkeypatch.setattr(settings, "TRANSCRIPTION_VAD_MIN_SILENCE_MS", 700)
        monkeypatch.setattr(settings, "TRANSCRIPTION_VAD_SPEECH_PAD_MS", 250)
        asr_path = model_dir(str(tmp_path), settings.TRANSCRIPTION_MODEL)
        vad_path = vad_dir(str(tmp_path))
        asr_path.mkdir()
        vad_path.mkdir()

        with (
            patch("onnx_asr.load_model") as load_model,
            patch("onnx_asr.load_vad") as load_vad,
        ):
            result = transcription._load_default_model()

        load_model.assert_called_once()
        args, kwargs = load_model.call_args
        assert args == (settings.TRANSCRIPTION_MODEL, asr_path)
        assert kwargs["quantization"] == expected
        assert kwargs["sess_options"].intra_op_num_threads == 3
        load_vad.assert_called_once()
        assert load_vad.call_args.args == ("silero", vad_path)
        load_model.return_value.with_vad.assert_called_once_with(
            load_vad.return_value,
            max_speech_duration_s=20.0,
            min_silence_duration_ms=700,
            speech_pad_ms=250,
        )
        assert result is load_model.return_value.with_vad.return_value


@pytest.mark.unit
class TestSlot:
    """Тесты ограничения числа одновременных распознаваний."""

    def test_slot_busy_raises(self, monkeypatch):
        """Второй запрос при занятом слоте получает TranscriberBusyError."""
        monkeypatch.setattr(settings, "TRANSCRIPTION_MAX_CONCURRENCY", 1)
        transcriber = Transcriber(model_factory=StubModel)

        with transcriber.slot(0.05):
            with pytest.raises(TranscriberBusyError) as error:
                with transcriber.slot(0.05):
                    pass

        assert error.value.status_code == 503
        assert error.value.retry_after == 30

    def test_slot_released_after_use(self, monkeypatch):
        """После выхода из блока слот снова доступен, в том числе после ошибки."""
        monkeypatch.setattr(settings, "TRANSCRIPTION_MAX_CONCURRENCY", 1)
        transcriber = Transcriber(model_factory=StubModel)

        with pytest.raises(RuntimeError):
            with transcriber.slot(0.05):
                raise RuntimeError("сбой внутри слота")

        with transcriber.slot(0.05):
            pass

    def test_slot_concurrency_two(self, monkeypatch):
        """При лимите 2 два слота берутся одновременно, третий — нет."""
        monkeypatch.setattr(settings, "TRANSCRIPTION_MAX_CONCURRENCY", 2)
        transcriber = Transcriber(model_factory=StubModel)

        with transcriber.slot(0.05), transcriber.slot(0.05):
            with pytest.raises(TranscriberBusyError):
                with transcriber.slot(0.05):
                    pass


@pytest.mark.unit
class TestGetTranscriber:
    """Тесты синглтона процесса."""

    def test_get_transcriber_returns_same_instance(self, monkeypatch):
        """Повторные вызовы возвращают один и тот же объект."""
        monkeypatch.setattr(transcription, "_transcriber", None)

        first = get_transcriber()
        second = get_transcriber()

        assert first is second
        assert isinstance(first, Transcriber)
