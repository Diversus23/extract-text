"""Расшифровка речи из аудиофайлов (эндпоинт /v1/transcribe)."""

import json
import logging
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

import numpy as np

from app.config import settings
from app.utils import run_subprocess_with_limits

logger = logging.getLogger(__name__)

# Частота дискретизации, с которой работает модель распознавания
SAMPLE_RATE = 16000

# Демуксер ffmpeg принудительно выбирается по расширению: автоопределение формата
# позволило бы подсунуть плейлист/concat-скрипт и заставить ffmpeg читать сеть или файлы.
FFMPEG_DEMUXERS = {
    "mp3": "mp3",
    "wav": "wav",
    "ogg": "ogg",
    "opus": "ogg",
    "flac": "flac",
    "m4a": "mov",
    "aac": "aac",
    "wma": "asf",
    "amr": "amr",
}

PROBE_TIMEOUT_SECONDS = 30
DECODE_TIMEOUT_SECONDS = 120


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


@dataclass(frozen=True)
class AudioInfo:
    """Сведения об аудиофайле из ffprobe."""

    duration: Optional[float]
    channels: int


def _demuxer_for(extension: str) -> str:
    """Демуксер ffmpeg для расширения; неизвестное расширение — ошибка файла."""
    demuxer = FFMPEG_DEMUXERS.get(extension.lower())
    if demuxer is None:
        raise AudioFormatError(f"Неподдерживаемый формат аудио: .{extension}")
    return demuxer


def _run_media_tool(command: list, timeout: int) -> subprocess.CompletedProcess:
    """
    Запускает ffprobe/ffmpeg с ограничениями ресурсов.

    Отсутствие бинарника — проблема сервиса (503), а таймаут, лимит памяти
    и ненулевой код — проблема файла (422).
    """
    try:
        result = run_subprocess_with_limits(command, timeout=timeout, text=False)
    except FileNotFoundError as error:
        logger.error(f"Не найден {command[0]}: {error}")
        raise ModelUnavailableError("Сервис обработки аудио недоступен.") from error
    except (subprocess.TimeoutExpired, MemoryError) as error:
        logger.error(f"{command[0]} прерван ({type(error).__name__})")
        raise AudioFormatError("Не удалось обработать аудиофайл.") from error

    if result.returncode != 0:
        stderr = (result.stderr or b"").decode("utf-8", errors="replace")[:500]
        logger.warning(f"{command[0]} завершился с кодом {result.returncode}: {stderr}")
        raise AudioFormatError("Файл повреждён или не является аудиозаписью.")
    return result


def probe_audio(path: Path, extension: str) -> AudioInfo:
    """
    Определяет число каналов и длительность первой аудиодорожки через ffprobe.

    Длительность может быть неизвестна (None) — тогда лимит проверяется
    после декодирования.

    Raises:
        AudioFormatError: нет аудиодорожки или файл не читается.
        AudioTooLongError: известная длительность больше лимита.
    """
    command = [
        "ffprobe",
        "-v",
        "error",
        "-protocol_whitelist",
        "file",
        "-f",
        _demuxer_for(extension),
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=channels:format=duration",
        "-of",
        "json",
        str(path),
    ]
    result = _run_media_tool(command, PROBE_TIMEOUT_SECONDS)

    try:
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        channels = int(stream["channels"])
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise AudioFormatError("В файле не найдена аудиодорожка.") from error

    duration: Optional[float] = None
    try:
        parsed = float((data.get("format") or {}).get("duration"))
        if parsed > 0:
            duration = parsed
    except (TypeError, ValueError):
        duration = None

    if duration is not None and duration > settings.MAX_AUDIO_DURATION_SECONDS:
        raise AudioTooLongError(
            f"Запись длиннее допустимых {settings.MAX_AUDIO_DURATION_SECONDS} секунд."
        )
    return AudioInfo(duration=duration, channels=channels)


def decode_audio(path: Path, extension: str, channels: int) -> np.ndarray:
    """
    Декодирует первую аудиодорожку в PCM int16, 16 кГц.

    Returns:
        Массив формы (n_channels, n_samples): два канала для стерео, во всех
        остальных случаях один (микс в моно).

    Raises:
        AudioFormatError: ошибка декодирования или пустой результат.
        AudioTooLongError: декодированный звук длиннее лимита.
    """
    n_channels = 2 if channels == 2 else 1
    max_seconds = settings.MAX_AUDIO_DURATION_SECONDS
    command = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-protocol_whitelist",
        "file",
        "-f",
        _demuxer_for(extension),
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        str(n_channels),
        "-ar",
        str(SAMPLE_RATE),
        # Страховка на случай неизвестной длительности: декодируем не больше лимита + 1 с
        "-t",
        str(max_seconds + 1),
        "-f",
        "s16le",
        "-",
    ]
    result = _run_media_tool(command, DECODE_TIMEOUT_SECONDS)

    frame_bytes = 2 * n_channels
    raw = result.stdout[: len(result.stdout) - len(result.stdout) % frame_bytes]
    if not raw:
        raise AudioFormatError("В файле нет звука.")

    pcm = np.frombuffer(raw, dtype="<i2").reshape(-1, n_channels).T
    if pcm.shape[1] > max_seconds * SAMPLE_RATE:
        raise AudioTooLongError(f"Запись длиннее допустимых {max_seconds} секунд.")
    return np.ascontiguousarray(pcm)


def model_dir(models_dir: str, model: str) -> Path:
    """Каталог с весами модели распознавания внутри MODELS_DIR."""
    return Path(models_dir) / model


def vad_dir(models_dir: str) -> Path:
    """Каталог с весами silero VAD внутри MODELS_DIR."""
    return Path(models_dir) / "silero-vad"


# Модель принимает записи до 20–30 секунд, поэтому VAD режет речь на куски не длиннее
VAD_MAX_SPEECH_SECONDS = 20.0


def _load_default_model() -> Any:
    """
    Загружает GigaAM и silero VAD из локальных каталогов MODELS_DIR.

    Если каталога нет, onnx-asr попытался бы скачать веса из интернета, поэтому
    наличие каталогов проверяется заранее: рантайм работает только офлайн.
    """
    asr_path = model_dir(settings.MODELS_DIR, settings.TRANSCRIPTION_MODEL)
    vad_path = vad_dir(settings.MODELS_DIR)
    if not asr_path.is_dir() or not vad_path.is_dir():
        logger.error(f"Нет весов модели: {asr_path} или {vad_path}")
        raise ModelUnavailableError("Модель распознавания недоступна.")

    # Тяжёлые зависимости импортируются лениво: они нужны только для распознавания
    import onnx_asr
    import onnxruntime

    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = settings.TRANSCRIPTION_THREADS

    model = onnx_asr.load_model(
        settings.TRANSCRIPTION_MODEL,
        asr_path,
        quantization=settings.TRANSCRIPTION_QUANTIZATION or None,
        sess_options=options,
    )
    vad = onnx_asr.load_vad("silero", vad_path, sess_options=options)
    return model.with_vad(vad, max_speech_duration_s=VAD_MAX_SPEECH_SECONDS)


class Transcriber:
    """
    Распознавание речи: ленивая загрузка модели и ограничение параллелизма.

    Модель создаётся один раз при первом распознавании. Число одновременных
    распознаваний ограничено семафором TRANSCRIPTION_MAX_CONCURRENCY.
    """

    def __init__(self, model_factory: Optional[Callable[[], Any]] = None) -> None:
        """model_factory создаёт адаптер onnx-asr с VAD; по умолчанию грузит GigaAM."""
        self._model_factory = model_factory or _load_default_model
        self._model: Any = None
        self._load_lock = threading.Lock()
        self._semaphore = threading.BoundedSemaphore(
            max(1, settings.TRANSCRIPTION_MAX_CONCURRENCY)
        )

    @contextmanager
    def slot(self, wait_seconds: float) -> Iterator[None]:
        """
        Занимает слот распознавания на время блока.

        Raises:
            TranscriberBusyError: слот не освободился за wait_seconds.
        """
        if not self._semaphore.acquire(timeout=wait_seconds):
            raise TranscriberBusyError(
                "Сервис распознавания занят, повторите запрос позже."
            )
        try:
            yield
        finally:
            self._semaphore.release()

    def _get_model(self) -> Any:
        """Возвращает модель, загружая её при первом обращении."""
        if self._model is None:
            with self._load_lock:
                if self._model is None:
                    try:
                        self._model = self._model_factory()
                    except TranscriptionError:
                        raise
                    except Exception as error:
                        logger.exception("Не удалось загрузить модель распознавания")
                        raise ModelUnavailableError(
                            "Модель распознавания недоступна."
                        ) from error
        return self._model

    @staticmethod
    def _check_not_cancelled(cancel_event: threading.Event, deadline: float) -> None:
        """Прерывает обработку, если выставлен флаг отмены или истёк дедлайн."""
        if cancel_event.is_set() or time.monotonic() >= deadline:
            raise TranscriptionCancelled()

    def recognize(
        self, samples: np.ndarray, cancel_event: threading.Event, deadline: float
    ) -> list[RawSegment]:
        """
        Распознаёт один канал: samples — одномерный int16, 16 кГц.

        deadline — абсолютное время в шкале time.monotonic(). Флаг отмены и
        дедлайн проверяются перед обращением к модели и перед каждым сегментом.

        Raises:
            TranscriptionCancelled: отмена или истёк дедлайн.
            ModelUnavailableError: модель не загрузилась.
        """
        self._check_not_cancelled(cancel_event, deadline)
        model = self._get_model()
        waveform = samples.astype(np.float32) / 32768.0

        segments: list[RawSegment] = []
        iterator = iter(model.recognize(waveform, sample_rate=SAMPLE_RATE))
        while True:
            self._check_not_cancelled(cancel_event, deadline)
            try:
                segment = next(iterator)
            except StopIteration:
                break
            segments.append(
                RawSegment(float(segment.start), float(segment.end), str(segment.text))
            )
        return segments


_transcriber: Optional[Transcriber] = None
_transcriber_lock = threading.Lock()


def get_transcriber() -> Transcriber:
    """Синглтон Transcriber для процесса (модель одна на воркер)."""
    global _transcriber
    if _transcriber is None:
        with _transcriber_lock:
            if _transcriber is None:
                _transcriber = Transcriber()
    return _transcriber


@dataclass(frozen=True)
class TranscriptionResult:
    """Итог обработки файла: длительность, исходное число каналов, сегменты."""

    duration: float
    channels: int
    segments: list[Segment]


def transcribe_bytes(
    content: bytes,
    *,
    extension: str,
    channel_labels: list[str],
    cancel_event: threading.Event,
    deadline: float,
    transcriber: Optional[Transcriber] = None,
) -> TranscriptionResult:
    """
    Расшифровывает аудиофайл целиком: зондирование, декодирование, распознавание.

    Слот распознавания занимается до зондирования и декодирования: декодированный
    PCM длинной записи занимает десятки мегабайт, и ожидающие запросы не должны его
    копить. Файл пишется во временный каталог под фиксированным именем
    input.<расширение>, имя от клиента не используется; каталог удаляется всегда.

    Raises:
        TranscriberBusyError: нет свободного слота.
        AudioFormatError, AudioTooLongError: проблемы с файлом.
        ModelUnavailableError: нет модели или ffmpeg.
        TranscriptionCancelled: отмена или истёк дедлайн.
    """
    transcriber = transcriber or get_transcriber()

    with transcriber.slot(settings.TRANSCRIPTION_QUEUE_WAIT_SECONDS):
        with tempfile.TemporaryDirectory(prefix="transcribe_") as directory:
            path = Path(directory) / f"input.{extension}"
            path.write_bytes(content)

            info = probe_audio(path, extension)
            pcm = decode_audio(path, extension, info.channels)

        per_channel = [
            transcriber.recognize(pcm[channel], cancel_event, deadline)
            for channel in range(pcm.shape[0])
        ]

    return TranscriptionResult(
        duration=pcm.shape[1] / SAMPLE_RATE,
        channels=info.channels,
        segments=build_segments(per_channel, channel_labels),
    )
