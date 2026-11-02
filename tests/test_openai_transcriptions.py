"""OpenAI transcription contract without loading speech models."""

from unittest.mock import patch

import pytest

from app.config import settings
from app.transcription import Segment, TranscriptionError, TranscriptionResult

PATH = "/v1/audio/transcriptions"
PUBLIC_ID = "softonit/gigaam-v3-e2e-rnnt"


def post(client, **data):
    return client.post(
        PATH,
        files={"file": ("call.wav", b"audio")},
        data={"model": settings.TRANSCRIPTION_MODEL, **data},
    )


@pytest.fixture
def recognition(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "none")
    monkeypatch.setattr(settings, "ENABLE_TRANSCRIPTION", True)
    result = TranscriptionResult(
        duration=2.34,
        channels=1,
        detected_format="wav",
        segments=[Segment(0.1, 2.2, None, None, "hello")],
    )
    with patch("app.main.transcribe_bytes", return_value=result) as mocked:
        yield mocked


@pytest.mark.parametrize("response_format", ["json", "verbose_json", "text"])
def test_formats(test_client, recognition, response_format):
    response = post(
        test_client,
        response_format=response_format,
        external_id="record-1",
        language="en",
        prompt="ignored",
        temperature="0",
        **{"timestamp_granularities[]": "segment"},
    )
    assert response.status_code == 200
    if response_format == "text":
        assert response.text == "hello"
        assert response.headers["content-type"].startswith("text/plain")
        return
    body = response.json()
    assert body["text"] == "hello"
    assert body["text_status"] == "ok"
    assert body["usage"] == {"type": "duration", "seconds": 2.3}
    if response_format == "verbose_json":
        assert body["segments"] == [
            {
                "id": 0,
                "start": 0.1,
                "end": 2.2,
                "speaker": None,
                "channel": None,
                "text": "hello",
            }
        ]
        assert body["external_id"] == "record-1"
        assert body["language"] == "ru"
        assert body["task"] == "transcribe"


def test_form_defaults(test_client, recognition):
    response = test_client.post(PATH, files={"file": ("call.wav", b"audio")})
    assert response.status_code == 200
    assert response.json()["model"] == PUBLIC_ID
    assert response.json()["language"] == "ru"
    assert recognition.call_args.kwargs["channel_labels"] == ["operator", "client"]


def test_legacy_and_public_ids_give_same_result(test_client, recognition):
    legacy = post(test_client, model="gigaam-v3-e2e-rnnt")
    public = post(test_client, model=PUBLIC_ID)
    assert legacy.status_code == public.status_code == 200
    assert legacy.json() == public.json()
    assert public.json()["model"] == PUBLIC_ID
    assert recognition.call_count == 2


def test_public_id_in_json_and_text_formats(test_client, recognition):
    for response_format in ("json", "text"):
        response = post(test_client, model=PUBLIC_ID, response_format=response_format)
        assert response.status_code == 200


def test_extraction_model_is_not_a_transcription_model(test_client, recognition):
    response = post(test_client, model="softonit/extracttext")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "model_not_found"
    assert error["param"] == "model"
    assert "not a transcription model" in error["message"].lower()
    recognition.assert_not_called()


def test_empty_form_fields_use_defaults(test_client, recognition):
    # Swagger UI шлёт очищенные поля пустыми строками
    response = post(test_client, model="", language="", channel_labels="")
    assert response.status_code == 200
    assert recognition.call_args.kwargs["channel_labels"] == ["operator", "client"]


def test_default_format_is_verbose_json(test_client, recognition):
    response = post(test_client)
    assert response.status_code == 200
    body = response.json()
    assert body["task"] == "transcribe"
    assert [segment["text"] for segment in body["segments"]] == ["hello"]


@pytest.mark.parametrize(
    "fields,status,code,param",
    [
        ({"model": "other"}, 404, "model_not_found", "model"),
        ({"model": "softonit/other"}, 404, "model_not_found", "model"),
        ({"model": "softonit/extracttext"}, 404, "model_not_found", "model"),
        (
            {"response_format": "srt"},
            400,
            "unsupported_response_format",
            "response_format",
        ),
        (
            {"response_format": "vtt"},
            400,
            "unsupported_response_format",
            "response_format",
        ),
    ],
)
def test_rejected_parameters(test_client, recognition, fields, status, code, param):
    response = post(test_client, **fields)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["param"] == param
    recognition.assert_not_called()


def test_missing_file(test_client, recognition):
    response = test_client.post(PATH, data={"model": settings.TRANSCRIPTION_MODEL})
    assert response.status_code == 400
    assert response.json()["error"]["param"] == "file"
    recognition.assert_not_called()


@pytest.mark.parametrize(
    "status,code",
    [
        (413, "audio_too_large"),
        (415, "unsupported_audio_format"),
        (422, "invalid_audio"),
        (503, "service_busy"),
        (504, "request_timeout"),
        (500, "internal_error"),
    ],
)
def test_processing_errors(test_client, recognition, status, code):
    recognition.side_effect = TranscriptionError(
        "failed", status_code=status, retry_after=7
    )
    response = post(test_client)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert response.headers["retry-after"] == "7"


@pytest.mark.parametrize(
    "texts,status",
    [([], "no_speech"), ([""], "unrecognized"), (["hello", ""], "partial")],
)
def test_text_status(test_client, recognition, texts, status):
    recognition.return_value.segments[:] = [
        Segment(0, 1, None, None, text) for text in texts
    ]
    response = post(test_client)
    assert response.status_code == 200
    assert response.json()["text_status"] == status


def test_empty_file(test_client, recognition):
    response = test_client.post(
        PATH,
        files={"file": ("a.wav", b"")},
        data={"model": settings.TRANSCRIPTION_MODEL},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_audio"
    recognition.assert_not_called()


def test_malformed_file_field(test_client, recognition):
    response = test_client.post(
        PATH, data={"model": settings.TRANSCRIPTION_MODEL, "file": "oops"}
    )
    assert response.status_code == 400
    assert "error" in response.json()


@pytest.mark.asyncio
async def test_validation_under_root_path(recognition):
    import httpx

    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, root_path="/service"),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/service/v1/audio/transcriptions",
            data={"file": "invalid", "model": settings.TRANSCRIPTION_MODEL},
        )
    assert response.status_code == 400
    assert "error" in response.json()
    assert "detail" not in response.json()


def test_channel_labels_reach_worker(test_client, recognition):
    response = post(test_client, channel_labels=" client , ,operator")
    assert response.status_code == 200
    assert recognition.call_args.kwargs["channel_labels"] == ["client", "", "operator"]
