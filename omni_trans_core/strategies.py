import logging
import time
import collections
import random
import litellm
from typing import Optional
from PySide6 import QtCore
from . import settings
from .interfaces import AbstractConnectionStrategy, DispatchReadiness
from .key_pool import KeyPool
from .runnables import CustomJobRunnable
from .interfaces import JobSignals
from .localization_manager import translate

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

class LiteLLMStrategy(AbstractConnectionStrategy):
    def __init__(self, manager, connection_name, connection_settings):
        self.manager = manager
        self.name = connection_name
        self.settings = connection_settings
        keys = connection_settings.get("api_keys") or []
        if not keys and connection_settings.get("api_key"):
            keys = [connection_settings["api_key"]]
        limits = connection_settings.get("global_limits", {}) or {}
        self.key_pool = KeyPool(keys, rpm_limit=limits.get("rpm"))
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
        # With multiple keys the pool enforces RPM per key, so the
        # connection-level counter must not stop rotation early.
        if len(self.key_pool.keys) <= 1:
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

        if self.key_pool.has_keys:
            api_key = self.key_pool.next_key()
            if api_key is None:
                self._pending_job_data = job_data
                self._dispatch_timer.start(self.key_pool.next_retry_delay_ms())
                return
            job_data["api_key"] = api_key
            self.key_pool.record_request(api_key)

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
        if self.key_pool.has_keys and self.key_pool.stats()["available"] == 0:
            logger.debug(f"Dispatch for '{self.name}' deferred: all API keys busy.")
            return DispatchReadiness(False, self.key_pool.next_retry_delay_ms())
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
        api_key = job_data.get("api_key")
        if api_key:
            self.key_pool.mark_failed(api_key)
        self.backoff_multiplier = min(self.backoff_multiplier + 1.0, 10.0)
        delay = 1000 * self.backoff_multiplier
        logger.warning(
            f"LiteLLM RateLimitError for '{self.name}'. Increasing backoff to {self.backoff_multiplier:.1f}x. Delay: {delay:.0f}ms."
        )
        self.manager.translation_timer.start(int(delay))

    def on_job_completed(self, job_data: dict, usage_metadata: dict):
        api_key = job_data.get("api_key")
        if api_key:
            self.key_pool.mark_success(api_key)
        self.backoff_multiplier = max(1.0, self.backoff_multiplier / 2.0)
        if usage_metadata:
            token_count = usage_metadata.get("total", 0)
            if token_count > 0:
                self.usage_tracker["tokens"].append((time.monotonic(), token_count))

    def reset(self):
        self._dispatch_timer.stop()
        self._pending_job_data = None
