import logging
import time
import collections
import random
import litellm
from typing import Any, Optional
from PySide6 import QtCore
from . import settings, utils
from .constants import RPM_COOLDOWN_SECONDS
from .interfaces import AbstractConnectionStrategy, DispatchReadiness
from .runnables import GeminiJobRunnable, CustomJobRunnable
from .interfaces import JobSignals
from .localization_manager import translate

try:
    from google import genai
    from google.genai import errors
    from google.api_core.exceptions import ResourceExhausted
except ImportError:
    genai: Optional[Any] = None
    errors: Optional[Any] = None
    ResourceExhausted: Optional[Any] = None

logger = logging.getLogger('CORE.strategies')

LLM_STRATEGY_DELAY_WARNING_THRESHOLD_PERCENT = 75.0
LLM_STRATEGY_DELAY_MAX_DYNAMIC_MS = 4000
LLM_STRATEGY_DELAY_BASE_MS = 1000
LLM_STRATEGY_DELAY_MAX_JITTER_MS = 500

def _cull_and_count_requests(
    timestamps_deque: collections.deque, window_seconds: int
) -> int:
    if not timestamps_deque:
        return 0
    now = time.monotonic()
    cutoff = now - window_seconds
    while timestamps_deque and timestamps_deque[0] < cutoff:
        timestamps_deque.popleft()
    return len(timestamps_deque)

def _cull_and_sum_tokens(token_deque: collections.deque, window_seconds: int) -> int:
    if not token_deque:
        return 0
    now = time.monotonic()
    cutoff = now - window_seconds
    while token_deque and token_deque[0][0] < cutoff:
        token_deque.popleft()
    return sum(item[1] for item in token_deque)

class GeminiStrategy(AbstractConnectionStrategy):
    def __init__(self, manager, connection_name, global_settings):
        self.manager = manager
        self.name = connection_name
        self.settings = global_settings
        self.api_request_timestamps_per_key = {}
        self.api_key_cooldown_end_times = {}
        self.discovered_rpm_limits = {}

    def get_dispatch_readiness(self) -> DispatchReadiness:
        api_keys = self.settings.get("api_keys", [])
        if not api_keys:
            return DispatchReadiness(False, fatal_reason="failed (no Gemini API keys)")
        if self._find_available_key():
            return DispatchReadiness(True)
        return DispatchReadiness(False, self._next_key_retry_delay_ms())

    def dispatch_job(self, job_data: dict) -> bool:
        selected = self._find_available_key()
        if not selected:
            return False

        key_to_use, key_index = selected
        api_keys = self.settings.get("api_keys", [])
        self.settings["current_api_key_index"] = (key_index + 1) % len(api_keys)

        try:
            job_data["api_key"] = key_to_use
            self._record_api_request_timestamp(key_to_use)
            runnable = self.create_runnable(job_data)
            self.manager.thread_pool.start(runnable)
            self.manager._mark_job_started(job_data)

            logger.debug(
                f"[Gemini] Dispatched job for '{job_data['original_item']['source_text']}'."
            )
        except Exception as e:
            self.manager._handle_job_dispatch_failed(job_data, str(e), e)
            return True

        if self.manager.pending_translation_jobs:
            self.manager.translation_timer.start(100)
        return True

    def _find_available_key(self) -> tuple[str, int] | None:
        api_keys = self.settings.get("api_keys", [])
        if not api_keys:
            return None

        now = time.monotonic()
        num_k = len(api_keys)
        start_idx_rot = self.settings.get("current_api_key_index", 0)
        for i in range(num_k):
            key_idx_chk = (start_idx_rot + i) % num_k
            cand_key = api_keys[key_idx_chk]
            cooldown_end = self.api_key_cooldown_end_times.get(cand_key)
            if cooldown_end and cooldown_end > now:
                continue
            if self._is_rpm_limit_reached_for_key(cand_key):
                continue
            return cand_key, key_idx_chk
        return None

    def _next_key_retry_delay_ms(self) -> int:
        api_keys = self.settings.get("api_keys", [])
        if not api_keys:
            return 1000

        now = time.monotonic()
        wait_times_ms = []
        model = self.settings.get("gemini_model")
        rpm_limit = self._get_effective_rpm_limit_for_model(model)

        for api_key in api_keys:
            cooldown_end = self.api_key_cooldown_end_times.get(api_key)
            if cooldown_end and cooldown_end > now:
                wait_times_ms.append(int((cooldown_end - now) * 1000) + 50)
                continue

            timestamps = self.api_request_timestamps_per_key.get(api_key)
            if timestamps and rpm_limit > 0:
                _cull_and_count_requests(timestamps, 60)
                if len(timestamps) >= rpm_limit:
                    wait_times_ms.append(
                        max(50, int((timestamps[0] + 60 - now) * 1000) + 50)
                    )

        if wait_times_ms:
            next_attempt_delay_ms = min(wait_times_ms)
        else:
            next_attempt_delay_ms = 1000

        logger.warning(
            f"All Gemini keys busy/cooldown. Smart waiting: {next_attempt_delay_ms}ms."
        )
        return next_attempt_delay_ms

    def create_runnable(self, job_data: dict) -> "QtCore.QRunnable":
        signals = JobSignals()
        signals.job_completed.connect(self.manager._handle_job_completed)
        signals.job_failed.connect(self.manager._handle_job_failed)
        signals.inspector_update.connect(self.manager.inspector_update)
        signals.thinking_unexpected.connect(self.manager.thinking_unexpected)
        return GeminiJobRunnable(
            job_data,
            signals,
            self.manager.prompt_formatter,
            self.manager.response_parser,
        )

    def get_status_lines(self) -> dict:
        model_name = self.settings.get("gemini_model", "N/A")
        api_keys = self.settings.get("api_keys", [])
        if not api_keys:
            return {
                "message": translate("strategy.gemini.status.no_api_keys"),
                "color": "#FFA500",
            }
        now = time.monotonic()
        rpm_limit = self._get_effective_rpm_limit_for_model(model_name)
        num_keys = len(api_keys)
        if num_keys == 1:
            key = api_keys[0]
            current_rpm = self._get_current_rpm_for_key(key)
            return {
                "model_name": model_name,
                "limits": [{"name": "RPM", "current": current_rpm, "total": rpm_limit}],
            }
        cooldown_keys = []
        available_key_to_dispatch = None
        start_idx = self.settings.get("current_api_key_index", 0)
        for i in range(num_keys):
            key_idx = (start_idx + i) % num_keys
            key = api_keys[key_idx]
            cooldown_end_time = self.api_key_cooldown_end_times.get(key)
            if cooldown_end_time and cooldown_end_time > now:
                cooldown_keys.append({"key": key, "wait": cooldown_end_time - now})
                continue
            current_rpm = self._get_current_rpm_for_key(key)
            if current_rpm >= rpm_limit:
                cooldown_keys.append({"key": key, "wait": 60})
                continue
            if not available_key_to_dispatch:
                available_key_to_dispatch = {"idx": key_idx, "rpm": current_rpm}
        if not available_key_to_dispatch:
            min_wait_time = (
                min(c["wait"] for c in cooldown_keys) if cooldown_keys else 60
            )
            text = translate(
                "strategy.gemini.status.all_keys_cooldown",
                count=num_keys,
                wait_time=f"{min_wait_time:.0f}",
            )
            return {"message": text, "color": "#FF5555"}
        key_at_start_idx = api_keys[start_idx]
        cooldown_end_at_start = self.api_key_cooldown_end_times.get(key_at_start_idx)
        if cooldown_end_at_start and cooldown_end_at_start > now:
            wait_time = cooldown_end_at_start - now
            text = translate(
                "strategy.gemini.status.next_key_cooldown",
                key_text=f"#{start_idx + 1}",
                wait_time=f"{wait_time:.0f}",
            )
            return {"message": text, "color": "#FFA500"}
        idx = available_key_to_dispatch["idx"]
        rpm = available_key_to_dispatch["rpm"]
        return {
            "model_name": f"{model_name} (Key #{idx + 1})",
            "limits": [{"name": "RPM", "current": rpm, "total": rpm_limit}],
        }

    def on_job_failed(self, job_data: dict, error: Exception, extra_details: dict):
        if ResourceExhausted is None or errors is None:
            return
        is_quota_error = isinstance(
            error, (ResourceExhausted, errors.ClientError)
        ) and ("429" in str(error) or "RESOURCE_EXHAUSTED" in str(error).upper())
        if not is_quota_error:
            return
        used_key = job_data.get("api_key", "UNKNOWN_KEY")
        retry_delay = extra_details.get("retry_delay_seconds")
        cooldown = (retry_delay + 3) if retry_delay else RPM_COOLDOWN_SECONDS
        self.api_key_cooldown_end_times[used_key] = time.monotonic() + cooldown
        logger.info(
            f"Cooling down Gemini key {utils.mask_api_key(used_key)} for {cooldown}s."
        )

    def _get_effective_rpm_limit_for_model(self, model_name: str) -> int:
        return self.discovered_rpm_limits.get(
            model_name,
            self.settings.get("rpm_limit", settings.default_global_settings["rpm_limit"]),
        )

    def _record_api_request_timestamp(self, api_key: str):
        if api_key not in self.api_request_timestamps_per_key:
            self.api_request_timestamps_per_key[api_key] = collections.deque()
        self.api_request_timestamps_per_key[api_key].append(time.monotonic())

    def _get_current_rpm_for_key(self, api_key: str) -> int:
        timestamps = self.api_request_timestamps_per_key.get(api_key)
        return _cull_and_count_requests(timestamps, 60) if timestamps else 0

    def _is_rpm_limit_reached_for_key(self, api_key: str) -> bool:
        model = self.settings.get("gemini_model")
        limit = self._get_effective_rpm_limit_for_model(model)
        return self._get_current_rpm_for_key(api_key) >= limit

    def on_job_completed(self, job_data: dict, usage_metadata: dict):
        pass

    def reset(self):
        pass

class LiteLLMStrategy(AbstractConnectionStrategy):
    def __init__(self, manager, connection_name, connection_settings):
        self.manager = manager
        self.name = connection_name
        self.settings = connection_settings
        self.usage_tracker = {"requests": collections.deque(), "tokens": collections.deque()}
        self.backoff_multiplier = 1.0
        self._pending_job_data: Optional[dict] = None
        self._dispatch_timer = QtCore.QTimer(manager)
        self._dispatch_timer.setSingleShot(True)
        self._dispatch_timer.timeout.connect(self._execute_dispatch)
        self._last_error: Optional[str] = None
        self._last_error_time: float = 0

    def _get_effective_limits(self) -> dict:
        limits = self.settings.get("global_limits", {})
        active_model_id = settings.current_settings.get(
            "active_model_for_connection", {}
        ).get(self.name)
        model_config = next(
            (
                model
                for model in self.settings.get("configured_models", [])
                if model.get("model_id") == active_model_id
            ),
            None,
        )
        if model_config and not model_config.get("limits", {}).get(
            "use_global_limits", True
        ):
            return model_config.get("limits", {})
        return limits

    def _is_rate_limited(self) -> bool:
        limits = self._get_effective_limits()
        if (rpd := limits.get("rpd")) is not None and rpd > 0 and _cull_and_count_requests(
            self.usage_tracker["requests"], 86400
        ) >= rpd:
            return True
        if (rpm := limits.get("rpm")) is not None and rpm > 0 and _cull_and_count_requests(
            self.usage_tracker["requests"], 60
        ) >= rpm:
            return True
        if (tpm := limits.get("tpm")) is not None and tpm > 0 and _cull_and_sum_tokens(
            self.usage_tracker["tokens"], 60
        ) >= tpm:
            return True
        return False

    def _execute_dispatch(self):
        job_data = self._pending_job_data
        if not job_data:
            return

        self._pending_job_data = None

        if not self.manager.is_running():
            return

        try:
            self.usage_tracker["requests"].append(time.monotonic())
            runnable = self.create_runnable(job_data)
            self.manager.thread_pool.start(runnable)
            self.manager._mark_job_started(job_data)

            logger.debug(
                f"[LiteLLM] Dispatched job for '{job_data['original_item']['source_text']}'."
            )
        except Exception as e:
            self.manager._handle_job_dispatch_failed(job_data, str(e), e)
            return

        if self.manager.pending_translation_jobs:
            self.manager.translation_timer.start(100)

    def _calculate_delay_ms(self) -> int:
        limits = self._get_effective_limits()
        rpm_limit = limits.get("rpm")
        tpm_limit = limits.get("tpm")
        rpm_usage_percent = 0
        if rpm_limit and rpm_limit > 0:
            current_rpm = _cull_and_count_requests(self.usage_tracker["requests"], 60)
            rpm_usage_percent = (current_rpm / rpm_limit) * 100
        tpm_usage_percent = 0
        if tpm_limit and tpm_limit > 0:
            current_tpm = _cull_and_sum_tokens(self.usage_tracker["tokens"], 60)
            tpm_usage_percent = (current_tpm / tpm_limit) * 100
        max_usage_percent = max(rpm_usage_percent, tpm_usage_percent)
        dynamic_delay_ms = 0
        if max_usage_percent > LLM_STRATEGY_DELAY_WARNING_THRESHOLD_PERCENT:
            progress_in_warning_zone = (
                max_usage_percent - LLM_STRATEGY_DELAY_WARNING_THRESHOLD_PERCENT
            ) / (100.0 - LLM_STRATEGY_DELAY_WARNING_THRESHOLD_PERCENT)
            dynamic_delay_ms = LLM_STRATEGY_DELAY_MAX_DYNAMIC_MS * min(
                progress_in_warning_zone, 1.0
            )
        base_delay_ms = LLM_STRATEGY_DELAY_BASE_MS + random.uniform(
            0, LLM_STRATEGY_DELAY_MAX_JITTER_MS
        )
        total_delay = base_delay_ms + dynamic_delay_ms
        logger.debug(
            f"Calculated dispatch delay for '{self.name}': {total_delay:.0f}ms (Usage: {max_usage_percent:.1f}%)"
        )
        return int(total_delay)

    def get_dispatch_readiness(self) -> DispatchReadiness:
        if self._dispatch_timer.isActive() or self._pending_job_data:
            logger.debug(
                f"Dispatch for '{self.name}' deferred: Another job is already queued on internal timer."
            )
            return DispatchReadiness(False, 100)
        is_sequential = self.settings.get("wait_for_response", True)
        if is_sequential:
            active_for_connection = self.manager._active_jobs_per_connection.get(
                self.name, 0
            )
            if active_for_connection > 0:
                logger.debug(
                    f"Dispatch for '{self.name}' deferred: 'Wait for response' is ON."
                )
                return DispatchReadiness(False, 100)
        if self._is_rate_limited():
            logger.debug(f"Dispatch for '{self.name}' deferred: Rate limit reached.")
            return DispatchReadiness(False, 1000)
        return DispatchReadiness(True)

    def dispatch_job(self, job_data: dict) -> bool:
        if self._dispatch_timer.isActive() or self._pending_job_data:
            logger.debug(
                f"Dispatch for '{self.name}' refused: Another job is already queued on internal timer."
            )
            return False

        self._pending_job_data = job_data
        if self.settings.get("wait_for_response", True):
            self._execute_dispatch()
        else:
            delay = self._calculate_delay_ms()
            self._dispatch_timer.start(delay)
        return True

    def create_runnable(self, job_data: dict) -> "QtCore.QRunnable":
        signals = JobSignals()
        signals.job_completed.connect(self.manager._handle_job_completed)
        signals.job_failed.connect(self.manager._handle_job_failed)
        signals.inspector_update.connect(self.manager.inspector_update)
        signals.thinking_unexpected.connect(self.manager.thinking_unexpected)
        signals.thinking_mode_discovered.connect(
            self.manager._on_thinking_mode_discovered
        )
        return CustomJobRunnable(
            job_data,
            signals,
            self.manager.prompt_formatter,
            self.manager.response_parser,
        )

    def get_status_lines(self) -> dict:
        limits_data = []
        limits = self._get_effective_limits()
        active_model_id = settings.current_settings.get(
            "active_model_for_connection", {}
        ).get(self.name)
        model_name = "N/A"
        if active_model_id:
            model_name = active_model_id.split("/")[-1]
        if (rpm := limits.get("rpm")) is not None and rpm > 0:
            current = _cull_and_count_requests(self.usage_tracker["requests"], 60)
            limits_data.append({"name": "RPM", "current": current, "total": rpm})
        if (tpm := limits.get("tpm")) is not None and tpm > 0:
            current = _cull_and_sum_tokens(self.usage_tracker["tokens"], 60)
            limits_data.append({"name": "TPM", "current": current, "total": tpm})
        if (rpd := limits.get("rpd")) is not None and rpd > 0:
            current = _cull_and_count_requests(self.usage_tracker["requests"], 86400)
            limits_data.append({"name": "RPD", "current": current, "total": rpd})
        
        result = {"model_name": model_name, "limits": limits_data}
        
        if self._last_error and (time.monotonic() - self._last_error_time) < 60:
            result["last_error"] = self._last_error
            result["color"] = "#FFA500"
        
        if not limits_data and not result.get("last_error"):
            return {"message": translate("strategy.litellm.status.no_limits")}
        
        return result

    def on_job_failed(self, job_data: dict, error: Exception, extra_details: dict):
        error_msg = str(error)
        if len(error_msg) > 100:
            error_msg = error_msg[:100] + "..."
        self._last_error = error_msg
        self._last_error_time = time.monotonic()
        
        if not litellm or not isinstance(error, litellm.RateLimitError):
            return
        self.backoff_multiplier = min(self.backoff_multiplier + 1.0, 10.0)
        delay = 1000 * self.backoff_multiplier
        logger.warning(
            f"LiteLLM RateLimitError for '{self.name}'. Increasing backoff to {self.backoff_multiplier:.1f}x. Delay: {delay:.0f}ms."
        )
        self.manager.translation_timer.start(int(delay))

    def on_job_completed(self, job_data: dict, usage_metadata: dict):
        self.backoff_multiplier = max(1.0, self.backoff_multiplier / 2.0)
        if usage_metadata:
            token_count = usage_metadata.get("total", 0)
            if token_count > 0:
                self.usage_tracker["tokens"].append((time.monotonic(), token_count))

    def reset(self):
        self._dispatch_timer.stop()
        self._pending_job_data = None
