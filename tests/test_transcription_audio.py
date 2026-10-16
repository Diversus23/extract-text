"""Тесты зондирования и декодирования аудио (ffprobe/ffmpeg) из app/transcription.py."""

import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from app import transcription
from app.config import settings
from app.transcription import (
    AudioFormatError,
    AudioInfo,
    AudioTooLongError,
    ModelUnavailableError,
    decode_audio,
    probe_audio,
)

TWO_SAMPLES = b"\x01\x00" * 100


def _completed(stdout: bytes, returncode: int = 0) -> subprocess.CompletedProcess:
    """Результат подпроцесса для подмены run_subprocess_with_limits."""
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=b""
    )


def _probe_output(channels: int = 1, duration: str = "10.0") -> bytes:
    """Ответ ffprobe в формате JSON; duration=None — поле отсутствует."""
    format_info = {} if duration is None else {"duration": duration}
    return json.dumps(
        {"streams": [{"channels": channels}], "format": format_info}
    ).encode()


def _flag_value(command: list, flag: str) -> str:
    """Значение, которое следует за флагом в списке аргументов команды."""
    return command[command.index(flag) + 1]


@pytest.mark.unit
class TestProbeAudio:
    """Тесты ffprobe-зондирования (подпроцесс подменён)."""

    @patch("app.transcription.run_subprocess_with_limits")
    def test_probe_command_is_hardened(self, run):
        """Команда ffprobe: только протокол file, форсированный демуксер."""
        run.return_value = _completed(_probe_output())

        probe_audio(Path("/tmp/input.m4a"), "m4a")

        command = run.call_args[0][0]
        assert command[0] == "ffprobe"
        assert _flag_value(command, "-protocol_whitelist") == "file"
        assert _flag_value(command, "-f") == "mov"
        assert _flag_value(command, "-select_streams") == "a:0"
        assert command[-1] == str(Path("/tmp/input.m4a"))
        assert run.call_args.kwargs["text"] is False

    @patch("app.transcription.run_subprocess_with_limits")
    def test_probe_returns_channels_and_duration(self, run):
        """Число каналов и длительность берутся из ответа ffprobe."""
        run.return_value = _completed(_probe_output(channels=2, duration="183.4"))

        info = probe_audio(Path("a.mp3"), "mp3")

        assert info == AudioInfo(duration=183.4, channels=2)

    @pytest.mark.parametrize("duration", ["N/A", None, "0.000000", "abc"])
    @patch("app.transcription.run_subprocess_with_limits")
    def test_probe_unknown_duration_is_none(self, run, duration):
        """Неизвестная длительность (N/A, нет поля, ноль) даёт None."""
        run.return_value = _completed(_probe_output(duration=duration))

        assert probe_audio(Path("a.aac"), "aac") == AudioInfo(None, 1)

    @patch("app.transcription.run_subprocess_with_limits")
    def test_probe_no_audio_stream_raises(self, run):
        """Файл без аудиодорожки — AudioFormatError."""
        run.return_value = _completed(b'{"streams": [], "format": {}}')

        with pytest.raises(AudioFormatError):
            probe_audio(Path("a.m4a"), "m4a")

    @patch("app.transcription.run_subprocess_with_limits")
    def test_probe_too_long_raises(self, run):
        """Длительность больше лимита — AudioTooLongError."""
        limit = settings.MAX_AUDIO_DURATION_SECONDS
        run.return_value = _completed(_probe_output(duration=f"{limit + 1}.0"))

        with pytest.raises(AudioTooLongError):
            probe_audio(Path("a.mp3"), "mp3")

    @patch("app.transcription.run_subprocess_with_limits")
    def test_probe_nonzero_exit_raises(self, run):
        """Ненулевой код ffprobe — AudioFormatError."""
        run.return_value = _completed(b"", returncode=1)

        with pytest.raises(AudioFormatError):
            probe_audio(Path("a.mp3"), "mp3")

    @patch("app.transcription.run_subprocess_with_limits")
    def test_probe_invalid_json_raises(self, run):
        """Нечитаемый ответ ffprobe — AudioFormatError."""
        run.return_value = _completed(b"not json")

        with pytest.raises(AudioFormatError):
            probe_audio(Path("a.mp3"), "mp3")

    @patch("app.transcription.run_subprocess_with_limits")
    def test_probe_timeout_raises(self, run):
        """Таймаут ffprobe — AudioFormatError."""
        run.side_effect = subprocess.TimeoutExpired(cmd="ffprobe", timeout=30)

        with pytest.raises(AudioFormatError):
            probe_audio(Path("a.mp3"), "mp3")

    @patch("app.transcription.run_subprocess_with_limits")
    def test_probe_missing_binary_is_unavailable(self, run):
        """Нет ffprobe в системе — сервис недоступен (503), а не ошибка файла."""
        run.side_effect = FileNotFoundError("ffprobe")

        with pytest.raises(ModelUnavailableError):
            probe_audio(Path("a.mp3"), "mp3")

    def test_probe_unknown_extension_raises(self):
        """Расширение вне allowlist демуксеров отклоняется до запуска ffprobe."""
        with pytest.raises(AudioFormatError):
            probe_audio(Path("a.txt"), "txt")

    def test_demuxers_cover_all_audio_formats(self):
        """Для каждого поддерживаемого аудио-расширения задан демуксер."""
        assert set(settings.AUDIO_FORMATS) == set(transcription.FFMPEG_DEMUXERS)


@pytest.mark.unit
class TestDecodeAudio:
    """Тесты ffmpeg-декодирования (подпроцесс подменён)."""

    @patch("app.transcription.run_subprocess_with_limits")
    def test_decode_command_caps_duration(self, run):
        """Команда ffmpeg: ограничение по длительности, без stdin, 16 кГц."""
        run.return_value = _completed(TWO_SAMPLES)

        decode_audio(Path("/tmp/input.mp3"), "mp3", channels=1)

        command = run.call_args[0][0]
        assert command[0] == "ffmpeg"
        assert "-nostdin" in command
        assert _flag_value(command, "-t") == str(
            settings.MAX_AUDIO_DURATION_SECONDS + 1
        )
        assert _flag_value(command, "-ar") == "16000"
        assert _flag_value(command, "-ac") == "1"
        assert _flag_value(command, "-protocol_whitelist") == "file"
        assert _flag_value(command, "-f") == "mp3"
        assert run.call_args.kwargs["text"] is False

    @patch("app.transcription.run_subprocess_with_limits")
    def test_decode_stereo_splits_interleaved_channels(self, run):
        """Стерео: интерливленный PCM раскладывается по каналам."""
        samples = np.array([1, -1, 2, -2, 3, -3], dtype="<i2")
        run.return_value = _completed(samples.tobytes())

        pcm = decode_audio(Path("a.wav"), "wav", channels=2)

        assert pcm.dtype == np.int16
        assert pcm.shape == (2, 3)
        assert pcm[0].tolist() == [1, 2, 3]
        assert pcm[1].tolist() == [-1, -2, -3]
        assert _flag_value(run.call_args[0][0], "-ac") == "2"

    @patch("app.transcription.run_subprocess_with_limits")
    def test_decode_multichannel_downmixed_to_mono(self, run):
        """Больше двух каналов сводятся в моно."""
        run.return_value = _completed(TWO_SAMPLES)

        pcm = decode_audio(Path("a.wav"), "wav", channels=6)

        assert pcm.shape == (1, 100)
        assert _flag_value(run.call_args[0][0], "-ac") == "1"

    @patch("app.transcription.run_subprocess_with_limits")
    def test_decode_over_limit_raises(self, run, monkeypatch):
        """Декодированный звук длиннее лимита — AudioTooLongError."""
        monkeypatch.setattr(settings, "MAX_AUDIO_DURATION_SECONDS", 1)
        run.return_value = _completed(b"\x01\x00" * (16000 + 1))

        with pytest.raises(AudioTooLongError):
            decode_audio(Path("a.aac"), "aac", channels=1)

    @patch("app.transcription.run_subprocess_with_limits")
    def test_decode_exactly_at_limit_is_ok(self, run, monkeypatch):
        """Ровно лимит секунд — допустимо."""
        monkeypatch.setattr(settings, "MAX_AUDIO_DURATION_SECONDS", 1)
        run.return_value = _completed(b"\x01\x00" * 16000)

        assert decode_audio(Path("a.aac"), "aac", channels=1).shape == (1, 16000)

    @patch("app.transcription.run_subprocess_with_limits")
    def test_decode_failure_raises(self, run):
        """Ненулевой код ffmpeg — AudioFormatError."""
        run.return_value = _completed(b"", returncode=1)

        with pytest.raises(AudioFormatError):
            decode_audio(Path("a.mp3"), "mp3", channels=1)

    @patch("app.transcription.run_subprocess_with_limits")
    def test_decode_empty_output_raises(self, run):
        """Пустой PCM на выходе — AudioFormatError."""
        run.return_value = _completed(b"")

        with pytest.raises(AudioFormatError):
            decode_audio(Path("a.mp3"), "mp3", channels=1)

    @pytest.mark.parametrize(
        "error", [MemoryError(), subprocess.TimeoutExpired(cmd="ffmpeg", timeout=1)]
    )
    @patch("app.transcription.run_subprocess_with_limits")
    def test_decode_resource_errors_raise(self, run, error):
        """Лимит памяти и таймаут ffmpeg — AudioFormatError."""
        run.side_effect = error

        with pytest.raises(AudioFormatError):
            decode_audio(Path("a.mp3"), "mp3", channels=1)


requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe не установлены",
)


def _ffmpeg(*args: str) -> None:
    """Запуск настоящего ffmpeg для подготовки тестовых файлов."""
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", *args], check=True, capture_output=True
    )


def _sine(seconds: int) -> list:
    """Аргументы ffmpeg: источник синуса заданной длительности."""
    return ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]


@requires_ffmpeg
@pytest.mark.unit
class TestRealFfmpeg:
    """Тесты с настоящими ffprobe/ffmpeg."""

    def test_real_roundtrip_stereo_wav(self, tmp_path):
        """Стерео WAV: два канала, длительность около двух секунд."""
        path = tmp_path / "input.wav"
        _ffmpeg(*_sine(2), "-ac", "2", "-ar", "16000", str(path))

        info = probe_audio(path, "wav")
        pcm = decode_audio(path, "wav", info.channels)

        assert info.channels == 2
        assert info.duration == pytest.approx(2.0, abs=0.1)
        assert pcm.shape[0] == 2
        assert pcm.shape[1] == pytest.approx(32000, abs=1600)

    def test_real_mp3_mono(self, tmp_path):
        """MP3 моно декодируется в один канал."""
        path = tmp_path / "input.mp3"
        _ffmpeg(*_sine(2), "-c:a", "libmp3lame", str(path))

        info = probe_audio(path, "mp3")
        pcm = decode_audio(path, "mp3", info.channels)

        assert info.channels == 1
        assert pcm.shape[0] == 1

    def test_real_mp4_with_video_and_audio(self, tmp_path):
        """Контейнер с видео и аудио: берётся аудиодорожка."""
        path = tmp_path / "input.m4a"
        video = ["-f", "lavfi", "-i", "testsrc=duration=2:size=64x64:rate=5"]
        _ffmpeg(
            *video, *_sine(2), "-c:v", "mpeg4", "-c:a", "aac", "-f", "mp4", str(path)
        )

        info = probe_audio(path, "m4a")
        pcm = decode_audio(path, "m4a", info.channels)

        assert info.channels == 1
        assert pcm.shape[0] == 1
        assert pcm.shape[1] > 16000

    def test_real_mp4_without_audio_raises(self, tmp_path):
        """Контейнер только с видео — AudioFormatError."""
        path = tmp_path / "input.m4a"
        video = ["-f", "lavfi", "-i", "testsrc=duration=1:size=64x64:rate=5"]
        _ffmpeg(*video, "-c:v", "mpeg4", "-an", "-f", "mp4", str(path))

        with pytest.raises(AudioFormatError):
            probe_audio(path, "m4a")

    def test_real_five_one_downmixed_to_mono(self, tmp_path):
        """Дорожка 5.1 (шесть каналов) сводится в моно."""
        path = tmp_path / "input.wav"
        source = ["-f", "lavfi", "-i", "anullsrc=channel_layout=5.1:sample_rate=16000"]
        _ffmpeg(*source, "-t", "1", str(path))

        info = probe_audio(path, "wav")
        pcm = decode_audio(path, "wav", info.channels)

        assert info.channels == 6
        assert pcm.shape[0] == 1

    def test_real_too_long_by_probe(self, tmp_path, monkeypatch):
        """Известная длительность больше лимита отклоняется до декодирования."""
        path = tmp_path / "input.wav"
        _ffmpeg(*_sine(3), "-ar", "16000", str(path))
        monkeypatch.setattr(settings, "MAX_AUDIO_DURATION_SECONDS", 1)

        with pytest.raises(AudioTooLongError):
            probe_audio(path, "wav")

    def test_real_decode_cap_enforces_limit(self, tmp_path, monkeypatch):
        """Даже без проверки зондом декодирование упирается в лимит."""
        path = tmp_path / "input.wav"
        _ffmpeg(*_sine(3), "-ar", "16000", str(path))
        monkeypatch.setattr(settings, "MAX_AUDIO_DURATION_SECONDS", 1)

        with pytest.raises(AudioTooLongError):
            decode_audio(path, "wav", channels=1)

    def test_real_garbage_file_raises(self, tmp_path):
        """Случайные байты под видом mp3 — AudioFormatError."""
        path = tmp_path / "input.mp3"
        path.write_bytes(bytes(range(256)) * 40)

        with pytest.raises(AudioFormatError):
            probe_audio(path, "mp3")

    @pytest.mark.parametrize(
        "extension,content",
        [
            ("mp3", b"#EXTM3U\n#EXTINF:1,\nhttp://127.0.0.1:9/x.mp3\n"),
            ("wav", b"ffconcat version 1.0\nfile /etc/passwd\n"),
        ],
    )
    def test_real_playlist_and_concat_are_not_followed(
        self, tmp_path, extension, content
    ):
        """Плейлисты и concat-скрипты не разворачиваются (защита от SSRF/LFI)."""
        path = tmp_path / f"input.{extension}"
        path.write_bytes(content)

        with pytest.raises(AudioFormatError):
            probe_audio(path, extension)
