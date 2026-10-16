"""Расшифровка речи из аудиофайлов (эндпоинт /v1/transcribe)."""

import logging
from dataclasses import dataclass
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RawSegment:
    """Сегмент речи, распознанный моделью в одном канале."""

    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Segment:
    """Сегмент речи в итоговом ответе: с каналом и меткой говорящего."""

    start: float
    end: float
    speaker: Optional[str]
    channel: Optional[int]
    text: str


class TranscriptionError(Exception):
    """Ошибка транскрибации, которая возвращается клиенту с HTTP-кодом."""

    default_status_code: int = 500
    default_retry_after: Optional[int] = None

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        retry_after: Optional[int] = None,
    ) -> None:
        """Сообщение для клиента, HTTP-код и пауза до повтора (для 503)."""
        super().__init__(message, status_code, retry_after)
        self.message = message
        self.status_code = (
            status_code if status_code is not None else self.default_status_code
        )
        self.retry_after = (
            retry_after if retry_after is not None else self.default_retry_after
        )

    def __str__(self) -> str:
        """Текст ошибки — сообщение для клиента."""
        return self.message


class AudioFormatError(TranscriptionError):
    """Файл повреждён, пустой или не содержит аудиодорожки (422)."""

    default_status_code = 422


class AudioTooLongError(TranscriptionError):
    """Запись длиннее допустимого лимита (413)."""

    default_status_code = 413


class ModelUnavailableError(TranscriptionError):
    """Модель распознавания не найдена или не загрузилась (503)."""

    default_status_code = 503


class TranscriberBusyError(TranscriptionError):
    """Все слоты распознавания заняты, клиенту нужно повторить запрос (503)."""

    default_status_code = 503
    default_retry_after = 30


class TranscriptionCancelled(Exception):
    """Внутренний сигнал: обработка отменена по таймауту или флагу отмены."""


def parse_channel_labels(raw: Optional[str]) -> list[str]:
    """
    Разбор параметра channel_labels: метки через запятую.

    Пустые метки сохраняются как пустые строки, чтобы индекс метки
    совпадал с индексом канала.
    """
    if not raw:
        return []
    return [label.strip() for label in raw.split(",")]


def speaker_label(labels: list[str], channel: int) -> str:
    """Метка говорящего для канала; если метки нет — channel_N."""
    if channel < len(labels) and labels[channel]:
        return labels[channel]
    return f"channel_{channel}"


def build_segments(
    per_channel: list[list[RawSegment]], labels: list[str]
) -> list[Segment]:
    """
    Объединяет сегменты каналов в один список, отсортированный по времени.

    Для стерео (ровно два канала) заполняются channel и speaker, для моно
    оба поля остаются None. Сегменты с пустым текстом отбрасываются.
    """
    is_stereo = len(per_channel) == 2
    segments: list[Segment] = []

    for channel_index, raw_segments in enumerate(per_channel):
        for raw in raw_segments:
            text = raw.text.strip()
            if not text:
                continue
            segments.append(
                Segment(
                    start=raw.start,
                    end=raw.end,
                    speaker=speaker_label(labels, channel_index) if is_stereo else None,
                    channel=channel_index if is_stereo else None,
                    text=text,
                )
            )

    segments.sort(key=lambda s: (s.start, s.channel if s.channel is not None else 0))
    return segments


def build_response(
    *,
    filename: str,
    external_id: Optional[str],
    duration: float,
    channels: int,
    segments: list[Segment],
) -> dict:
    """Формирует тело успешного ответа /v1/transcribe."""
    return {
        "status": "success",
        "filename": filename,
        "external_id": external_id,
        "duration": round(duration, 1),
        "channels": channels,
        "model": settings.TRANSCRIPTION_MODEL,
        "language": "ru",
        "text_status": "ok" if segments else "no_speech",
        "text": " ".join(segment.text for segment in segments),
        "segments": [
            {
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "speaker": segment.speaker,
                "channel": segment.channel,
                "text": segment.text,
            }
            for segment in segments
        ],
    }
