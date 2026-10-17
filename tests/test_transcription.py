"""Тесты модуля транскрибации аудио (app/transcription.py)."""

import pytest

from app.config import settings
from app.transcription import (
    AudioFormatError,
    AudioTooLongError,
    ModelUnavailableError,
    RawSegment,
    Segment,
    TranscriberBusyError,
    TranscriptionCancelled,
    TranscriptionError,
    build_response,
    build_segments,
    parse_channel_labels,
    speaker_label,
)


@pytest.mark.unit
class TestBuildSegments:
    """Тесты слияния сегментов каналов."""

    def test_build_segments_stereo_sorted_and_labeled(self):
        """Стерео: сегменты сортируются по времени, спикер берётся из меток."""
        per_channel = [
            [RawSegment(3.4, 5.85, "Здравствуйте")],
            [RawSegment(0.52, 3.1, "Добрый день")],
        ]

        segments = build_segments(per_channel, ["client", "operator"])

        assert [s.text for s in segments] == ["Добрый день", "Здравствуйте"]
        assert [s.speaker for s in segments] == ["operator", "client"]
        assert [s.channel for s in segments] == [1, 0]

    def test_build_segments_mono_has_null_speaker(self):
        """Моно: speaker и channel равны None."""
        segments = build_segments([[RawSegment(0.0, 1.0, "Привет")]], ["client"])

        assert len(segments) == 1
        assert segments[0].speaker is None
        assert segments[0].channel is None

    def test_build_segments_preserves_unrecognized_speech(self):
        """Выделенная VAD, но не распознанная речь сохраняет тайм-коды."""
        segments = build_segments(
            [[RawSegment(0.0, 1.0, "  "), RawSegment(1.0, 2.0, " текст ")]], []
        )

        assert [s.text for s in segments] == ["", "текст"]
        assert segments[0].start == 0.0
        assert segments[0].end == 1.0

    def test_build_segments_equal_start_orders_by_channel(self):
        """При одинаковом начале порядок определяется номером канала."""
        per_channel = [[RawSegment(1.0, 2.0, "а")], [RawSegment(1.0, 2.0, "б")]]

        segments = build_segments(per_channel, [])

        assert [s.channel for s in segments] == [0, 1]

    def test_build_segments_stereo_without_labels_uses_channel_names(self):
        """Стерео без меток: channel_0 / channel_1."""
        per_channel = [[RawSegment(0.0, 1.0, "а")], [RawSegment(2.0, 3.0, "б")]]

        segments = build_segments(per_channel, [])

        assert [s.speaker for s in segments] == ["channel_0", "channel_1"]

    def test_build_segments_all_channels_empty(self):
        """Оба канала без речи дают пустой список."""
        assert build_segments([[], []], ["client", "operator"]) == []


@pytest.mark.unit
class TestChannelLabels:
    """Тесты разбора и подстановки меток каналов."""

    def test_speaker_label_fallbacks(self):
        """Пустые и недостающие метки заменяются на channel_N."""
        labels = parse_channel_labels(" client , ,operator")

        assert labels == ["client", "", "operator"]
        assert speaker_label(labels, 0) == "client"
        assert speaker_label(labels, 1) == "channel_1"
        assert speaker_label(labels, 5) == "channel_5"
        assert parse_channel_labels(None) == []
        assert parse_channel_labels("") == []

    def test_cyrillic_labels_preserved(self):
        """Кириллические метки возвращаются как есть."""
        labels = parse_channel_labels("клиент,оператор")

        assert speaker_label(labels, 0) == "клиент"
        assert speaker_label(labels, 1) == "оператор"


@pytest.mark.unit
class TestBuildResponse:
    """Тесты формирования ответа API."""

    def test_build_response_no_speech(self):
        """Без сегментов: text_status = no_speech, пустые text и segments."""
        response = build_response(
            filename="call.mp3",
            external_id=None,
            duration=3.0,
            channels=1,
            segments=[],
        )

        assert response["status"] == "success"
        assert response["text"] == ""
        assert response["text_status"] == "no_speech"
        assert response["segments"] == []
        assert response["language"] == "ru"

    @pytest.mark.parametrize(
        "texts,status,text",
        [([""], "unrecognized", ""), (["", "Алло"], "partial", "Алло")],
    )
    def test_unrecognized_speech_is_not_silence(self, texts, status, text):
        response = build_response(
            filename="call.wav",
            external_id=None,
            duration=2.0,
            channels=1,
            segments=[
                Segment(i, i + 1, None, None, value) for i, value in enumerate(texts)
            ],
        )

        assert response["text_status"] == status
        assert response["text"] == text
        assert response["segments"][0]["text"] == ""

    def test_build_response_ok_text_joined(self):
        """Текст собирается из сегментов через пробел, поля соответствуют контракту."""
        segments = [
            Segment(0.523, 3.104, "operator", 1, "Добрый день"),
            Segment(3.4, 5.85, "client", 0, "Здравствуйте"),
        ]

        response = build_response(
            filename="звонок.mp3",
            external_id="rec-123",
            duration=183.44,
            channels=2,
            segments=segments,
        )

        assert response["text"] == "Добрый день Здравствуйте"
        assert response["text_status"] == "ok"
        assert response["filename"] == "звонок.mp3"
        assert response["external_id"] == "rec-123"
        assert response["duration"] == 183.4
        assert response["channels"] == 2
        assert response["model"] == settings.TRANSCRIPTION_MODEL
        assert response["segments"][0] == {
            "start": 0.52,
            "end": 3.1,
            "speaker": "operator",
            "channel": 1,
            "text": "Добрый день",
        }

    def test_build_response_mono_segment_has_null_speaker_and_channel(self):
        """Для моно в сегменте speaker и channel равны None."""
        response = build_response(
            filename="a.wav",
            external_id=None,
            duration=1.0,
            channels=1,
            segments=[Segment(0.0, 1.0, None, None, "текст")],
        )

        assert response["segments"][0]["speaker"] is None
        assert response["segments"][0]["channel"] is None
        assert response["external_id"] is None


@pytest.mark.unit
class TestErrors:
    """Тесты типов ошибок транскрибации."""

    def test_error_status_codes(self):
        """Каждый тип ошибки несёт свой HTTP-код."""
        assert AudioFormatError("x").status_code == 422
        assert AudioTooLongError("x").status_code == 413
        assert ModelUnavailableError("x").status_code == 503
        busy = TranscriberBusyError("x")
        assert busy.status_code == 503
        assert busy.retry_after == 30

    def test_error_carries_message(self):
        """Сообщение доступно клиенту через атрибут message."""
        error = AudioFormatError("файл повреждён")

        assert error.message == "файл повреждён"
        assert str(error) == "файл повреждён"
        assert isinstance(error, TranscriptionError)

    def test_cancelled_is_not_a_transcription_error(self):
        """Отмена — внутренний сигнал, а не ошибка для клиента."""
        assert not issubclass(TranscriptionCancelled, TranscriptionError)
