"""Тесты скрипта загрузки весов модели при сборке образа."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import settings
from app.transcription import model_dir, vad_dir

SCRIPT = Path(__file__).parent.parent / "scripts" / "download_models.py"

pytestmark = pytest.mark.unit


def _load_script():
    """Импортирует скрипт: scripts/ не является пакетом."""
    spec = importlib.util.spec_from_file_location("download_models", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_download_script_layout_matches_runtime(tmp_path, monkeypatch):
    """Скрипт кладёт веса туда, откуда их читает рантайм (model_dir / vad_dir)."""
    monkeypatch.setenv("MODELS_DIR", str(tmp_path))
    monkeypatch.delenv("TRANSCRIPTION_MODEL", raising=False)
    monkeypatch.delenv("TRANSCRIPTION_QUANTIZATION", raising=False)

    with (
        patch("onnx_asr.load_model") as load_model,
        patch("onnx_asr.load_vad") as load_vad,
    ):
        _load_script().main()

    assert load_model.call_args.args == (
        settings.TRANSCRIPTION_MODEL,
        model_dir(str(tmp_path), settings.TRANSCRIPTION_MODEL),
    )
    assert load_vad.call_args.args == ("silero", vad_dir(str(tmp_path)))


@pytest.mark.parametrize("value,expected", [("", None), ("int8", "int8")])
def test_download_script_passes_quantization(tmp_path, monkeypatch, value, expected):
    """Пустая квантизация — fp32 (None), иначе передаётся как есть."""
    monkeypatch.setenv("MODELS_DIR", str(tmp_path))
    monkeypatch.setenv("TRANSCRIPTION_QUANTIZATION", value)

    with patch("onnx_asr.load_model") as load_model, patch("onnx_asr.load_vad"):
        _load_script().main()

    assert load_model.call_args.kwargs["quantization"] == expected


def test_download_script_uses_model_from_env(tmp_path, monkeypatch):
    """Имя модели берётся из TRANSCRIPTION_MODEL."""
    monkeypatch.setenv("MODELS_DIR", str(tmp_path))
    monkeypatch.setenv("TRANSCRIPTION_MODEL", "gigaam-v3-e2e-ctc")

    with patch("onnx_asr.load_model") as load_model, patch("onnx_asr.load_vad"):
        _load_script().main()

    assert load_model.call_args.args == (
        "gigaam-v3-e2e-ctc",
        model_dir(str(tmp_path), "gigaam-v3-e2e-ctc"),
    )
