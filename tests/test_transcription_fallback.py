"""Восстановление пустых речевых сегментов без изменения распознанного текста."""

from types import SimpleNamespace

import numpy as np

from app.transcription import SpeechRecognitionModel


def test_fallback_recognizes_only_empty_speech_interval():
    class Primary:
        def recognize(self, waveform, *, sample_rate):
            yield SimpleNamespace(start=0.0, end=1.0, text="Готовый текст")
            yield SimpleNamespace(start=1.0, end=2.0, text=" ")

    class Fallback:
        def recognize(self, waveform, *, sample_rate):
            # Первый интервал не должен попасть в резервное распознавание.
            assert sample_rate == 16000
            assert len(waveform) == 16000
            assert np.all(waveform == 0.25)
            return " Алло "

    waveform = np.concatenate([np.zeros(16000), np.full(16000, 0.25)])
    segments = list(
        SpeechRecognitionModel(Primary(), Fallback()).recognize(
            waveform, sample_rate=16000
        )
    )

    assert [segment.text for segment in segments] == ["Готовый текст", "Алло"]
    assert segments[1].start == 1.0
    assert segments[1].end == 2.0


def test_both_models_empty_preserve_detected_speech():
    class Primary:
        def recognize(self, waveform, *, sample_rate):
            yield SimpleNamespace(start=0.0, end=1.0, text="")

    class Fallback:
        def recognize(self, waveform, *, sample_rate):
            return ""

    segments = list(
        SpeechRecognitionModel(Primary(), Fallback()).recognize(
            np.zeros(16000), sample_rate=16000
        )
    )

    assert len(segments) == 1
    assert segments[0].text == ""
    assert segments[0].end == 1.0
