"""Реальные ZIP проходят MIME-проверку до извлечения текста."""

import base64
import io
import zipfile
from unittest.mock import patch

import pytest

from app.utils import validate_file_type

TEXT = "ZIP validation regression: readable document"


@pytest.fixture(params=[zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED])
def zip_content(request):
    """Архив с обычным документом без внешних зависимостей."""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", request.param) as archive:
        archive.writestr("nested/document.txt", TEXT)
    return stream.getvalue()


@pytest.mark.unit
def test_real_zip_is_accepted(zip_content):
    """Проверяется настоящий libmagic, а не подмена MIME в тесте."""
    assert validate_file_type(zip_content, "document.zip") == (True, None)


@pytest.mark.unit
def test_zip_with_generic_mime_is_accepted(zip_content):
    """Общий MIME разрешается только для структурно корректного ZIP."""
    with patch("app.utils.magic.from_buffer", return_value="application/octet-stream"):
        assert validate_file_type(zip_content, "document.zip") == (True, None)


@pytest.mark.unit
@pytest.mark.parametrize("mime", ["text/plain", "application/pdf"])
def test_zip_does_not_override_specific_mime(zip_content, mime):
    """Резервная проверка не отменяет конкретный несовпадающий тип."""
    with patch("app.utils.magic.from_buffer", return_value=mime):
        assert validate_file_type(zip_content, "document.zip")[0] is False


@pytest.mark.unit
@pytest.mark.parametrize("damage", ["not_zip", "truncated", "directory"])
def test_generic_mime_does_not_accept_invalid_zip(zip_content, damage):
    """Подпись или конечная запись ZIP без корректного каталога недостаточны."""
    if damage == "not_zip":
        content = b"PK\x03\x04not an archive"
    elif damage == "truncated":
        content = zip_content[:-22]
    else:
        content = zip_content.replace(b"PK\x01\x02", b"FAIL", 1)
        assert zipfile.is_zipfile(io.BytesIO(content))
    with patch("app.utils.magic.from_buffer", return_value="application/octet-stream"):
        assert validate_file_type(content, "document.zip")[0] is False


@pytest.mark.integration
@pytest.mark.parametrize("endpoint", ["file", "base64"])
def test_zip_extraction_without_mime_mock(test_client, zip_content, endpoint):
    """API действительно извлекает документ из ZIP через оба входных маршрута."""
    if endpoint == "file":
        response = test_client.post(
            "/v1/extract/file",
            files={"file": ("document.zip", zip_content, "application/zip")},
        )
    else:
        response = test_client.post(
            "/v1/extract/base64",
            json={
                "encoded_base64_file": base64.b64encode(zip_content).decode("ascii"),
                "filename": "document.zip",
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "success"
    assert len(body["files"]) == 1
    assert TEXT in body["files"][0]["text"]
