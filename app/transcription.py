"""Расшифровка речи из аудиофайлов (эндпоинт /v1/transcribe)."""

import asyncio
import json
import logging
import subprocess
import tempfile
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
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


class TranscriptionSlot:
    """Слот от приёма запроса до фактического завершения рабочего потока."""

    def __init__(self, semaphore: threading.BoundedSemaphore) -> None:
        """Принимает уже занятый семафор обработки."""
        self._semaphore = semaphore
        self._lock = threading.Lock()
        self._transferred = False
        self._released = False

    def transfer(self) -> None:
        """Передаёт ответственность за освобождение рабочему заданию."""
        with self._lock:
            self._transferred = True

    def release(self, *, unless_transferred: bool = False) -> None:
        """Освобождает слот ровно один раз, в том числе после отмены HTTP-запроса."""
        with self._lock:
            if self._released or (unless_transferred and self._transferred):
                return
            self._released = True
            self._semaphore.release()

    def __enter__(self) -> None:
        """Слот уже занят до чтения тела запроса."""

    def __exit__(self, *args: Any) -> None:
        """Возвращает слот после обработки, включая ошибки и отмену."""
        self.release()


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
    оба поля остаются None. Нераспознанные речевые сегменты сохраняют тайм-коды.
    """
    is_stereo = len(per_channel) == 2
    segments: list[Segment] = []

    for channel_index, raw_segments in enumerate(per_channel):
        for raw in raw_segments:
            text = raw.text.strip()
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
    texts = [segment.text for segment in segments if segment.text]
    if not segments:
        text_status = "no_speech"
    elif not texts:
        text_status = "unrecognized"
    elif len(texts) < len(segments):
        text_status = "partial"
    else:
        text_status = "ok"
    return {
        "status": "success",
        "filename": filename,
        "external_id": external_id,
        "duration": round(duration, 1),
        "channels": channels,
        "model": settings.TRANSCRIPTION_MODEL,
        "language": "ru",
        "text_status": text_status,
        "text": " ".join(texts),
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


def _run_media_tool(
    command: list, timeout: float, deadline: Optional[float] = None
) -> subprocess.CompletedProcess:
    """
    Запускает ffprobe/ffmpeg с ограничениями ресурсов.

    Отсутствие бинарника — проблема сервиса (503), а таймаут, лимит памяти
    и ненулевой код — проблема файла (422).
    """
    if deadline is not None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TranscriptionCancelled()
        timeout = min(timeout, remaining)
    try:
        result = run_subprocess_with_limits(command, timeout=timeout, text=False)
    except FileNotFoundError as error:
        logger.error(f"Не найден {command[0]}: {error}")
        raise ModelUnavailableError("Сервис обработки аудио недоступен.") from error
    except (subprocess.TimeoutExpired, MemoryError) as error:
        if deadline is not None and time.monotonic() >= deadline:
            raise TranscriptionCancelled() from error
        logger.error(f"{command[0]} прерван ({type(error).__name__})")
        raise AudioFormatError("Не удалось обработать аудиофайл.") from error

    if result.returncode != 0:
        stderr = (result.stderr or b"").decode("utf-8", errors="replace")[:500]
        logger.warning(f"{command[0]} завершился с кодом {result.returncode}: {stderr}")
        raise AudioFormatError("Файл повреждён или не является аудиозаписью.")
    return result


def probe_audio(
    path: Path, extension: str, *, deadline: Optional[float] = None
) -> AudioInfo:
    """
    Определяет число каналов и длительность первой аудиодорожки через ffprobe.

    Длительность из метаданных — лишь подсказка: она может быть неизвестна (None)
    или оценена по битрейту (сырой AAC/AMR, mp3 без заголовка Xing) и сильно
    завышена, например при тишине в начале записи. Поэтому лимит длительности
    здесь не применяется: его проверяет decode_audio по реально декодированному звуку.

    Raises:
        AudioFormatError: нет аудиодорожки или файл не читается.
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
    result = _run_media_tool(command, PROBE_TIMEOUT_SECONDS, deadline)

    try:
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        channels = int(stream["channels"])
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise AudioFormatError("В файле не найдена аудиодорожка.") from error

    duration: Optional[float] = None
    raw_duration = (data.get("format") or {}).get("duration")
    if raw_duration is not None:
        try:
            parsed = float(raw_duration)
        except (TypeError, ValueError):
            parsed = 0.0
        if parsed > 0:
            duration = parsed

    return AudioInfo(duration=duration, channels=channels)


def decode_audio(
    path: Path,
    extension: str,
    channels: int,
    *,
    deadline: Optional[float] = None,
) -> np.ndarray:
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
    result = _run_media_tool(command, DECODE_TIMEOUT_SECONDS, deadline)

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

# Короче 0.1 с речи не бывает, а silero падает на входе короче ~36 мс
# (ValueError/IndexError), что превратилось бы в ответ 500 на оборванной записи.
MIN_RECOGNIZABLE_SAMPLES = SAMPLE_RATE // 10


class SpeechRecognitionModel:
    """Основная модель с VAD и резервная CTC для пустых речевых сегментов."""

    def __init__(self, primary: Any, fallback: Any) -> None:
        """Объединяет основную модель с VAD и резервную модель без VAD."""
        self._primary = primary
        self._fallback = fallback

    def recognize(
        self, waveform: np.ndarray, *, sample_rate: int
    ) -> Iterator[RawSegment]:
        """Повторяет только нераспознанные фрагменты, сохраняя время и канал."""
        for segment in self._primary.recognize(waveform, sample_rate=sample_rate):
            text = segment.text.strip()
            if not text:
                start = max(0, round(segment.start * sample_rate))
                end = min(len(waveform), round(segment.end * sample_rate))
                if end - start >= MIN_RECOGNIZABLE_SAMPLES:
                    text = self._fallback.recognize(
                        waveform[start:end], sample_rate=sample_rate
                    ).strip()
            yield RawSegment(float(segment.start), float(segment.end), text)


def _load_default_model() -> Any:
    """
    Загружает GigaAM и silero VAD из локальных каталогов MODELS_DIR.

    Если каталога нет, onnx-asr попытался бы скачать веса из интернета, поэтому
    наличие каталогов проверяется заранее: рантайм работает только офлайн.
    """
    asr_path = model_dir(settings.MODELS_DIR, settings.TRANSCRIPTION_MODEL)
    fallback_path = model_dir(
        settings.MODELS_DIR, settings.TRANSCRIPTION_FALLBACK_MODEL
    )
    vad_path = vad_dir(settings.MODELS_DIR)
    if not all(path.is_dir() for path in (asr_path, fallback_path, vad_path)):
        logger.error(f"Нет весов модели: {asr_path}, {fallback_path} или {vad_path}")
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
    primary = model.with_vad(
        vad,
        max_speech_duration_s=VAD_MAX_SPEECH_SECONDS,
        min_silence_duration_ms=settings.TRANSCRIPTION_VAD_MIN_SILENCE_MS,
        speech_pad_ms=settings.TRANSCRIPTION_VAD_SPEECH_PAD_MS,
    )
    fallback = onnx_asr.load_model(
        settings.TRANSCRIPTION_FALLBACK_MODEL,
        fallback_path,
        quantization="int8",
        sess_options=options,
    )
    return SpeechRecognitionModel(primary, fallback)


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
        self._load_failed = False
        self._load_lock = threading.Lock()
        self._semaphore = threading.BoundedSemaphore(
            max(1, settings.TRANSCRIPTION_MAX_CONCURRENCY)
        )
        self._admission_lock = threading.Lock()
        self._waiting = 0
        self._executor_lock = threading.Lock()
        self._executor: Optional[ThreadPoolExecutor] = None

    async def reserve(self) -> TranscriptionSlot:
        """Ожидает слот без рабочего потока, ограничивая число ожидающих запросов."""
        if self._semaphore.acquire(blocking=False):
            return TranscriptionSlot(self._semaphore)
        with self._admission_lock:
            if self._waiting >= settings.TRANSCRIPTION_MAX_QUEUE_SIZE:
                raise TranscriberBusyError("Очередь распознавания заполнена.")
            self._waiting += 1
        deadline = time.monotonic() + settings.TRANSCRIPTION_QUEUE_WAIT_SECONDS
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TranscriberBusyError(
                        "Сервис распознавания занят, повторите запрос позже."
                    )
                if self._semaphore.acquire(blocking=False):
                    return TranscriptionSlot(self._semaphore)
                await asyncio.sleep(min(0.01, remaining))
        finally:
            with self._admission_lock:
                self._waiting -= 1

    def submit(
        self, slot: TranscriptionSlot, function: Callable, *args: Any, **kwargs: Any
    ) -> Future:
        """Запускает принятое задание в отдельном ограниченном пуле аудио."""
        slot.transfer()
        try:
            with self._executor_lock:
                if self._executor is None:
                    self._executor = ThreadPoolExecutor(
                        max_workers=max(1, settings.TRANSCRIPTION_MAX_CONCURRENCY),
                        thread_name_prefix="transcription",
                    )
                future = self._executor.submit(
                    function, *args, slot=slot, transcriber=self, **kwargs
                )
        except BaseException:
            slot.release()
            raise
        future.add_done_callback(lambda _: slot.release())
        return future

    def close(self) -> None:
        """Дожидается завершения заданий при остановке сервиса."""
        with self._executor_lock:
            executor, self._executor = self._executor, None
        if executor is not None:
            executor.shutdown(wait=True)

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

    @property
    def status(self) -> str:
        """Готовность модели: ready, unavailable (загрузка не удалась) или not_loaded."""
        if self._model is not None:
            return "ready"
        return "unavailable" if self._load_failed else "not_loaded"

    def warm_up(self) -> None:
        """
        Загружает модель заранее (при старте сервиса), не дожидаясь первого запроса.

        Raises:
            ModelUnavailableError: модель не загрузилась.
        """
        self._get_model()

    def _get_model(self) -> Any:
        """Возвращает модель, загружая её при первом обращении."""
        if self._model is None:
            with self._load_lock:
                if self._model is None:
                    try:
                        self._model = self._model_factory()
                        self._load_failed = False
                    except TranscriptionError:
                        self._load_failed = True
                        raise
                    except Exception as error:
                        self._load_failed = True
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

        deadline — абсолютное время в шкале time.monotonic(). Флаг отмены и дедлайн
        проверяются перед обращением к модели и перед получением каждого сегмента;
        onnx-asr распознаёт сегменты пакетами (по умолчанию до 8), поэтому остановка
        может занять время обработки одного пакета.

        Raises:
            TranscriptionCancelled: отмена или истёк дедлайн.
            ModelUnavailableError: модель не загрузилась.
        """
        self._check_not_cancelled(cancel_event, deadline)
        if samples.shape[0] < MIN_RECOGNIZABLE_SAMPLES:
            return []
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
    """Синглтон Transcriber: один комплект моделей и пул аудио на процесс."""
    global _transcriber
    if _transcriber is None:
        with _transcriber_lock:
            if _transcriber is None:
                _transcriber = Transcriber()
    return _transcriber


# Каналы считаются одинаковыми, если отсчёты различаются не больше, чем на шум
# квантования (допуск для моно, сохранённого как стерео после lossy-кодека)
IDENTICAL_CHANNELS_MAX_DIFF = 8
_COMPARE_CHUNK_SAMPLES = 1_000_000


def _channels_identical(left: np.ndarray, right: np.ndarray) -> bool:
    """Совпадают ли каналы (моно, записанное как стерео); блоками, чтобы не копить int32."""
    for start in range(0, left.shape[0], _COMPARE_CHUNK_SAMPLES):
        end = start + _COMPARE_CHUNK_SAMPLES
        difference = np.abs(
            left[start:end].astype(np.int32) - right[start:end].astype(np.int32)
        )
        if difference.max() > IDENTICAL_CHANNELS_MAX_DIFF:
            return False
    return True


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
    slot: Optional[TranscriptionSlot] = None,
) -> TranscriptionResult:
    """
    Расшифровывает аудиофайл целиком: зондирование, декодирование, распознавание.

    Слот распознавания занимается до зондирования и декодирования: декодированный
    PCM длинной записи занимает десятки мегабайт, и ожидающие запросы не должны его
    копить. Файл пишется во временный каталог под фиксированным именем
    input.<расширение>, имя от клиента не используется; каталог удаляется всегда.
    Стерео с совпадающими каналами распознаётся как моно (speaker=None).

    Raises:
        TranscriberBusyError: нет свободного слота.
        AudioFormatError, AudioTooLongError: проблемы с файлом.
        ModelUnavailableError: нет модели или ffmpeg.
        TranscriptionCancelled: отмена или истёк дедлайн.
    """
    transcriber = transcriber or get_transcriber()

    transcriber._check_not_cancelled(cancel_event, deadline)
    with slot or transcriber.slot(settings.TRANSCRIPTION_QUEUE_WAIT_SECONDS):
        transcriber._check_not_cancelled(cancel_event, deadline)
        with tempfile.TemporaryDirectory(prefix="transcribe_") as directory:
            path = Path(directory) / f"input.{extension}"
            path.write_bytes(content)

            transcriber._check_not_cancelled(cancel_event, deadline)
            info = probe_audio(path, extension, deadline=deadline)
            transcriber._check_not_cancelled(cancel_event, deadline)
            pcm = decode_audio(path, extension, info.channels, deadline=deadline)
            transcriber._check_not_cancelled(cancel_event, deadline)

        if pcm.shape[0] == 2 and _channels_identical(pcm[0], pcm[1]):
            # Моно, сохранённое как стерео: иначе каждая реплика пришла бы дважды
            # с двумя разными говорящими, а расчёт удвоился бы.
            logger.info("Каналы стерео-записи совпадают, распознаём как моно")
            pcm = pcm[:1]

        per_channel = [
            transcriber.recognize(pcm[channel], cancel_event, deadline)
            for channel in range(pcm.shape[0])
        ]

    return TranscriptionResult(
        duration=pcm.shape[1] / SAMPLE_RATE,
        channels=info.channels,
        segments=build_segments(per_channel, channel_labels),
    )
