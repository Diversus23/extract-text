"""Проверки конфигурации развёртывания: env_example и docker-compose.prod.yml."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent

pytestmark = pytest.mark.unit


class _ComposeLoader(yaml.SafeLoader):
    """SafeLoader, понимающий теги Compose: `!reset`, `!override`."""


def _construct_compose_tag(loader, suffix, node):
    """Тег Compose превращается в {"!тег": значение}, чтобы тест видел его в файле."""
    if isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    elif isinstance(node, yaml.MappingNode):
        value = loader.construct_mapping(node, deep=True)
    else:
        value = loader.construct_scalar(node)
    return {f"!{suffix}": value}


_ComposeLoader.add_multi_constructor("!", _construct_compose_tag)


def _load_compose(name: str) -> dict:
    """Разобранный compose-файл из корня репозитория."""
    text = (ROOT / name).read_text(encoding="utf-8")
    return yaml.load(text, Loader=_ComposeLoader)  # nosec B506: свой SafeLoader


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
    compose = _load_compose("docker-compose.prod.yml")

    build = compose["services"][service]["build"]

    assert isinstance(build, dict)
    assert "GIGAAM_QUANTIZATION" in build["args"]


def _audio_service() -> dict:
    """Описание сервиса api-audio из docker-compose.prod.yml."""
    return _load_compose("docker-compose.prod.yml")["services"]["api-audio"]


def test_prod_api_drops_dev_volumes():
    """Prod-сервис api не монтирует dev-каталоги ./app и ./tests.

    `volumes: []` в override не очищает список из docker-compose.yml: списки
    сливаются, и prod запускал бы код с диска вместо кода из образа. Сбросить
    список можно только тегом `!reset` (Compose v2.24.4 и новее).
    """
    api = _load_compose("docker-compose.prod.yml")["services"]["api"]

    assert api["volumes"] == {"!reset": []}


def test_audio_healthcheck_uses_readiness_probe():
    """Healthcheck api-audio ждёт готовую модель, а не просто живой процесс."""
    command = _audio_service()["healthcheck"]["test"]

    assert any("/health?check=transcription" in part for part in command)


def test_audio_threads_can_be_overridden_from_env():
    """TRANSCRIPTION_THREADS из .env не перебивается молча значением из AUDIO_CPUS.

    Compose не задаёт TRANSCRIPTION_THREADS, поэтому значение из .env доходит до
    контейнера как есть. Выбор «TRANSCRIPTION_THREADS, иначе AUDIO_CPUS» делает
    app/config.py: вложенные значения по умолчанию docker-compose v1 не разбирает.
    """
    environment = _audio_service()["environment"]

    assert not any(item.startswith("TRANSCRIPTION_THREADS") for item in environment)
    assert any(item.startswith("AUDIO_CPUS=") for item in environment)


def test_env_example_documents_audio_cpus():
    """AUDIO_CPUS описан: на хосте меньше 4 ядер значение по умолчанию не запустится."""
    text = (ROOT / "env_example").read_text(encoding="utf-8")

    assert "AUDIO_CPUS" in text
