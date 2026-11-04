import logging

import httpx
import pytest

import omni_trans_core.gemini_models as gemini_models_module
from omni_trans_core.gemini_models import GeminiModel, fetch_gemini_models

API_KEY = "AIzaSyDummyTestKey-9f3c2b1a"
MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def make_model(
    name: str,
    methods: list[str] | None = None,
    display_name: str | None = None,
    description: str = "",
    input_token_limit: int | None = None,
    output_token_limit: int | None = None,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "name": name,
        "supportedGenerationMethods": ["generateContent"] if methods is None else methods,
    }
    if display_name is not None:
        entry["displayName"] = display_name
    if description:
        entry["description"] = description
    if input_token_limit is not None:
        entry["inputTokenLimit"] = input_token_limit
    if output_token_limit is not None:
        entry["outputTokenLimit"] = output_token_limit
    return entry


def http_status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", MODELS_URL)
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(f"HTTP {status}", request=request, response=response)


class FakeResponse:
    def __init__(
        self,
        payload: object = None,
        error: Exception | None = None,
    ) -> None:
        self._payload = payload
        self._error = error

    def raise_for_status(self) -> None:
        if self._error is not None:
            raise self._error

    def json(self) -> object:
        return self._payload


class FakeClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.close_count = 0

    def get(self, url: str, headers: dict[str, str] | None = None) -> FakeResponse:
        self.calls.append((url, dict(headers or {})))
        return self.response

    def close(self) -> None:
        self.close_count += 1

    @property
    def closed(self) -> bool:
        return self.close_count > 0


def install_recording_client(
    monkeypatch: pytest.MonkeyPatch,
    response: FakeResponse,
) -> list[FakeClient]:
    class RecordingClient(FakeClient):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(response)
            self.kwargs = kwargs
            created.append(self)

    created: list[RecordingClient] = []
    monkeypatch.setattr(gemini_models_module.httpx, "Client", RecordingClient)
    return created


def test_fetch_returns_generate_content_models_sorted():
    payload = {
        "models": [
            make_model(
                "models/gemini-2.5-pro",
                display_name="Gemini 2.5 Pro",
                description="Reasoning model",
                input_token_limit=2_097_152,
                output_token_limit=65_536,
            ),
            make_model("models/text-embedding-004", methods=["embedContent"]),
            make_model(
                "models/gemini-2.5-flash",
                methods=["generateContent", "countTokens"],
                display_name="Gemini 2.5 Flash",
                description="Fast model",
                input_token_limit=1_048_576,
                output_token_limit=65_536,
            ),
            {"name": "models/no-methods"},
        ]
    }

    models = fetch_gemini_models(API_KEY, http_client=FakeClient(FakeResponse(payload)))

    assert models == [
        GeminiModel(
            id="gemini-2.5-flash",
            display_name="Gemini 2.5 Flash",
            description="Fast model",
            input_token_limit=1_048_576,
            output_token_limit=65_536,
        ),
        GeminiModel(
            id="gemini-2.5-pro",
            display_name="Gemini 2.5 Pro",
            description="Reasoning model",
            input_token_limit=2_097_152,
            output_token_limit=65_536,
        ),
    ]


def test_api_key_is_sent_in_header_not_in_url():
    client = FakeClient(FakeResponse({"models": []}))

    fetch_gemini_models(API_KEY, http_client=client)

    assert len(client.calls) == 1
    url, headers = client.calls[0]
    assert url == MODELS_URL
    assert headers == {"x-goog-api-key": API_KEY}
    assert API_KEY not in url


def test_proxy_client_is_created_and_closed(monkeypatch):
    created = install_recording_client(monkeypatch, FakeResponse({"models": []}))

    models = fetch_gemini_models(
        API_KEY,
        proxy_url="http://127.0.0.1:8080",
        timeout=12.5,
    )

    assert models == []
    assert len(created) == 1
    assert created[0].kwargs == {"proxy": "http://127.0.0.1:8080", "timeout": 12.5}
    assert created[0].closed


def test_client_without_proxy_uses_timeout_only(monkeypatch):
    created = install_recording_client(monkeypatch, FakeResponse({"models": []}))

    fetch_gemini_models(API_KEY)

    assert len(created) == 1
    assert created[0].kwargs == {"timeout": 30.0}
    assert created[0].closed


def test_injected_client_is_used_and_not_closed():
    payload = {"models": [make_model("models/gemini-x", display_name="X")]}
    client = FakeClient(FakeResponse(payload))

    models = fetch_gemini_models(API_KEY, http_client=client)

    assert [model.id for model in models] == ["gemini-x"]
    assert len(client.calls) == 1
    assert client.close_count == 0


@pytest.mark.parametrize("status", [401, 429, 500])
def test_http_error_raises_runtime_error_without_key(status):
    client = FakeClient(FakeResponse(error=http_status_error(status)))

    with pytest.raises(RuntimeError) as excinfo:
        fetch_gemini_models(API_KEY, http_client=client)

    message = str(excinfo.value)
    assert str(status) in message
    assert API_KEY not in message


def test_created_client_is_closed_on_http_error(monkeypatch):
    created = install_recording_client(monkeypatch, FakeResponse(error=http_status_error(403)))

    with pytest.raises(RuntimeError):
        fetch_gemini_models(API_KEY, proxy_url="http://127.0.0.1:8080")

    assert len(created) == 1
    assert created[0].closed


def test_duplicate_model_ids_are_deduplicated():
    payload = {
        "models": [
            make_model("models/gemini-x", display_name="First"),
            make_model("models/gemini-x", display_name="Second"),
            make_model("models/gemini-a", display_name="A"),
        ]
    }

    models = fetch_gemini_models(API_KEY, http_client=FakeClient(FakeResponse(payload)))

    assert [model.id for model in models] == ["gemini-a", "gemini-x"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"models": None},
        {"models": "gemini"},
        {"models": ["gemini-2.5-pro"]},
        [],
    ],
)
def test_malformed_payload_raises_runtime_error(payload):
    client = FakeClient(FakeResponse(payload))

    with pytest.raises(RuntimeError) as excinfo:
        fetch_gemini_models(API_KEY, http_client=client)

    assert API_KEY not in str(excinfo.value)


def test_logs_mask_api_key(caplog):
    client = FakeClient(FakeResponse({"models": []}))

    with caplog.at_level(logging.DEBUG, logger="CORE.gemini_models"):
        fetch_gemini_models(API_KEY, http_client=client)

    messages = [record.getMessage() for record in caplog.records]
    assert messages
    assert all(API_KEY not in message for message in messages)
    assert any("..." in message for message in messages)
