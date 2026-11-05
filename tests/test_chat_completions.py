"""POST /v1/chat/completions: извлечение текста через модель softonit/extracttext."""

import base64
import io
import logging
import re
import time
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.chat_completions import (
    CHAT_BODY_OVERHEAD_BYTES,
    ChatFile,
    build_chat_response,
    chat_body_limit,
    format_extraction_content,
    parse_chat_request,
)
from app.config import settings
from app.openai_compat import EXTRACTION_MODEL_ID, OpenAIAPIError

PATH = "/v1/chat/completions"
LEGACY_PATH = "/v1/extract/file"
TESTS_DIR = Path(__file__).parent
TRANSCRIPTION_ID = "softonit/gigaam-v3-e2e-rnnt"
TEXT = "Тестовый текст для проверки\nВторая строка".encode("utf-8")

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def open_api(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "none")


def data_url(content, mime="application/octet-stream"):
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


def file_part(name="test.txt", content=TEXT, **extra):
    file = {"filename": name, "file_data": data_url(content)}
    file.update(extra)
    return {"type": "file", "file": file}


def chat_payload(name="test.txt", content=TEXT, **extra):
    payload = {
        "model": EXTRACTION_MODEL_ID,
        "messages": [{"role": "user", "content": [file_part(name, content)]}],
    }
    payload.update(extra)
    return payload


def post_chat(client, payload, headers=None):
    return client.post(PATH, json=payload, headers=headers)


def error_of(response, status, code):
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"message", "type", "param", "code"}
    assert body["error"]["code"] == code
    return body["error"]


def expected_content(files):
    return "\n".join(
        f"--- FILE: {item['filename'].strip()} ---\n{item['text']}"
        for item in files
        if "text" in item
    )


def zip_with_files(names):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.writestr(name, f"Содержимое файла {name}")
    return stream.getvalue()


# --- успешный ответ ---------------------------------------------------------


def test_success_txt_response_shape(test_client):
    response = post_chat(test_client, chat_payload())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert set(body) == {"id", "object", "created", "model", "choices", "usage"}
    assert re.fullmatch(r"chatcmpl-[0-9a-f]{32}", body["id"])
    assert body["object"] == "chat.completion"
    assert body["model"] == EXTRACTION_MODEL_ID
    assert abs(body["created"] - time.time()) < 60
    assert body["usage"] == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    (choice,) = body["choices"]
    assert choice["index"] == 0
    assert choice["finish_reason"] == "stop"
    assert choice["message"]["role"] == "assistant"
    assert choice["message"]["content"] == (
        "--- FILE: test.txt ---\n" + TEXT.decode("utf-8")
    )


def test_ids_are_unique(test_client):
    first = post_chat(test_client, chat_payload()).json()["id"]
    second = post_chat(test_client, chat_payload()).json()["id"]
    assert first != second


def test_mime_in_data_url_is_ignored(test_client):
    payload = chat_payload()
    payload["messages"][0]["content"][0]["file"]["file_data"] = data_url(
        TEXT, "image/png"
    )
    assert post_chat(test_client, payload).status_code == 200


# --- golden: сравнение со старым маршрутом ----------------------------------


@pytest.mark.parametrize(
    "name,content,blocks",
    [
        ("test.txt", (TESTS_DIR / "test.txt").read_bytes(), 1),
        ("test.csv", (TESTS_DIR / "test.csv").read_bytes(), 1),
        ("test.docx", (TESTS_DIR / "test.docx").read_bytes(), 1),
        ("bundle.zip", zip_with_files(["a.txt", "dir/b.txt", "c.txt"]), 3),
    ],
    ids=["txt", "csv", "docx", "zip"],
)
def test_content_equals_blocks_of_legacy_route(test_client, name, content, blocks):
    legacy = test_client.post(
        LEGACY_PATH, files={"file": (name, content, "application/octet-stream")}
    )
    assert legacy.status_code == 200
    files = legacy.json()["files"]
    assert len(files) == blocks

    response = post_chat(test_client, chat_payload(name, content))

    assert response.status_code == 200
    text = response.json()["choices"][0]["message"]["content"]
    assert text == expected_content(files)
    assert text.count("--- FILE: ") == blocks


def test_every_file_of_archive_gets_a_block(test_client):
    content = zip_with_files(["one.txt", "two.txt"])
    text = post_chat(test_client, chat_payload("pack.zip", content)).json()["choices"][
        0
    ]["message"]["content"]
    assert text.startswith("--- FILE: ")
    assert "one.txt ---\nСодержимое файла one.txt" in text
    assert "\n--- FILE: " in text
    assert "two.txt ---\nСодержимое файла two.txt" in text


def test_extra_parameters_and_text_parts_are_ignored(test_client):
    payload = {
        "model": EXTRACTION_MODEL_ID,
        "temperature": 0.2,
        "max_tokens": 10,
        "n": 3,
        "user": "someone",
        "stream": False,
        "messages": [
            {"role": "system", "content": "Игнорируется"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "подпись"},
                    file_part(),
                ],
            },
        ],
    }
    baseline = post_chat(test_client, chat_payload()).json()
    response = post_chat(test_client, payload)
    assert response.status_code == 200
    assert (
        response.json()["choices"][0]["message"]["content"]
        == baseline["choices"][0]["message"]["content"]
    )


# --- stream и model ----------------------------------------------------------


def test_stream_true_is_rejected(test_client):
    with patch("app.extractors.TextExtractor.extract_text") as extract:
        response = post_chat(test_client, chat_payload(stream=True))
    error = error_of(response, 400, "unsupported_parameter")
    assert error["param"] == "stream"
    extract.assert_not_called()


def test_stream_false_is_accepted(test_client):
    assert post_chat(test_client, chat_payload(stream=False)).status_code == 200


def test_stream_of_wrong_type_is_rejected(test_client):
    error_of(post_chat(test_client, chat_payload(stream="yes")), 400, "invalid_request")


def test_model_is_required(test_client):
    payload = chat_payload()
    del payload["model"]
    error = error_of(post_chat(test_client, payload), 400, "missing_required_parameter")
    assert error["param"] == "model"


def test_empty_model_is_required_too(test_client):
    error_of(
        post_chat(test_client, chat_payload(model="")),
        400,
        "missing_required_parameter",
    )


def test_model_of_wrong_type_is_rejected(test_client):
    error_of(post_chat(test_client, chat_payload(model=5)), 400, "invalid_request")


@pytest.mark.parametrize("model", [TRANSCRIPTION_ID, "gigaam-v3-e2e-rnnt"])
def test_transcription_model_is_not_an_extraction_model(test_client, model):
    with patch("app.extractors.TextExtractor.extract_text") as extract:
        response = post_chat(test_client, chat_payload(model=model))
    error = error_of(response, 404, "model_not_found")
    assert error["message"] == "Not an extraction model"
    assert error["param"] == "model"
    extract.assert_not_called()


@pytest.mark.parametrize("model", ["other", "extracttext", "gpt-4o"])
def test_unknown_model_is_rejected(test_client, model):
    with patch("app.extractors.TextExtractor.extract_text") as extract:
        response = post_chat(test_client, chat_payload(model=model))
    error = error_of(response, 404, "model_not_found")
    assert error["message"] == "Unknown extraction model"
    extract.assert_not_called()


# --- разбор частей сообщений -------------------------------------------------


def test_missing_file_part(test_client):
    payload = chat_payload()
    payload["messages"][0]["content"] = [{"type": "text", "text": "только текст"}]
    error = error_of(post_chat(test_client, payload), 400, "missing_required_parameter")
    assert error["param"] == "messages"


def test_string_content_only_means_missing_file(test_client):
    payload = chat_payload()
    payload["messages"] = [{"role": "user", "content": "привет"}]
    error_of(post_chat(test_client, payload), 400, "missing_required_parameter")


def test_two_file_parts_are_rejected(test_client):
    payload = chat_payload()
    payload["messages"][0]["content"].append(file_part("second.txt"))
    with patch("app.extractors.TextExtractor.extract_text") as extract:
        response = post_chat(test_client, payload)
    error_of(response, 400, "too_many_files")
    extract.assert_not_called()


def test_file_parts_in_different_messages_are_counted_together(test_client):
    payload = chat_payload()
    payload["messages"].append({"role": "user", "content": [file_part("b.txt")]})
    error_of(post_chat(test_client, payload), 400, "too_many_files")


def test_file_id_is_not_supported(test_client):
    payload = chat_payload()
    payload["messages"][0]["content"] = [
        {"type": "file", "file": {"file_id": "file-abc", "filename": "a.txt"}}
    ]
    error_of(post_chat(test_client, payload), 400, "unsupported_parameter")


def test_file_id_with_file_data_is_rejected(test_client):
    payload = chat_payload()
    payload["messages"][0]["content"][0]["file"]["file_id"] = "file-abc"
    error_of(post_chat(test_client, payload), 400, "unsupported_parameter")


@pytest.mark.parametrize("filename", [None, "", "   ", 5])
def test_filename_is_required(test_client, filename):
    payload = chat_payload()
    file = payload["messages"][0]["content"][0]["file"]
    if filename is None:
        del file["filename"]
    else:
        file["filename"] = filename
    response = post_chat(test_client, payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] in {
        "missing_required_parameter",
        "invalid_request",
    }


def test_file_object_is_required(test_client):
    payload = chat_payload()
    payload["messages"][0]["content"] = [{"type": "file"}]
    error_of(post_chat(test_client, payload), 400, "missing_required_parameter")


@pytest.mark.parametrize("kind", ["image_url", "input_audio", "refusal"])
def test_unsupported_part_types(test_client, kind):
    payload = chat_payload()
    payload["messages"][0]["content"].append({"type": kind})
    error = error_of(post_chat(test_client, payload), 400, "unsupported_content_type")
    assert error["param"] == "messages"


@pytest.mark.parametrize(
    "messages",
    [[], "text", {"role": "user"}, [5], [{"role": "user", "content": 5}]],
)
def test_malformed_messages(test_client, messages):
    payload = chat_payload()
    payload["messages"] = messages
    error_of(post_chat(test_client, payload), 400, "invalid_request")


def test_part_must_be_an_object(test_client):
    payload = chat_payload()
    payload["messages"][0]["content"] = ["text"]
    error_of(post_chat(test_client, payload), 400, "invalid_request")


def test_messages_are_required(test_client):
    payload = chat_payload()
    del payload["messages"]
    error_of(post_chat(test_client, payload), 400, "missing_required_parameter")


def test_body_must_be_a_json_object(test_client):
    error_of(post_chat(test_client, ["not", "an", "object"]), 400, "invalid_request")


def test_invalid_json_is_in_the_envelope(test_client):
    response = test_client.post(
        PATH, content=b"{not json", headers={"Content-Type": "application/json"}
    )
    error_of(response, 400, "invalid_request")


def test_invalid_utf8_is_in_the_envelope(test_client):
    response = test_client.post(
        PATH, content=b"\xff\xfe\x00", headers={"Content-Type": "application/json"}
    )
    error_of(response, 400, "invalid_request")


def test_deeply_nested_json_does_not_crash(test_client):
    response = test_client.post(
        PATH,
        content=b"[" * 200000,
        headers={"Content-Type": "application/json"},
    )
    error_of(response, 400, "invalid_request")


@pytest.mark.parametrize(
    "content_type", ["text/plain", "multipart/form-data; boundary=x", ""]
)
def test_content_type_must_be_json(test_client, content_type):
    headers = {"Content-Type": content_type} if content_type else {}
    response = test_client.post(PATH, content=b"{}", headers=headers)
    error_of(response, 415, "unsupported_media_type")


def test_json_content_type_with_charset_is_accepted(test_client):
    import json

    response = test_client.post(
        PATH,
        content=json.dumps(chat_payload()).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    assert response.status_code == 200


# --- file_data ---------------------------------------------------------------


@pytest.mark.parametrize(
    "file_data",
    [
        "QUJD",
        "data:text/plain,hello",
        "data:text/plain;charset=utf-8,hello",
        "text/plain;base64,QUJD",
        "http://example.com/a.txt",
    ],
)
def test_file_data_must_be_a_base64_data_url(test_client, file_data):
    payload = chat_payload()
    payload["messages"][0]["content"][0]["file"]["file_data"] = file_data
    error = error_of(post_chat(test_client, payload), 400, "invalid_file_data")
    assert file_data not in error["message"]


@pytest.mark.parametrize(
    "encoded", ["!!!!", "QUJ", "QU=D", "QUJDx", "Привет", "QUJD====", "QU JD"]
)
def test_broken_base64(test_client, encoded):
    payload = chat_payload()
    payload["messages"][0]["content"][0]["file"][
        "file_data"
    ] = f"data:text/plain;base64,{encoded}"
    error_of(post_chat(test_client, payload), 400, "invalid_file_data")


@pytest.mark.parametrize("file_data", [None, "", 5])
def test_file_data_is_required(test_client, file_data):
    payload = chat_payload()
    file = payload["messages"][0]["content"][0]["file"]
    if file_data is None:
        del file["file_data"]
    else:
        file["file_data"] = file_data
    response = post_chat(test_client, payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "missing_required_parameter"


@pytest.mark.parametrize("separator", ["\r\n", "\n"])
def test_line_breaks_inside_base64_are_allowed(test_client, separator):
    encoded = base64.b64encode(TEXT).decode("ascii")
    chunks = [encoded[i : i + 16] for i in range(0, len(encoded), 16)]
    payload = chat_payload()
    payload["messages"][0]["content"][0]["file"]["file_data"] = (
        "data:text/plain;base64," + separator.join(chunks)
    )
    baseline = post_chat(test_client, chat_payload()).json()
    response = post_chat(test_client, payload)
    assert response.status_code == 200
    assert (
        response.json()["choices"][0]["message"]["content"]
        == baseline["choices"][0]["message"]["content"]
    )


def test_empty_content_is_unprocessable(test_client):
    with patch("app.extractors.TextExtractor.extract_text") as extract:
        response = post_chat(test_client, chat_payload(content=b""))
    error = error_of(response, 422, "invalid_file")
    assert error["message"] == "File is empty"
    extract.assert_not_called()


# --- размер файла ------------------------------------------------------------


def test_file_of_exactly_max_size_is_accepted(test_client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 100)
    content = b"a" * 100
    response = post_chat(test_client, chat_payload(content=content))
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"].endswith("a" * 100)


@pytest.mark.parametrize("size", [101, 102, 103, 500])
def test_file_larger_by_a_byte_is_rejected_before_decoding(
    test_client, monkeypatch, size
):
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 100)
    with (
        patch("app.chat_completions.base64.b64decode") as decode,
        patch("app.extractors.TextExtractor.extract_text") as extract,
    ):
        response = post_chat(test_client, chat_payload(content=b"a" * size))
    error = error_of(response, 413, "file_too_large")
    assert "100" in error["message"]
    decode.assert_not_called()
    extract.assert_not_called()


def test_size_is_checked_after_decoding_too(monkeypatch):
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 100)
    payload = chat_payload(content=b"a" * 10)
    with patch("app.chat_completions.base64.b64decode", return_value=b"a" * 101):
        with pytest.raises(OpenAIAPIError) as raised:
            parse_chat_request(payload)
    assert raised.value.status == 413
    assert raised.value.code == "file_too_large"


def test_body_larger_than_limit_is_rejected(test_client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 100)
    body = b" " * (chat_body_limit() + 1)
    response = test_client.post(
        PATH, content=body, headers={"Content-Type": "application/json"}
    )
    error_of(response, 413, "file_too_large")


def test_chat_body_limit_formula(monkeypatch):
    assert CHAT_BODY_OVERHEAD_BYTES == 256 * 1024
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 20 * 1024 * 1024)
    assert chat_body_limit() == 27962028 + 262144
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 3)
    assert chat_body_limit() == 4 + CHAT_BODY_OVERHEAD_BYTES
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 4)
    assert chat_body_limit() == 8 + CHAT_BODY_OVERHEAD_BYTES


def test_limit_fits_file_of_max_size(monkeypatch):
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 1000)
    payload = chat_payload("name.txt", b"x" * 1000)
    import json

    assert len(json.dumps(payload).encode("utf-8")) < chat_body_limit()


# --- отображение ошибок общей функции ----------------------------------------


def test_extension_mismatch_is_unsupported_media(test_client):
    response = post_chat(test_client, chat_payload("fake.pdf", b"plain text only"))
    error = error_of(response, 415, "unsupported_file_format")
    assert error["type"] == "invalid_request_error"


def test_validation_failure_is_415(test_client):
    with patch("app.main.validate_file_type", return_value=(False, "mismatch")):
        response = post_chat(test_client, chat_payload())
    error_of(response, 415, "unsupported_file_format")


def test_unsupported_format_is_415(test_client):
    with (
        patch("app.main.validate_file_type", return_value=(True, None)),
        patch(
            "app.extractors.TextExtractor.extract_text",
            side_effect=ValueError("Unsupported file format: .xyz"),
        ),
    ):
        response = post_chat(test_client, chat_payload())
    error_of(response, 415, "unsupported_file_format")


def test_damaged_file_is_422(test_client):
    with patch(
        "app.extractors.TextExtractor.extract_text", side_effect=ValueError("broken")
    ):
        response = post_chat(test_client, chat_payload())
    error = error_of(response, 422, "invalid_file")
    assert "broken" not in error["message"]


def test_unexpected_exception_is_500_here_and_422_on_legacy_route(test_client):
    boom = RuntimeError("секретная подробность")
    with patch("app.extractors.TextExtractor.extract_text", side_effect=boom):
        chat = post_chat(test_client, chat_payload())
        legacy = test_client.post(
            LEGACY_PATH, files={"file": ("test.txt", TEXT, "text/plain")}
        )
    error = error_of(chat, 500, "internal_error")
    assert error["type"] == "server_error"
    assert "секретная" not in error["message"]
    assert legacy.status_code == 422
    assert legacy.json() == {
        "status": "error",
        "filename": "test.txt",
        "message": "Файл поврежден или формат не поддерживается.",
    }


def test_timeout_is_504(test_client, monkeypatch):
    monkeypatch.setattr(settings, "PROCESSING_TIMEOUT_SECONDS", 0.05)

    def slow(*args, **kwargs):
        time.sleep(0.5)
        return []

    with patch("app.extractors.TextExtractor.extract_text", side_effect=slow):
        response = post_chat(test_client, chat_payload())
    error = error_of(response, 504, "request_timeout")
    assert error["type"] == "server_error"


def test_extraction_runs_in_threadpool(test_client):
    with patch("app.main.run_in_threadpool") as pool:

        async def fake(function, *args):
            return [{"filename": "x.txt", "text": "из пула"}]

        pool.side_effect = fake
        response = post_chat(test_client, chat_payload())
    assert response.json()["choices"][0]["message"]["content"] == (
        "--- FILE: x.txt ---\nиз пула"
    )
    assert pool.call_count == 1


def test_unexpected_failure_outside_extraction_is_500_in_envelope(test_client):
    with patch("app.main.parse_chat_request", side_effect=RuntimeError("bug")):
        response = post_chat(test_client, chat_payload())
    error_of(response, 500, "internal_error")


# --- авторизация -------------------------------------------------------------


@pytest.fixture
def protected(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "apikey")
    monkeypatch.setattr(settings, "API_KEYS", ["secret"])


@pytest.mark.parametrize(
    "headers,status",
    [
        ({"Authorization": "Bearer secret"}, 200),
        ({"Authorization": "bearer secret"}, 200),
        ({"X-API-Key": "secret"}, 200),
        ({"X-API-Key": "secret", "Authorization": "Bearer wrong"}, 200),
        ({"X-API-Key": "wrong", "Authorization": "Bearer secret"}, 401),
        ({"X-API-Key": "wrong"}, 401),
        ({"Authorization": "Bearer wrong"}, 401),
        ({"Authorization": "Basic secret"}, 401),
        ({}, 401),
    ],
)
def test_credentials(test_client, protected, headers, status):
    response = post_chat(test_client, chat_payload(), headers=headers)
    assert response.status_code == status
    if status == 401:
        error_of(response, 401, "invalid_api_key")
        assert response.headers["www-authenticate"] == "Bearer"


def test_unauthorized_request_does_not_extract(test_client, protected):
    with patch("app.extractors.TextExtractor.extract_text") as extract:
        post_chat(test_client, chat_payload())
    extract.assert_not_called()


def test_disabled_auth_ignores_credentials(test_client):
    response = post_chat(
        test_client, chat_payload(), headers={"Authorization": "Bearer junk"}
    )
    assert response.status_code == 200


# --- методы и конверт --------------------------------------------------------


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE", "PATCH"])
def test_other_methods_are_405_in_the_envelope(test_client, method):
    response = test_client.request(method, PATH)
    error = error_of(response, 405, "method_not_allowed")
    assert error["type"] == "invalid_request_error"


def test_405_code_is_shared_by_other_compat_paths(test_client):
    response = test_client.get("/v1/audio/transcriptions")
    error_of(response, 405, "method_not_allowed")


def test_legacy_routes_keep_their_405_format(test_client):
    response = test_client.get(LEGACY_PATH)
    assert response.status_code == 405
    assert response.json() == {"detail": "Method Not Allowed"}


# --- секреты в логах ---------------------------------------------------------


@pytest.mark.parametrize("scenario", ["success", "broken", "extract_error"])
def test_base64_and_file_data_never_reach_the_logs(test_client, caplog, scenario):
    content = bytes(range(33, 126)) * 20
    encoded = base64.b64encode(content).decode("ascii")
    payload = chat_payload("log.txt", content)
    if scenario == "broken":
        payload["messages"][0]["content"][0]["file"]["file_data"] = (
            "data:text/plain;base64," + encoded + "!"
        )
    with caplog.at_level(logging.DEBUG):
        if scenario == "extract_error":
            with patch(
                "app.extractors.TextExtractor.extract_text",
                side_effect=RuntimeError("fail"),
            ):
                post_chat(test_client, payload)
        else:
            post_chat(test_client, payload)
    if scenario == "success":
        assert "chat/completions" in caplog.text
    assert encoded[:40] not in caplog.text
    assert "file_data" not in caplog.text
    assert "data:" not in caplog.text
    assert "base64" not in caplog.text.lower()


# --- чистые функции ----------------------------------------------------------


def test_format_content_blocks():
    files = [
        {"filename": "  a.txt ", "text": "первый"},
        {"filename": "b/c.txt", "text": ""},
        {"filename": "no-text.bin"},
        {"filename": "d.txt", "text": "последний\n"},
    ]
    assert format_extraction_content(files) == (
        "--- FILE: a.txt ---\nпервый\n--- FILE: b/c.txt ---\n"
        "\n--- FILE: d.txt ---\nпоследний\n"
    )


def test_format_content_single_file_has_a_block():
    assert format_extraction_content([{"filename": "x.txt", "text": "t"}]) == (
        "--- FILE: x.txt ---\nt"
    )


def test_format_content_empty():
    assert format_extraction_content([]) == ""
    assert format_extraction_content([{"filename": "x"}]) == ""


def test_format_content_does_not_truncate():
    text = "я" * 1_000_000
    result = format_extraction_content([{"filename": "big.txt", "text": text}])
    assert result.endswith(text)
    assert len(result) == len("--- FILE: big.txt ---\n") + len(text)


def test_build_response_content_is_kept_as_is():
    body = build_chat_response("--- FILE: a ---\nтекст")
    assert body["choices"][0]["message"]["content"] == "--- FILE: a ---\nтекст"
    assert body["model"] == EXTRACTION_MODEL_ID


def test_parse_returns_filename_and_bytes():
    parsed = parse_chat_request(chat_payload("  имя.txt ", b"abc"))
    assert parsed == ChatFile(filename="  имя.txt ", content=b"abc")
