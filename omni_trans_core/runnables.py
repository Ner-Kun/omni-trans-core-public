import logging
import re
import time
import asyncio
import aiohttp
import litellm
import os
import json
import urllib.request
import ast
from .proxy_manager import proxy_manager
import httpx
from PySide6 import QtCore
from openai import OpenAI
from . import settings
from .interfaces import AbstractPromptFormatter, AbstractResponseParser, JobSignals
from .localization_manager import translate

try:
    from ruamel.yaml import YAML
except ImportError:
    YAML = None

logger = logging.getLogger('CORE.runnables')

_litellm_verbose = settings.DEV_MODE_ENABLED and not settings.LITELLM_LOGGING_DISABLED
litellm.set_verbose = _litellm_verbose

class BaseJobRunnable(QtCore.QRunnable):
    def __init__(
        self,
        job_data: dict,
        signals: JobSignals,
        prompt_formatter: AbstractPromptFormatter,
        response_parser: AbstractResponseParser,
    ):
        super().__init__()
        self.job_data = job_data
        self.signals = signals
        self.prompt_formatter = prompt_formatter
        self.response_parser = response_parser

    def run(self):
        raise NotImplementedError

class CustomJobRunnable(BaseJobRunnable):
    async def _run_async_with_proxy(self, final_call_args, custom_provider_params, proxy_url):
        proxy_kwargs = {}
        if proxy_url:
            proxy_kwargs["proxy"] = proxy_url
        async with aiohttp.ClientSession(**proxy_kwargs) as session:
            response = await litellm.acompletion(
                **final_call_args,
                extra_body=custom_provider_params,
                num_retries=0,
                shared_session=session
            )
            return response

    @QtCore.Slot()
    def run(self):
        if not litellm:
            error_msg = translate("runnable.custom.error.library_missing")
            logger.error(f"[LiteLLM] {error_msg}")
            self.signals.job_failed.emit(
                self.job_data, error_msg, "N/A", error_msg, ImportError(error_msg), {}
            )
            return

        job_data = self.job_data
        original_item = job_data["original_item"]
        item_id = original_item["id"]
        generation_params = job_data.get("generation_params") or {}
        provider = job_data.get("provider")
        model_name = job_data.get("model_name")
        api_key = job_data.get("api_key")
        base_url = job_data.get("base_url")
        headers = job_data.get("headers")
        thinking_config = job_data.get("thinking_config", {"mode": "unsupported"})

        if not provider or not model_name:
            error_msg = translate("runnable.custom.error.job_misconfigured")
            logger.error(f"[LiteLLM] {error_msg}")
            self.signals.job_failed.emit(
                self.job_data, error_msg, "N/A", error_msg, None, {}
            )
            return

        provider_for_litellm = "openai" if provider == "openai_compatible" else provider
        if model_name.startswith(f"{provider_for_litellm}/"):
            model_for_litellm = model_name
        else:
            model_for_litellm = f"{provider_for_litellm}/{model_name}"
        start_time = time.monotonic()
        logger.info(
            f"[LiteLLM] Job starting for item '{item_id}' for '{model_for_litellm}'. Using endpoint: {base_url or 'Default'}"
        )

        try:
            messages = self.prompt_formatter.format_prompt(
                item=original_item,
                src_lang=job_data["source_lang"],
                tgt_lang=job_data["target_lang"],
                custom_settings=generation_params,
                is_regeneration=job_data.get("is_regeneration", False),
            )

            defaults = settings.get_default_generation_params()

            standard_litellm_args = {
                "model": model_for_litellm,
                "messages": messages,
                "api_key": api_key,
                "api_base": base_url,
                "headers": headers,
                "timeout": job_data.get("timeout", 600),
                "temperature": generation_params.get(
                    "temperature", defaults["temperature"]
                ),
                "top_p": generation_params.get("top_p", defaults["top_p"]),
                "max_tokens": generation_params.get(
                    "max_output_tokens", defaults["max_output_tokens"]
                ),
                "frequency_penalty": generation_params.get(
                    "frequency_penalty", defaults["frequency_penalty"]
                ),
                "presence_penalty": generation_params.get(
                    "presence_penalty", defaults["presence_penalty"]
                ),
            }

            if not standard_litellm_args.get("api_base"):
                standard_litellm_args.pop("api_base", None)

            custom_provider_params = {}

            if YAML:
                additional_params = job_data.get("additional_params", {})

                include_body_text = additional_params.get(
                    "include_body_params", ""
                ).strip()
                if include_body_text:
                    try:
                        yaml = YAML(typ="safe")
                        parsed_body = yaml.load(include_body_text)
                        if isinstance(parsed_body, dict):
                            custom_provider_params.update(parsed_body)
                            logger.debug(
                                f"[Custom Params] Staged for extra_body: {parsed_body}"
                            )
                        else:
                            logger.warning(
                                "[Custom Params] Parsed include_body_params is not a dictionary, skipping."
                            )
                    except Exception as e:
                        logger.warning(
                            f"[Custom Params] Failed to parse include_body_params YAML/JSON: {e}"
                        )

                exclude_body_text = additional_params.get(
                    "exclude_body_params", ""
                ).strip()
                if exclude_body_text:
                    try:
                        yaml = YAML(typ="safe")
                        parsed_exclude = yaml.load(exclude_body_text)
                        if isinstance(parsed_exclude, list):
                            for key in parsed_exclude:
                                if isinstance(key, str):
                                    standard_litellm_args.pop(key, None)
                            logger.debug(
                                f"[Custom Params] Removed from standard args: {parsed_exclude}"
                            )
                        else:
                            logger.warning(
                                "[Custom Params] Parsed exclude_body_params is not a list, skipping."
                            )
                    except Exception as e:
                        logger.warning(
                            f"[Custom Params] Failed to parse exclude_body_params YAML/JSON: {e}"
                        )

                include_headers_text = additional_params.get(
                    "include_headers", ""
                ).strip()
                if include_headers_text:
                    try:
                        yaml = YAML(typ="safe")
                        parsed_headers = yaml.load(include_headers_text)
                        if isinstance(parsed_headers, dict):
                            if "headers" not in standard_litellm_args or not isinstance(
                                standard_litellm_args["headers"], dict
                            ):
                                standard_litellm_args["headers"] = {}
                            standard_litellm_args["headers"].update(parsed_headers)
                            logger.debug(
                                f"[Custom Params] Added to request headers: {parsed_headers}"
                            )
                        else:
                            logger.warning(
                                "[Custom Params] Parsed include_headers is not a dictionary, skipping."
                            )
                    except Exception as e:
                        logger.warning(
                            f"[Custom Params] Failed to parse include_headers YAML/JSON: {e}"
                        )
            else:
                logger.warning(
                    "ruamel.yaml is not installed. Additional parameters will be ignored."
                )

            should_enable_thinking = thinking_config.get("enabled", True)
            current_mode = thinking_config.get("mode", "unsupported")

            if provider == "gemini":
                if "gemini-3" in model_name.lower():
                    if should_enable_thinking:
                        level = generation_params.get("thinking_level", "high")
                        standard_litellm_args["reasoning_effort"] = (
                            level if level in ("low", "medium", "high") else "high"
                        )
                    else:
                        standard_litellm_args["reasoning_effort"] = "none"
                elif should_enable_thinking:
                    budget = generation_params.get("thinking_budget_value", -1)
                    if isinstance(budget, int):
                        standard_litellm_args["thinking"] = {
                            "type": "enabled",
                            "budget_tokens": budget,
                        }
                    else:
                        standard_litellm_args["reasoning_effort"] = "high"
                else:
                    standard_litellm_args["thinking"] = {
                        "type": "enabled",
                        "budget_tokens": 0,
                    }
            elif current_mode == "command":
                cmd = (
                    thinking_config.get("enable_cmd")
                    if should_enable_thinking
                    else thinking_config.get("disable_cmd")
                )
                if cmd:
                    messages[-1]["content"] = f"{cmd}\n{messages[-1]['content']}"
            elif current_mode == "auto" and should_enable_thinking:
                if provider != "mistral":
                    standard_litellm_args["reasoning_effort"] = "auto"

            final_call_args = {
                k: v for k, v in standard_litellm_args.items() if v is not None
            }
            proxy_url = proxy_manager.get_proxy()
            if proxy_url:
                logger.info(f"[LiteLLM] Using proxy for item '{item_id}': {proxy_url}")

            response = None
            try:
                if proxy_url:
                    response = asyncio.run(
                        self._run_async_with_proxy(final_call_args, custom_provider_params, proxy_url)
                    )
                else:
                    response = litellm.completion(
                        **final_call_args, extra_body=custom_provider_params, num_retries=0
                    )
            except litellm.APIConnectionError as e:
                error_str = str(e)
                if (
                    "pydantic_core.ValidationError" in error_str
                    and "Input should be a valid string" in error_str
                ):
                    logger.warning(
                        "Caught known litellm parsing error for Mistral-like response. Attempting to recover raw response."
                    )
                    try:
                        match = re.search(
                            r"received_args={'response_object': ({.*?}), 'model_response_object'",
                            error_str,
                            re.DOTALL,
                        )
                        if match:
                            response_object_str = match.group(1)
                            raw_response_dict = ast.literal_eval(response_object_str)
                            logger.info(
                                "Successfully recovered raw response from litellm exception."
                            )
                            response = raw_response_dict
                        else:
                            raise e
                    except (json.JSONDecodeError, ValueError) as parse_error:
                        logger.error(
                            f"Failed to parse recovered response from exception: {parse_error}. Failing job."
                        )
                        raise e
                else:
                    raise e

            duration = time.monotonic() - start_time
            final_processed_translation, thinking_text, usage_meta = (
                self.response_parser.parse(response, job_data)
            )
            if thinking_text and not should_enable_thinking:
                conn_name = job_data.get("connection_name", "unknown")
                self.signals.thinking_unexpected.emit(conn_name, model_name)
            prompt_for_inspector = "\n\n".join(
                [f"{msg['role'].capitalize()}: {msg['content']}" for msg in messages]
            )
            proxy_ip = ""
            proxy_used = False
            if proxy_url:
                proxy_used = True
                try:
                    if "://" in proxy_url:
                        host_part = proxy_url.split("://", 1)[1]
                        if "@" in host_part:
                            host_part = host_part.split("@", 1)[1]
                        proxy_ip = host_part.rsplit(":", 1)[0]
                except Exception:
                    proxy_ip = proxy_url
            self.signals.inspector_update.emit(
                model_name,
                prompt_for_inspector,
                final_processed_translation,
                thinking_text,
                usage_meta,
                proxy_ip,
                proxy_used,
            )
            if proxy_url:
                proxy_manager.mark_success(proxy_url)
            self.signals.job_completed.emit(
                job_data,
                final_processed_translation,
                thinking_text,
                usage_meta,
                duration,
            )
    
        except litellm.RateLimitError as e:
            if proxy_url:
                proxy_manager.mark_failed(proxy_url)
            logger.warning(
                f"[LiteLLM] RateLimitError for '{original_item['source_text']}': {e}"
            )
            self.signals.job_failed.emit(
                self.job_data,
                str(e),
                translate("runnable.custom.error.rate_limit_title"),
                translate("runnable.custom.error.rate_limit_text", error=str(e)),
                e,
                {},
            )
        except litellm.Timeout as e:
            if proxy_url:
                proxy_manager.mark_failed(proxy_url)
            logger.warning(
                f"[LiteLLM] Timeout for '{original_item['source_text']}': {e}"
            )
            self.signals.job_failed.emit(
                self.job_data,
                str(e),
                translate("runnable.custom.error.timeout_title"),
                translate("runnable.custom.error.timeout_text", error=str(e)),
                e,
                {},
            )
        except litellm.AuthenticationError as e:
            if proxy_url:
                proxy_manager.mark_failed(proxy_url)
            logger.error(
                f"[LiteLLM] AuthenticationError for '{original_item['source_text']}': {e}"
            )
            self.signals.job_failed.emit(
                self.job_data,
                str(e),
                translate("runnable.custom.error.auth_title"),
                translate("runnable.custom.error.auth_text", error=str(e)),
                e,
                {},
            )
        except litellm.NotFoundError as e:
            if proxy_url:
                proxy_manager.mark_failed(proxy_url)
            logger.error(
                f"[LiteLLM] NotFoundError for '{original_item['source_text']}': {e}"
            )
            self.signals.job_failed.emit(
                self.job_data,
                str(e),
                translate("runnable.custom.error.not_found_title"),
                translate("runnable.custom.error.not_found_text", error=str(e)),
                e,
                {},
            )
        except litellm.BadRequestError as e:
            if proxy_url:
                proxy_manager.mark_failed(proxy_url)
            logger.error(
                f"[LiteLLM] BadRequestError for '{original_item['source_text']}': {e}"
            )
            self.signals.job_failed.emit(
                self.job_data,
                str(e),
                translate("runnable.custom.error.bad_request_title"),
                translate("runnable.custom.error.bad_request_text", error=str(e)),
                e,
                {},
            )
        except litellm.ServiceUnavailableError as e:
            if proxy_url:
                proxy_manager.mark_failed(proxy_url)
            logger.warning(
                f"[LiteLLM] ServiceUnavailableError for '{original_item['source_text']}': {e}"
            )
            self.signals.job_failed.emit(
                self.job_data,
                str(e),
                translate("runnable.custom.error.service_unavailable_title"),
                translate("runnable.custom.error.service_unavailable_text", error=str(e)),
                e,
                {},
            )
        except litellm.APIConnectionError as e:
            if proxy_url:
                proxy_manager.mark_failed(proxy_url)
            logger.warning(
                f"[LiteLLM] APIConnectionError for '{original_item['source_text']}': {e}"
            )
            self.signals.job_failed.emit(
                self.job_data,
                str(e),
                translate("runnable.custom.error.connection_title"),
                translate("runnable.custom.error.connection_text", error=str(e)),
                e,
                {},
            )
        except litellm.APIError as e:
            if proxy_url:
                proxy_manager.mark_failed(proxy_url)
            status_code = getattr(e, 'status_code', None)
            error_msg = str(e)
            if status_code == 410:
                logger.error(
                    f"[LiteLLM] Model gone (410) for '{original_item['source_text']}': {error_msg}"
                )
                self.signals.job_failed.emit(
                    self.job_data,
                    error_msg,
                    translate("runnable.custom.error.model_gone_title"),
                    translate("runnable.custom.error.model_gone_text", error=error_msg),
                    e,
                    {},
                )
            else:
                logger.error(
                    f"[LiteLLM] APIError ({status_code}) for '{original_item['source_text']}': {error_msg}"
                )
                self.signals.job_failed.emit(
                    self.job_data,
                    error_msg,
                    translate("runnable.custom.error.api_error_title"),
                    translate("runnable.custom.error.api_error_text", error=error_msg),
                    e,
                    {},
                )
        except Exception as e:
            if proxy_url:
                proxy_manager.mark_failed(proxy_url)
            logger.error(
                f"[LiteLLM] Unhandled Exception for '{original_item['source_text']}': {e}",
                exc_info=True,
            )
            self.signals.job_failed.emit(
                self.job_data,
                str(e),
                translate("runnable.custom.error.generic_title"),
                translate("runnable.custom.error.generic_text", error=str(e)),
                e,
                {},
            )
    
class FetchModelsWorker(QtCore.QObject):
    finished = QtCore.Signal(list)
    error = QtCore.Signal(str)

    def __init__(self, api_key, base_url, provider_id: str = "openai_compatible"):
        super().__init__()
        self.api_key = api_key
        self.base_url = base_url
        self.provider_id = provider_id

    @QtCore.Slot()
    def run(self):
        try:
            from .proxy_manager import proxy_manager
            import httpx
            proxy_url = proxy_manager.get_proxy()
            http_client = None
            if proxy_url:
                http_client = httpx.Client(proxy=proxy_url)
                logger.info(f"[FetchModels] Using proxy for {self.provider_id}")
            logger.debug(f"[FetchModels] Provider: {self.provider_id}, Base URL: {self.base_url}")

            if self.provider_id == "gemini":
                from .gemini_models import fetch_gemini_models

                self.finished.emit(
                    fetch_gemini_models(self.api_key, proxy_url=proxy_url)
                )
                return

            try:
                client = OpenAI(api_key=self.api_key, base_url=self.base_url, http_client=http_client)
                models_response = client.models.list()
                logger.info(f"[FetchModels] Successfully fetched {len(models_response.data)} models via SDK.")
                self.finished.emit(models_response.data)
                return
            except AttributeError as e:
                if "'list' object has no attribute" in str(e) or "'list' object" in str(e):
                    logger.warning(f"[FetchModels] SDK failed with non-standard format, falling back to direct HTTP request: {e}")
                else:
                    raise
            except Exception as e:
                logger.warning(f"[FetchModels] SDK method failed, trying direct HTTP request: {e}")
            
            base_url = self.base_url.rstrip('/')
            models_url = f"{base_url}/models"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            if http_client:
                response = http_client.get(models_url, headers=headers)
            else:
                with httpx.Client() as temp_client:
                    response = temp_client.get(models_url, headers=headers)
            
            response.raise_for_status()
            raw_data = response.json()
            
            logger.debug(f"[FetchModels] Raw response type: {type(raw_data)}")
            
            if isinstance(raw_data, list):
                models_list = raw_data
                logger.info(f"[FetchModels] Successfully fetched {len(models_list)} models (non-standard list format).")
            elif isinstance(raw_data, dict) and "data" in raw_data:
                models_list = raw_data["data"]
                logger.info(f"[FetchModels] Successfully fetched {len(models_list)} models (standard format via HTTP).")
            else:
                logger.error(f"[FetchModels] Unexpected response format: {type(raw_data)}")
                self.error.emit("API returned unexpected format")
                return
            
            model_objects = []
            for model_data in models_list:
                if isinstance(model_data, dict):
                    model_objects.append(type('Model', (), {
                        'id': model_data.get('id', 'unknown'),
                        'object': model_data.get('object', 'model'),
                        'created': model_data.get('created', 0),
                        'owned_by': model_data.get('owned_by', 'unknown'),
                    })())
                else:
                    model_objects.append(model_data)
            
            self.finished.emit(model_objects)
        except Exception as e:
            logger.error(f"[FetchModels] Failed to fetch models: {e}", exc_info=True)
            self.error.emit(str(e))

class ModelInfoWorker(QtCore.QObject):
    finished = QtCore.Signal(dict)
    error = QtCore.Signal(str)

    def __init__(self, model_name, provider_id, api_key, api_base):
        super().__init__()
        self.full_model_name = model_name
        self.provider_id = provider_id
        self.api_key = api_key
        self.api_base = api_base

    def _get_models_dev_data(self):
        cache_path = settings.MODELS_DEV_CACHE_FILE
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    logger.debug("Using cached models.dev data.")
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(
                    f"Could not read models.dev cache file, will re-fetch. Error: {e}"
                )
        logger.info("Fetching full models.dev registry...")
        try:
            url = "https://models.dev/api.json"
            req = urllib.request.Request(url, headers={"User-Agent": "Omni-Trans-Core"})
            with urllib.request.urlopen(req, timeout=15) as response:
                if response.status == 200:
                    body = response.read().decode("utf-8")
                    data = json.loads(body)
                    with open(cache_path, "w", encoding="utf-8") as f:
                        f.write(body)
                    logger.info("Successfully fetched and cached models.dev registry.")
                    return data
        except Exception as e:
            logger.error(f"Failed to fetch or cache models.dev registry: {e}")
        return None

    def _find_models_in_registry(self, registry, search_term):
        if not registry or not search_term:
            return []
        found_entries = []
        seen_entry_ids = set()
        search_term_lower = search_term.lower()
        for provider_key, provider_data in registry.items():
            if not isinstance(provider_data, dict) or "models" not in provider_data:
                continue
            models_dict = provider_data.get("models", {})
            for model_key, model_info in models_dict.items():
                if not isinstance(model_info, dict):
                    continue
                unique_identifier = (provider_key, model_key)
                if unique_identifier in seen_entry_ids:
                    continue
                model_name = model_info.get("name", "").lower()
                model_id = model_info.get("id", "").lower()
                if (
                    search_term_lower in model_key.lower()
                    or search_term_lower in model_name
                    or search_term_lower in model_id
                ):
                    result_entry = model_info.copy()
                    result_entry["provider_name"] = provider_data.get(
                        "name", provider_key
                    )
                    found_entries.append(result_entry)
                    seen_entry_ids.add(unique_identifier)
        return found_entries

    @QtCore.Slot()
    def run(self):
        try:
            combined_info = {}
            live_data_key = translate("dialog.provider_config.info.live_data_header")
            community_data_key = translate(
                "dialog.provider_config.info.community_data_header"
            )
            static_data_key = translate(
                "dialog.provider_config.info.static_data_header"
            )
            
            litellm_info = None
            try:
                full_model_string = f"{self.provider_id}/{self.full_model_name}"
                litellm_info = litellm.get_model_info(full_model_string)
                if litellm_info:
                    combined_info[live_data_key] = litellm_info
                    logger.info(f"[ModelInfo] Successfully fetched info via litellm for '{full_model_string}'.")
            except Exception as e:
                logger.debug(f"[ModelInfo] litellm method failed: {e}. Trying OpenAI client...")

            if not litellm_info:
                try:
                    client = OpenAI(api_key=self.api_key, base_url=self.api_base)
                    models_response = client.models.list()
                    found_model_obj = next(
                        (m for m in models_response.data if m.id == self.full_model_name),
                        None,
                    )
                    if found_model_obj:
                        combined_info[live_data_key] = found_model_obj.model_dump()
                    else:
                        combined_info[live_data_key] = {
                            "error": translate(
                                "dialog.provider_config.info.error.model_not_found",
                                model_name=self.full_model_name,
                            )
                        }
                except Exception as e:
                    combined_info[live_data_key] = {
                        "error": translate(
                            "dialog.provider_config.info.error.could_not_fetch_live_data",
                            error=str(e),
                        )
                    }
            
            models_dev_registry = self._get_models_dev_data()
            if models_dev_registry:
                clean_model_id = self.full_model_name.split("/")[-1].split(":")[0]
                found_entries = self._find_models_in_registry(
                    models_dev_registry, clean_model_id
                )
                if found_entries:
                    combined_info[community_data_key] = found_entries
                else:
                    combined_info[community_data_key] = {
                        "error": translate(
                            "dialog.provider_config.info.error.model_not_found_in_registry",
                            model_name=clean_model_id,
                        )
                    }
            else:
                combined_info[community_data_key] = {
                    "error": translate(
                        "dialog.provider_config.info.error.could_not_load_registry"
                    )
                }
            
            try:
                full_model_string = f"{self.provider_id}/{self.full_model_name}"
                static_data = litellm.model_cost.get(full_model_string)
                combined_info[static_data_key] = static_data or {
                    "message": translate(
                        "dialog.provider_config.info.message.no_static_data"
                    )
                }
            except Exception as e:
                combined_info[static_data_key] = {
                    "error": translate(
                        "dialog.provider_config.info.error.could_not_fetch_static_data",
                        error=str(e),
                    )
                }
            
            self.finished.emit(combined_info)
        except Exception as e:
            self.error.emit(str(e))
