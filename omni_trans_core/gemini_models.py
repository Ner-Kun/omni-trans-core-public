import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger("CORE.gemini_models")

GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GENERATE_CONTENT_METHOD = "generateContent"


@dataclass(frozen=True)
class GeminiModel:
    id: str
    display_name: str
    description: str
    input_token_limit: int | None
    output_token_limit: int | None


def _mask_key(api_key: str) -> str:
    if not api_key:
        return "N/A_KEY"
    if len(api_key) <= 7:
        return "****"
    return f"{api_key[:3]}...{api_key[-4:]}"


def _as_text(value: object, fallback: str = "") -> str:
    return value if isinstance(value, str) else fallback


def _as_token_limit(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _parse_models(payload: object) -> list[GeminiModel]:
    if not isinstance(payload, dict):
        raise RuntimeError("Gemini models response is not a JSON object.")
    raw_models = payload.get("models")
    if not isinstance(raw_models, list):
        raise RuntimeError("Gemini models response has no model list.")

    models: dict[str, GeminiModel] = {}
    for entry in raw_models:
        if not isinstance(entry, dict):
            raise RuntimeError("Gemini models response contains an invalid model entry.")
        methods = entry.get("supportedGenerationMethods")
        if not isinstance(methods, list) or GENERATE_CONTENT_METHOD not in methods:
            continue
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        model_id = name.removeprefix("models/")
        if not model_id:
            continue
        models.setdefault(
            model_id,
            GeminiModel(
                id=model_id,
                display_name=_as_text(entry.get("displayName")) or model_id,
                description=_as_text(entry.get("description")),
                input_token_limit=_as_token_limit(entry.get("inputTokenLimit")),
                output_token_limit=_as_token_limit(entry.get("outputTokenLimit")),
            ),
        )
    return [models[model_id] for model_id in sorted(models)]


def fetch_gemini_models(
    api_key: str,
    *,
    proxy_url: str | None = None,
    timeout: float = 30.0,
    http_client: httpx.Client | None = None,
) -> list[GeminiModel]:
    """Fetch Gemini models that support generateContent.

    The key travels in the x-goog-api-key header, so it never ends up in URLs
    or logs. An injected http_client is used as-is and left open; a client
    created here owns its connection pool and is always closed.
    """
    masked_key = _mask_key(api_key)
    owns_client = http_client is None
    client = http_client
    if client is None:
        client = (
            httpx.Client(proxy=proxy_url, timeout=timeout)
            if proxy_url
            else httpx.Client(timeout=timeout)
        )

    try:
        try:
            response = client.get(
                GEMINI_MODELS_URL,
                headers={"x-goog-api-key": api_key},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Gemini models request for key %s failed with HTTP %s.",
                masked_key,
                exc.response.status_code,
            )
            raise RuntimeError(
                f"Gemini models request failed with HTTP {exc.response.status_code}."
            ) from None
        except httpx.HTTPError as exc:
            logger.error(
                "Gemini models request for key %s failed: %s.",
                masked_key,
                type(exc).__name__,
            )
            raise RuntimeError(
                f"Gemini models request failed: {type(exc).__name__}."
            ) from None

        try:
            payload = response.json()
        except ValueError:
            raise RuntimeError("Gemini models response is not valid JSON.") from None

        models = _parse_models(payload)
        logger.info("Fetched %d Gemini models for key %s.", len(models), masked_key)
        return models
    finally:
        if owns_client:
            client.close()
