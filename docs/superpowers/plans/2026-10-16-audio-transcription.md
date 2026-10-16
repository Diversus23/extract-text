# Расшифровка аудио (`/v1/transcribe`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Образ extract-text принимает аудиофайл по `POST /v1/transcribe` и возвращает расшифровку с тайм-кодами сегментов и меткой говорящего по каналам стерео.

**Architecture:** Новый модуль `app/transcription.py` (ffprobe/ffmpeg → PCM 16 кГц → onnx-asr GigaAM v3 + silero VAD по каждому каналу → слияние сегментов). Эндпоинт в `app/main.py` оборачивает синхронный вызов в `run_in_threadpool` + `asyncio.wait_for` с отдельным таймаутом и флагом отмены. Веса запечены в образ; второй compose-сервис `api-audio` из того же образа работает с `WORKERS=1`.

**Tech Stack:** Python 3.12, FastAPI, onnx-asr (onnxruntime, numpy), ffmpeg/ffprobe, python-magic, pytest.

**Spec:** [docs/superpowers/specs/2026-10-16-audio-transcription-design.md](../specs/2026-10-16-audio-transcription-design.md) — читать вместе с планом; контракт ответа и таблица ошибок берутся оттуда дословно.

## Global Constraints

- Python 3.12+, Black 88, isort профиль `black`, Flake8 `max-complexity=20`; перед каждым коммитом `make format && make lint-check`.
- Комментарии, логи, тексты ошибок и сообщения коммитов — на русском; коммиты по Conventional Commits; каждое сообщение коммита заканчивается строкой `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Ошибки эндпоинта — `JSONResponse` со структурой `{status:"error", filename, message}`, не `HTTPException`. Внутренние детали (stderr ffmpeg, трейсы) только в логи.
- Экстракторы остаются синхронными, без `asyncio.run`; тяжёлая работа только в threadpool.
- Аудио-расширения живут в `settings.AUDIO_FORMATS`, не в `SUPPORTED_FORMATS`; `/v1/supported-formats` и `/v1/extract/*` не меняются (аудио на них по-прежнему 415).
- Значения: модель `gigaam-v3-e2e-rnnt`, язык ответа `"ru"`, `MAX_FILE_SIZE` 20 МБ, `MAX_AUDIO_DURATION_SECONDS=1800`, `TRANSCRIPTION_TIMEOUT_SECONDS=900`, `TRANSCRIPTION_MAX_CONCURRENCY=1`, `TRANSCRIPTION_QUEUE_WAIT_SECONDS=30`, `external_id` до 128 символов, форматы `mp3, wav, ogg, opus, flac, m4a, aac, wma, amr`.
- Порог покрытия в `pytest.ini` (`--cov-fail-under=55`) не снижать. Для запуска отдельных тестов добавлять `--no-cov`; если локально нет libmagic или ffmpeg, выполнять ту же команду в контейнере (`make debug`).
- Уточнения к спецификации: (а) временный каталог создаётся и удаляется внутри рабочего потока (`tempfile.TemporaryDirectory`), а не общими helper'ами `utils.py`, чтобы после 504 поток не потерял файлы; (б) добавляется настройка `TRANSCRIPTION_QUANTIZATION` (пусто = fp32, `int8`), рантайм должен знать, какие файлы грузить.

## Review Focus

Входы, о которых спецификация молчит, а тесты задач иначе не покрыли бы (каждый закреплён тестом в указанной задаче):

1. Длительность неизвестна (`ffprobe` отдаёт `N/A`, сырой `.aac`/`.amr`): лимит обязан сработать после декодирования, а не пропуститься — Task 3.
2. Стерео, где один канал полностью тишина (односторонняя запись, mute): ответ валиден, сегменты только другого канала, без падения — Task 5.
3. Очень короткий или целиком беззвучный файл: HTTP 200 и `no_speech`, не ошибка — Task 5.
4. Странные `channel_labels` (`" client , ,operator"`, кириллица, больше или меньше меток, чем каналов) и `external_id` с юникодом/длиной 129 — Task 2 и Task 6.
5. Контейнер с видео и аудио (mp4/m4a) и дорожки 3+ каналов (5.1): берётся первая аудиодорожка; без аудио — 422; 3+ канала сводятся в моно с `speaker=null` — Task 3.

---

### Task 1: Настройки, зависимость, env_example

**Files:**
- Modify: `app/config.py` (класс `Settings`, рядом с остальными настройками обработки файлов), `requirements.txt`, `env_example`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: атрибуты `Settings.AUDIO_FORMATS: List[str]`, `ENABLE_TRANSCRIPTION: bool`, `TRANSCRIPTION_MODEL: str`, `TRANSCRIPTION_QUANTIZATION: str`, `MODELS_DIR: str`, `MAX_AUDIO_DURATION_SECONDS: int`, `TRANSCRIPTION_TIMEOUT_SECONDS: int`, `TRANSCRIPTION_MAX_CONCURRENCY: int`, `TRANSCRIPTION_QUEUE_WAIT_SECONDS: int`, `TRANSCRIPTION_THREADS: int` (по умолчанию `os.cpu_count() or 1`). Значения по умолчанию — из Global Constraints; `MODELS_DIR` = `/opt/models`.

- [ ] **Step 1: Failing-тесты** в `tests/test_config.py` по образцу `test_default_settings` (reload `app.config` с очищенным окружением): `test_transcription_defaults` проверяет все значения выше (`TRANSCRIPTION_QUANTIZATION == ""`, `ENABLE_TRANSCRIPTION is True`); `test_transcription_env_overrides` ставит `MAX_AUDIO_DURATION_SECONDS=60`, `ENABLE_TRANSCRIPTION=false`, `TRANSCRIPTION_MAX_CONCURRENCY=2` и ждёт их в `Settings()`; `test_audio_formats_not_in_supported_formats`: `set(AUDIO_FORMATS).isdisjoint(set(sum(Settings.SUPPORTED_FORMATS.values(), [])))` — если пересечение найдётся, остановиться и сообщить.
- [ ] **Step 2: Запустить** `python -m pytest tests/test_config.py -v --no-cov` — ожидается FAIL (`AttributeError`).
- [ ] **Step 3: Реализовать** атрибуты в `Settings` в стиле соседних (`int(os.getenv(...))`, bool через `.lower() == "true"`). В `requirements.txt` добавить `onnx-asr[cpu,hub]==<текущая версия>` (на момент планирования на PyPI значилась 0.11.0; взять актуальную и убедиться, что она знает имя `gigaam-v3-e2e-rnnt`). В `env_example` добавить блок «Транскрибация» со всеми переменными и комментариями.
- [ ] **Step 4: Запустить** тот же тест — PASS; `pip install -r requirements.txt` в контейнере проходит.
- [ ] **Step 5: Commit** — `feat: настройки и зависимость для транскрибации аудио`.

### Task 2: Сборка результата (чистая логика)

**Files:**
- Create: `app/transcription.py` (начало модуля)
- Test: `tests/test_transcription.py`

**Interfaces:**
- Produces (все в `app/transcription.py`):
  - `@dataclass(frozen=True) class RawSegment: start: float; end: float; text: str`
  - `@dataclass(frozen=True) class Segment: start: float; end: float; speaker: Optional[str]; channel: Optional[int]; text: str`
  - `class TranscriptionError(Exception)` с `__init__(self, message: str, status_code: int, retry_after: Optional[int] = None)`; подклассы с фиксированным кодом: `AudioFormatError` (422), `AudioTooLongError` (413), `ModelUnavailableError` (503), `TranscriberBusyError` (503, `retry_after=30`). Отдельный `class TranscriptionCancelled(Exception)` (не наследник `TranscriptionError`).
  - `parse_channel_labels(raw: Optional[str]) -> list[str]` — split по запятой, `strip()`, пустые остаются пустыми строками; `None` → `[]`.
  - `speaker_label(labels: list[str], channel: int) -> str` — `labels[channel]`, если индекс есть и метка непустая, иначе `f"channel_{channel}"`.
  - `build_segments(per_channel: list[list[RawSegment]], labels: list[str]) -> list[Segment]` — при `len(per_channel) == 2` заполняет `channel`/`speaker`, при 1 — `None`/`None`; пустой после `strip()` текст отбрасывается; сортировка по `(start, channel)`.
  - `build_response(*, filename: str, external_id: Optional[str], duration: float, channels: int, segments: list[Segment]) -> dict` — ровно поля из раздела 2 спецификации; `text` = тексты сегментов через пробел; `text_status` = `"ok"` или `"no_speech"`; `model` берётся из `settings.TRANSCRIPTION_MODEL`; `duration` округляется до 0.1, `start`/`end` до 0.01.

- [ ] **Step 1: Failing-тесты** (`@pytest.mark.unit`):
  - `test_build_segments_stereo_sorted_and_labeled`: каналы `[[RawSegment(3.4,5.85,"Здравствуйте")], [RawSegment(0.52,3.1,"Добрый день")]]`, метки `["client","operator"]` → порядок `["Добрый день","Здравствуйте"]`, спикеры `["operator","client"]`, каналы `[1,0]`.
  - `test_build_segments_mono_has_null_speaker`: один канал → `speaker is None and channel is None`.
  - `test_build_segments_drops_blank_text`: сегмент с `"  "` исчезает.
  - `test_speaker_label_fallbacks`: `parse_channel_labels(" client , ,operator")` → `["client","","operator"]`; `speaker_label(..., 1) == "channel_1"`; индекс за пределами списка → `channel_N`; `parse_channel_labels(None) == []`; кириллические метки возвращаются как есть.
  - `test_build_response_no_speech`: пустые сегменты → `text == ""`, `text_status == "no_speech"`, `segments == []`, `language == "ru"`.
  - `test_build_response_ok_text_joined`: два сегмента → `text == "Добрый день Здравствуйте"`.
  - `test_error_status_codes`: `AudioFormatError("x").status_code == 422`, `AudioTooLongError` 413, `ModelUnavailableError` 503, `TranscriberBusyError.retry_after == 30`.
- [ ] **Step 2: Запустить** `python -m pytest tests/test_transcription.py -v --no-cov` — FAIL (нет модуля).
- [ ] **Step 3: Реализовать** перечисленное, с docstring'ами на русском.
- [ ] **Step 4: Запустить** — PASS.
- [ ] **Step 5: Commit** — `feat: сборка результата транскрибации и типы ошибок`.

### Task 3: Зондирование и декодирование аудио (ffprobe/ffmpeg)

**Files:**
- Modify: `app/transcription.py`
- Test: `tests/test_transcription.py`

**Interfaces:**
- Consumes: `AudioFormatError`, `AudioTooLongError`; `run_subprocess_with_limits` из `app/utils.py` (вызывать с `text=False`; код возврата проверять самим, исключений при ненулевом коде он не бросает).
- Produces:
  - `FFMPEG_DEMUXERS: dict[str, str]` — `mp3→mp3, wav→wav, ogg→ogg, opus→ogg, flac→flac, m4a→mov, aac→aac, wma→asf, amr→amr`.
  - `@dataclass(frozen=True) class AudioInfo: duration: Optional[float]; channels: int`
  - `probe_audio(path: Path, extension: str) -> AudioInfo` — `ffprobe -v error -protocol_whitelist file -f <demuxer> -select_streams a:0 -show_entries stream=channels:format=duration -of json <path>`, таймаут 30 с; нет аудиодорожки или ошибка → `AudioFormatError`; `duration` `N/A`/отсутствует → `None`; `duration > MAX_AUDIO_DURATION_SECONDS` → `AudioTooLongError`.
  - `decode_audio(path: Path, extension: str, channels: int) -> np.ndarray` — int16, форма `(n_channels, n_samples)`, `n_channels = 2` только при `channels == 2`, иначе моно-микс (`-ac 1`); команда `ffmpeg -nostdin -v error -protocol_whitelist file -f <demuxer> -i <path> -map 0:a:0 -vn -ac N -ar 16000 -t <MAX+1> -f s16le -`, таймаут 120 с; ненулевой код, таймаут, `MemoryError` или пустой вывод → `AudioFormatError`; `n_samples > MAX_AUDIO_DURATION_SECONDS * 16000` → `AudioTooLongError`.

- [ ] **Step 1: Failing-тесты:**
  - С подменой `app.transcription.run_subprocess_with_limits` (`unit`): `test_probe_command_is_hardened` — в команде есть `-protocol_whitelist file`, `-f mov` для `m4a`, `-select_streams a:0`; `test_probe_unknown_duration_is_none` (ответ `{"streams":[{"channels":1}],"format":{"duration":"N/A"}}` → `AudioInfo(None, 1)`); `test_probe_no_audio_stream_raises` (`{"streams":[]}` → `AudioFormatError`); `test_probe_too_long_raises` (`duration "1801.0"` → `AudioTooLongError`); `test_decode_command_caps_duration` (в аргументах `-t` равен `str(MAX+1)`, есть `-nostdin`); `test_decode_over_limit_raises` (вывод длиннее `MAX*16000` отсчётов → `AudioTooLongError`, закрепляет Review Focus №1); `test_decode_multichannel_downmixed_to_mono` (`channels=6` → в команде `-ac 1`, форма `(1, n)`); `test_decode_failure_raises` (returncode 1 → `AudioFormatError`).
  - С настоящим ffmpeg (`skipif shutil.which("ffmpeg") is None`, фикстура `synth_audio(tmp_path, ext, channels, seconds)` строит файл через `ffmpeg -f lavfi -i sine=frequency=440:duration=N`): `test_real_roundtrip_stereo_wav` — `probe_audio` даёт `channels == 2`, `decode_audio` даёт форму `(2, ~16000*seconds)`; `test_real_mp4_with_video_and_audio` — mp4 с видео-дорожкой и аудио декодируется как первая аудиодорожка, mp4 без аудио → `AudioFormatError` (Review Focus №5).
- [ ] **Step 2: Запустить** `python -m pytest tests/test_transcription.py -k "probe or decode or real" -v --no-cov` — FAIL.
- [ ] **Step 3: Реализовать** функции; `ffprobe` и `ffmpeg` вызываются списком аргументов, без shell; ошибки логировать с stderr (в ответ клиенту stderr не попадает).
- [ ] **Step 4: Запустить** — PASS (реальные тесты в контейнере).
- [ ] **Step 5: Commit** — `feat: зондирование и декодирование аудио через ffmpeg`.

### Task 4: Transcriber (модель, VAD, отмена, слот)

**Files:**
- Modify: `app/transcription.py`
- Test: `tests/test_transcription.py`

**Interfaces:**
- Consumes: `RawSegment`, `ModelUnavailableError`, `TranscriberBusyError`, `TranscriptionCancelled`.
- Produces:
  - `model_dir(models_dir: str, model: str) -> Path` (= `Path(models_dir) / model`), `vad_dir(models_dir: str) -> Path` (= `Path(models_dir) / "silero-vad"`).
  - `class Transcriber`: `__init__(self, model_factory: Optional[Callable[[], Any]] = None)`; `slot(self, wait_seconds: float) -> ContextManager[None]` (семафор на `TRANSCRIPTION_MAX_CONCURRENCY`; не получен за `wait_seconds` → `TranscriberBusyError`); `recognize(self, samples: np.ndarray, cancel_event: threading.Event, deadline: float) -> list[RawSegment]` — `samples` int16 одномерный; `deadline` — абсолютное `time.monotonic()`.
  - `get_transcriber() -> Transcriber` — синглтон процесса.
  - Модель по умолчанию создаётся лениво один раз под `threading.Lock`: `onnx_asr.load_model(settings.TRANSCRIPTION_MODEL, path=model_dir(...), quantization=settings.TRANSCRIPTION_QUANTIZATION or None, sess_options=<SessionOptions c intra_op_num_threads=settings.TRANSCRIPTION_THREADS>).with_vad(onnx_asr.load_vad("silero", path=vad_dir(...)), max_speech_duration_s=20.0)`. Любая ошибка загрузки → `ModelUnavailableError("Модель распознавания недоступна.", 503)`.

- [ ] **Step 1: Failing-тесты** с фабрикой-заглушкой, возвращающей объект с `recognize(wave, sample_rate=16000)`, который отдаёт итератор `SimpleNamespace(start, end, text)`: `test_recognize_converts_int16_to_float32` (заглушка получает `float32` в диапазоне [-1, 1] и `sample_rate=16000`); `test_recognize_maps_segments` (результат — `RawSegment`); `test_recognize_stops_on_cancel_event` (событие выставляется после первого сегмента → `TranscriptionCancelled`, третий сегмент не запрашивался); `test_recognize_stops_on_deadline` (прошедший `deadline` → `TranscriptionCancelled`); `test_model_loaded_once` (две подряд `recognize` вызывают фабрику один раз); `test_factory_failure_is_model_unavailable`; `test_slot_busy_raises` (при `TRANSCRIPTION_MAX_CONCURRENCY=1` второй `slot(0.05)` во время первого → `TranscriberBusyError`; после выхода из первого слот снова доступен — закрепляет освобождение в `finally`).
- [ ] **Step 2: Запустить** `python -m pytest tests/test_transcription.py -k "recognize or slot or model" -v --no-cov` — FAIL.
- [ ] **Step 3: Реализовать.** Флаг отмены и дедлайн проверять перед получением каждого следующего сегмента итератора. Одномерный float32-массив передаётся в `recognize` как есть; сверить ожидания формы с Reference onnx-asr при реализации.
- [ ] **Step 4: Запустить** — PASS.
- [ ] **Step 5: Commit** — `feat: Transcriber с ленивой загрузкой модели, VAD и отменой`.

### Task 5: Оркестрация `transcribe_bytes`

**Files:**
- Modify: `app/transcription.py`
- Test: `tests/test_transcription.py`

**Interfaces:**
- Consumes: всё из Task 2–4.
- Produces: `@dataclass(frozen=True) class TranscriptionResult: duration: float; channels: int; segments: list[Segment]` и `transcribe_bytes(content: bytes, *, extension: str, channel_labels: list[str], cancel_event: threading.Event, deadline: float, transcriber: Optional[Transcriber] = None) -> TranscriptionResult`. Внутри: `tempfile.TemporaryDirectory(prefix="transcribe_")`, файл `input.<extension>` (имя от клиента не используется), `probe_audio` → `decode_audio` → `with transcriber.slot(settings.TRANSCRIPTION_QUEUE_WAIT_SECONDS)` → `recognize` по каждому каналу → `build_segments`. `duration` считается по декодированным отсчётам (`n_samples / 16000`), `channels` — число каналов исходного файла из `probe_audio`. Каталог удаляется в `finally`.

- [ ] **Step 1: Failing-тесты** (probe/decode/transcriber подменены):
  - `test_stereo_result_has_labeled_segments`: два канала, метки `["client","operator"]` → сегменты обоих каналов в хронологическом порядке, `channels == 2`.
  - `test_one_silent_channel` (Review Focus №2): `recognize` для канала 0 возвращает `[]`, для канала 1 — сегменты → результат содержит только сегменты канала 1, без исключений.
  - `test_total_silence_gives_empty_segments` (Review Focus №3): оба канала `[]`, и для одного семпла (`n_samples=1`) тоже → `segments == []`, исключения нет.
  - `test_temp_dir_removed_on_error`: после `AudioFormatError` каталог `transcribe_*` в `tempfile.gettempdir()` отсутствует.
  - `test_slot_released_on_cancel`: после `TranscriptionCancelled` слот доступен снова.
  - `test_mono_has_null_speaker`: один канал → `speaker is None`.
- [ ] **Step 2: Запустить** `python -m pytest tests/test_transcription.py -k "stereo or silent or silence or temp_dir or slot_released or mono" -v --no-cov` — FAIL.
- [ ] **Step 3: Реализовать** `transcribe_bytes`.
- [ ] **Step 4: Запустить** весь `tests/test_transcription.py` — PASS.
- [ ] **Step 5: Commit** — `feat: оркестрация транскрибации аудио`.

### Task 6: Эндпоинт `/v1/transcribe` и проверка MIME аудио

**Files:**
- Modify: `app/main.py` (импорт `Form`; эндпоинт на `v1_router` рядом с `/extract/file`), `app/utils.py` (`extension_to_mime` в `validate_file_type`)
- Test: `tests/test_transcribe_endpoint.py`, `tests/test_utils.py`

**Interfaces:**
- Consumes: `transcribe_bytes`, `build_response`, `parse_channel_labels`, `TranscriptionError`, `TranscriptionCancelled`, `validate_file_type`, `get_file_extension`, `sanitize_filename`.
- Produces: `async def transcribe(file: UploadFile = FILE_UPLOAD, channel_labels: Optional[str] = Form(None), external_id: Optional[str] = Form(None))` на `POST /v1/transcribe`. Порядок проверок и коды — раздел 6 спецификации; все ответы `JSONResponse`; при `TranscriberBusyError` заголовок `Retry-After: 30`. Таймаут: `asyncio.wait_for(run_in_threadpool(transcribe_bytes, ...), TRANSCRIPTION_TIMEOUT_SECONDS)`; при `asyncio.TimeoutError` выставить `cancel_event` и вернуть 504; `TranscriptionCancelled` из рабочего потока (дедлайн сработал чуть раньше `wait_for`) тоже даёт 504. `deadline = time.monotonic() + TRANSCRIPTION_TIMEOUT_SECONDS`. Расширение вне `AUDIO_FORMATS` → 415 с перечнем допустимых.
- В `validate_file_type` добавить MIME для аудио: `mp3: audio/mpeg`; `wav: audio/x-wav, audio/wav, audio/vnd.wave`; `ogg, opus: audio/ogg, application/ogg, audio/opus`; `flac: audio/flac, audio/x-flac`; `m4a: audio/x-m4a, audio/mp4, video/mp4`; `aac: audio/aac, audio/x-hx-aac-adts`; `wma: video/x-ms-asf, audio/x-ms-wma`; `amr: audio/amr`. Уточнить по фактическому выводу `magic` в образе (см. Step 1).

- [ ] **Step 1: Failing-тесты.**
  - `tests/test_utils.py`: `test_validate_audio_formats_with_real_ffmpeg` — для каждого формата из `AUDIO_FORMATS` синтезировать файл через ffmpeg (пропускать формат, если энкодера нет) и проверить `validate_file_type(...)[0] is True`; `test_validate_audio_ext_mismatch` — текстовый файл с именем `x.mp3` → `False`.
  - `tests/test_transcribe_endpoint.py` (`integration`, `Transcriber`/`transcribe_bytes` подменяются через `patch("app.main.transcribe_bytes")`): `test_200_contract` (поля и значения из раздела 2, `filename` и `external_id` возвращены без изменений, в том числе кириллическое имя); `test_no_speech_is_200`; `test_missing_content_length_400` (по образцу такого же теста для `/extract/file` в `tests/test_main.py`); `test_empty_file_422`; `test_unsupported_extension_415`; `test_mime_mismatch_415`; `test_too_long_413` (подмена бросает `AudioTooLongError`); `test_audio_format_error_422`; `test_busy_503_has_retry_after`; `test_model_unavailable_503`; `test_disabled_503` (`ENABLE_TRANSCRIPTION=false`); `test_timeout_504_sets_cancel_event` (подмена блокируется, `TRANSCRIPTION_TIMEOUT_SECONDS=0.05`, проверить, что событие отмены выставлено); `test_cancelled_from_worker_is_504` (подмена бросает `TranscriptionCancelled`); `test_external_id_129_chars_400` и `test_external_id_unicode_ok` (Review Focus №4); `test_channel_labels_passed_parsed` (в подмену приходит `["client","","operator"]`); `test_api_key_required` (по образцу `tests/test_security.py`: при `AUTH_MODE=apikey` без ключа 401); `test_extract_endpoints_still_reject_audio` (`/v1/extract/file` с `x.mp3` → 415).
- [ ] **Step 2: Запустить** `python -m pytest tests/test_transcribe_endpoint.py tests/test_utils.py -v --no-cov` — FAIL.
- [ ] **Step 3: Реализовать** эндпоинт и MIME-записи.
- [ ] **Step 4: Запустить** оба файла и затем весь набор `python -m pytest -q --no-cov` — PASS, существующие тесты не сломаны.
- [ ] **Step 5: Commit** — `feat: эндпоинт /v1/transcribe`.

### Task 7: Docker-образ, загрузка весов, compose

**Files:**
- Create: `scripts/download_models.py`
- Modify: `Dockerfile`, `docker-compose.prod.yml`, `docker-compose.yml` (комментарий/переменные при необходимости), `.github/workflows/ci.yml` (если сборка требует прав или кэша)
- Test: `tests/test_download_script.py`

**Interfaces:**
- Consumes: `model_dir`, `vad_dir` (Task 4) и значения `MODELS_DIR`, `TRANSCRIPTION_MODEL`, `TRANSCRIPTION_QUANTIZATION` из окружения.
- Produces: `scripts/download_models.py` с `main() -> None`: независим от `app/` (чтобы тяжёлый слой весов не инвалидировался правкой кода), читает те же env, скачивает модель и silero VAD в `MODELS_DIR/<TRANSCRIPTION_MODEL>` и `MODELS_DIR/silero-vad` через `onnx_asr.load_model(..., path=...)` и `onnx_asr.load_vad("silero", path=...)`; раскладка каталогов дублирует `model_dir`/`vad_dir`.

- [ ] **Step 1: Failing-тест** `tests/test_download_script.py`: `test_download_script_layout_matches_runtime` — загрузить скрипт через `importlib`, с подменой `onnx_asr.load_model`/`load_vad` вызвать `main()` с env `MODELS_DIR=<tmp>` и проверить, что переданные `path` равны `model_dir(tmp, "gigaam-v3-e2e-rnnt")` и `vad_dir(tmp)`; `test_download_script_passes_quantization` (`TRANSCRIPTION_QUANTIZATION=int8` → `quantization="int8"`, пусто → `None`).
- [ ] **Step 2: Запустить** `python -m pytest tests/test_download_script.py -v --no-cov` — FAIL.
- [ ] **Step 3: Реализовать скрипт, затем Dockerfile:** в apt-блок добавить `ffmpeg`; после `pip install` и до `COPY ./app`: `ARG GIGAAM_QUANTIZATION=""`, `ENV MODELS_DIR=/opt/models TRANSCRIPTION_QUANTIZATION=${GIGAAM_QUANTIZATION}`, `COPY scripts/download_models.py /tmp/`, `RUN python /tmp/download_models.py && chmod -R a+rX /opt/models && rm /tmp/download_models.py`; после этого `ENV HF_HUB_OFFLINE=1`. В `docker-compose.prod.yml` (файл объединяется с `docker-compose.yml` в `make prod-up`): у `api` добавить `environment: ENABLE_TRANSCRIPTION=false`; новый сервис `api-audio` — `build: .`, `container_name: extract-text-audio-prod`, команда `uvicorn app.main:app --host 0.0.0.0 --port 7556 --workers 1`, `ports: ["7556:7556"]`, `env_file: .env`, `restart: always`, лимит памяти 4G / 2 CPU (уточняется замером), healthcheck на `http://localhost:7556/health`, логирование как у `api`.
- [ ] **Step 4: Проверить:** `python -m pytest tests/test_download_script.py -v --no-cov` — PASS. Затем `docker build -t extract-text:audio .` — успех. `docker run --rm --network none extract-text:audio sh -c "ffmpeg -version | head -1 && python -c \"import onnx_asr, os; print(sorted(os.listdir('/opt/models')))\""` — выводит версию ffmpeg и каталоги `gigaam-v3-e2e-rnnt`, `silero-vad`. Запуск `docker-compose -f docker-compose.yml -f docker-compose.prod.yml config` проходит без ошибок. Открытый вопрос №4 спецификации (офлайн-загрузка VAD) считается закрытым, только если Task 8 проходит с `--network none`.
- [ ] **Step 5: Commit** — `feat: ffmpeg и веса GigaAM v3 в образе, сервис api-audio`.

### Task 8: Smoke-тест с настоящей моделью

**Files:**
- Create: `tests/audio/` (фикстуры), `tests/test_transcription_real.py`
- Предусловие: заказчик предоставляет короткую (5–15 с) русскую запись без персональных данных → `tests/audio/ru_short.wav`, и по возможности реальные стерео-записи МИКО (вне репозитория) для ручной проверки порядка каналов.

**Interfaces:**
- Consumes: `get_transcriber`, `transcribe_bytes`, `settings.MODELS_DIR`.

- [ ] **Step 1: Тесты** (`@pytest.mark.slow`, `skipif` если нет `model_dir(MODELS_DIR, TRANSCRIPTION_MODEL)` или `ru_short.wav`): `test_real_mono_has_text_and_monotonic_timestamps` (`text` непустой, `start` не убывают, `0 <= start < end <= duration`); `test_real_stereo_assigns_speakers` — стерео собрать в тесте из одного клипа: левый канал — клип, правый — тишина такой же длины после него; ожидаются метки `client` у первых сегментов и `operator` у вторых при `channel_labels=["client","operator"]`; `test_real_silence_is_no_speech` (10 с тишины → `segments == []`). Зарегистрировать маркер `slow` уже есть в `pytest.ini`.
- [ ] **Step 2: Запустить** в собранном контейнере с `--network none`: `docker run --rm --network none -v "$(pwd)":/code -w /code extract-text:audio python -m pytest tests/test_transcription_real.py -v --no-cov` — PASS. Записать в сообщении коммита или заметке измеренный RTF на этой машине (время / длительность аудио).
- [ ] **Step 3: Commit** — `test: smoke-тесты транскрибации с настоящей моделью`.

### Task 9: Документация и версия

**Files:**
- Modify: `app/config.py` (`VERSION = "1.12.0"`), `tests/test_config.py` (существующий `test_default_settings` проверяет `VERSION == "1.11.0"` — обновить), `CHANGELOG.md`, `README.md`, `docs/TZ.md`, `env_example` (если не завершено в Task 1)

- [ ] **Step 1: Failing-тест:** обновить ожидание версии в `test_default_settings` до `"1.12.0"`, запустить `python -m pytest tests/test_config.py -v --no-cov` — FAIL.
- [ ] **Step 2: Обновить версию**; в `CHANGELOG.md` добавить `## [1.12.0] - <дата из date +%Y-%m-%d>` с разделами «Добавлено» (эндпоинт, форматы, лимиты, образ, compose) и «Изменено» (размер образа, ffmpeg); в `docs/TZ.md` — контракт `/v1/transcribe`, форматы, лимиты, коды ошибок; в `README.md` — раздел «Транскрибация аудио»: запрос и ответ `curl` (с `channel_labels` и `external_id`), таблица ошибок, переменные окружения, инструкция по развёртыванию двух сервисов (`api` на 7555, `api-audio` на 7556), требования к CPU/RAM/диску (по измерениям Task 8), как включить int8 (`--build-arg GIGAAM_QUANTIZATION=int8`), как подключить 1С (адрес, `X-API-Key`, обработка 503 с `Retry-After`).
- [ ] **Step 3: Запустить** `make format && make lint-check && python -m pytest -q` — всё PASS, порог покрытия не нарушен.
- [ ] **Step 4: Commit** — `docs: описание API и развёртывания транскрибации, версия 1.12.0`.
