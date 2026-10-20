"""Совместимость compose-файлов со старым docker-compose v1 (его вызывает Makefile)."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.unit
@pytest.mark.parametrize("name", ["docker-compose.yml", "docker-compose.prod.yml"])
def test_no_nested_variable_interpolation(name):
    """docker-compose v1 не разбирает ${A:-${B:-4}}: контейнер получает ${B:-4} как текст."""
    text = (ROOT / name).read_text(encoding="utf-8")

    assert not re.search(r"\$\{[^}]*\$\{", text)
