"""Проверки конфигурации развёртывания: env_example и docker-compose.prod.yml."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent

pytestmark = pytest.mark.unit


def _env_example_lines() -> list:
    """Незакомментированные строки env_example."""
    lines = (ROOT / "env_example").read_text(encoding="utf-8").splitlines()
    return [
        line for line in lines if line.strip() and not line.lstrip().startswith("#")
    ]


def test_env_example_does_not_pin_runtime_quantization():
    """TRANSCRIPTION_QUANTIZATION задаёт образ (ENV из build-аргумента).

    Активная строка в .env перебила бы его: образ с весами int8 получил бы
    fp32-настройку, и каждый запрос отвечал бы 503 при зелёном /health.
    """
    pinned = [
        line
        for line in _env_example_lines()
        if line.startswith("TRANSCRIPTION_QUANTIZATION")
    ]

    assert pinned == []


def test_env_example_documents_build_quantization():
    """Выбор int8 описан через GIGAAM_QUANTIZATION, который уходит в сборку."""
    text = (ROOT / "env_example").read_text(encoding="utf-8")

    assert "GIGAAM_QUANTIZATION" in text


@pytest.mark.parametrize("service", ["api", "api-audio"])
def test_compose_passes_quantization_build_arg(service):
    """Compose передаёт GIGAAM_QUANTIZATION в сборку обоих сервисов."""
    compose = yaml.safe_load(
        (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    )

    build = compose["services"][service]["build"]

    assert isinstance(build, dict)
    assert "GIGAAM_QUANTIZATION" in build["args"]
