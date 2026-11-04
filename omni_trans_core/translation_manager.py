import logging
import collections
from typing import TYPE_CHECKING, TypedDict, NotRequired, cast, Any, Dict
from enum import Enum, auto
from .strategies import GeminiStrategy, LiteLLMStrategy
from PySide6 import QtCore, QtWidgets
from . import settings
from .localization_manager import translate
from .interfaces import TranslatableItem, AbstractPromptFormatter, AbstractResponseParser, UsageMetadata

try:
    import litellm
    from litellm import exceptions as litellm_exceptions
except ImportError:
    litellm = None
    litellm_exceptions = None

if TYPE_CHECKING:
    from .core import CoreApp
    from .strategies import GeminiStrategy, LiteLLMStrategy

logger = logging.getLogger('CORE.translation_manager')

class State(Enum):
    IDLE = auto()
    RUNNING = auto()
    CANCELING = auto()
    STOPPED = auto()

class GenerationParams(TypedDict, total=False):
    enable_model_thinking: bool
    thinking_budget_value: int
    use_content_as_context: bool
    temperature: float
    top_p: float
    max_output_tokens: int
    frequency_penalty: float
    presence_penalty: float

class ThinkingConfig(TypedDict, total=False):
    mode: str
    enable_cmd: str
    disable_cmd: str

class JobData(TypedDict):
    original_item: TranslatableItem
    source_lang: str
    target_lang: str
    is_regeneration: bool
    connection_name: str
    generation_params: GenerationParams
    model_name: str
    provider: str
    api_key: NotRequired[str]
    base_url: NotRequired[str]
    headers: NotRequired[dict[str, str]]
    parsing_rules: NotRequired[dict[str, str]]
    thinking_config: NotRequired[ThinkingConfig]
    timeout: NotRequired[int]
    failover_count: NotRequired[int]

class CustomConnectionProfile(TypedDict):
    name: str
    provider: str
    api_key: str
    base_url: str
    headers: dict[str, str]
    timeout: int
    configured_models: list[dict[str, str | dict[str, str | bool | int | None] | ThinkingConfig]]
    generation_params: GenerationParams

class TranslationManager(QtCore.QObject):
    batch_progress_updated: QtCore.Signal = QtCore.Signal(int, int)
    batch_finished: QtCore.Signal = QtCore.Signal(str)
    graceful_shutdown_initiated: QtCore.Signal = QtCore.Signal(int)
    graceful_shutdown_progress_updated: QtCore.Signal = QtCore.Signal(int)
    item_translated: QtCore.Signal = QtCore.Signal(dict)
    rpm_status_updated: QtCore.Signal = QtCore.Signal(dict)
    inspector_update: QtCore.Signal = QtCore.Signal(str, str, str, str, dict, str, bool)
    model_capability_discovered: QtCore.Signal = QtCore.Signal(str, str)
    thinking_misconfigured = QtCore.Signal(str, str)
    thinking_unexpected = QtCore.Signal(str, str)
    connection_auto_disabled = QtCore.Signal(str)
    
    app: 'CoreApp'
    prompt_formatter: AbstractPromptFormatter
    response_parser: AbstractResponseParser
    thread_pool: QtCore.QThreadPool
    max_api_jobs: int
    pending_translation_jobs: collections.deque[JobData]
    active_translation_jobs: int
    _active_jobs_per_connection: dict[str, int]
    total_jobs_for_progress: int
    completed_jobs_for_progress: int
    _state: State
    strategies: dict[str, 'GeminiStrategy | LiteLLMStrategy']
    models_without_thoughts_support: set[str]
    _thinking_failure_counts: dict[tuple[str, str], int]
    active_connection_name: str | None
    active_connections: list[tuple[str, str]]
    _connection_index: int
    _connection_error_counts: dict[str, int]
    translation_timer: QtCore.QTimer
    rpm_monitor_timer: QtCore.QTimer

    def __init__(
        self,
        app_ref: "CoreApp",
        prompt_formatter: AbstractPromptFormatter,
        response_parser: AbstractResponseParser,
    ):
        super().__init__(app_ref)
        self.app = app_ref
        self.prompt_formatter = prompt_formatter
        self.response_parser = response_parser
        self.thread_pool = app_ref.thread_pool
        total_threads: int = self.thread_pool.maxThreadCount()
        ratio: float = float(
            cast(float, settings.current_settings.get("api_thread_pool_ratio", 0.75))
        )
        self.max_api_jobs = max(1, min(total_threads - 1, int(total_threads * ratio)))
        logger.debug(
            f"ThreadPool configured: Total={total_threads}, API Job Limit={self.max_api_jobs}"
        )
        self.pending_translation_jobs = collections.deque()
        self.active_translation_jobs = 0
        self._active_jobs_per_connection: dict[str, int] = {}
        self.total_jobs_for_progress = 0
        self.completed_jobs_for_progress = 0
        self._state = State.IDLE
        self._thinking_failure_counts: dict[tuple[str, str], int] = {}
        self.strategies = {}
        self.models_without_thoughts_support = set()
        self.active_connection_name = None
        self.active_connections: list[tuple[str, str]] = []
        self._connection_index = 0
        self._connection_error_counts: dict[str, int] = {}
        self.translation_timer = QtCore.QTimer(self)
        self.translation_timer.setSingleShot(True)
        _ = self.translation_timer.timeout.connect(self._dispatch_next_job_to_pool)
        self.rpm_monitor_timer = QtCore.QTimer(self)
        _ = self.rpm_monitor_timer.timeout.connect(
            self.update_rpm_display_and_check_cooldown
        )
        _ = self.inspector_update.connect(self.send_data_to_inspector)

    def reset_batch_state(self) -> None:
        self._state = State.IDLE
        self.translation_timer.stop()
        self.active_translation_jobs = 0
        self._active_jobs_per_connection.clear()
        self.total_jobs_for_progress = 0
        self.completed_jobs_for_progress = 0
        self.pending_translation_jobs.clear()
        for strategy in self.strategies.values():
            if hasattr(strategy, "reset"):
                strategy.reset()
        logger.debug(
            "TranslationManager reset to IDLE state and all connection strategies have been cleared."
        )

    @QtCore.Slot(str, str, str)
    def _on_thinking_mode_discovered(
        self, connection_name: str, model_id: str, mode: str
    ) -> None:
        for conn in settings.current_settings.get("custom_connections", []):
            if conn.get("name") == connection_name:
                for model in conn.get("configured_models", []):
                    if model.get("model_id") == model_id:
                        if "thinking_config" not in model:
                            model["thinking_config"] = {}
                        model["thinking_config"]["mode"] = mode
                        logger.info(
                            f"Discovered and saved thinking mode for '{model_id}': {mode}"
                        )
                        settings.save_settings()
                        if mode == "unsupported":
                            full_model_id_for_signal = (
                                f"{conn.get('provider')}/{model_id}"
                            )
                            self.model_capability_discovered.emit(
                                full_model_id_for_signal, "thoughts_unsupported"
                            )
                        return

    def _initialize_strategies(self) -> None:
        self.strategies.clear()
        self.strategies["Google Gemini"] = GeminiStrategy(
            self, "Google Gemini", settings.current_settings
        )
        for conn_settings in settings.current_settings.get("custom_connections", []):
            name = conn_settings.get("name")
            if name:
                self.strategies[name] = LiteLLMStrategy(self, name, conn_settings)
        logger.debug(f"Initialized {len(self.strategies)} translation providers.")

    @QtCore.Slot(str)
    def set_active_connection(self, connection_name: str) -> None:
        if self.active_connection_name != connection_name:
            logger.debug(f"Active connection has been set to: '{connection_name}'")
            self.active_connection_name = connection_name
            self.update_rpm_display_and_check_cooldown()

    @QtCore.Slot(list)
    def set_active_connections(self, connections: list[tuple[str, str]]) -> None:
        """Set multiple active connections for parallel translation."""
        self.active_connections = connections
        self._connection_index = 0
        self._connection_error_counts = {conn: 0 for conn, _ in connections}
        logger.info(f"Active connections set to: {connections}")
        self.update_rpm_display_and_check_cooldown()

    @QtCore.Slot(str, str, str, str, dict)
    def send_data_to_inspector(
        self,
        model_name: str,
        prompt: str,
        final_translation: str,
        thinking_text: str,
        usage_metadata: Dict[str, int],
    ) -> None:
        usage_metadata_typed: UsageMetadata = cast(
            UsageMetadata, cast(object, usage_metadata)
        )
        inspector = self.app.model_inspector_window
        if inspector and inspector.isVisible():
            logger.debug("Updating inspector with data")
            inspector.update_data(
                model_name,
                prompt,
                final_translation,
                thinking_text,
                usage_metadata_typed,
            )
        else:
            logger.debug("Inspector window not available or not visible")

    def _finalize_batch(self, reason: str) -> None:
        if self._state == State.IDLE:
            return
        logger.debug(f"Finalizing batch. Reason: {reason}. State: {self._state.name}")
        self.batch_finished.emit(reason)
        self.reset_batch_state()

    def is_running(self) -> bool:
        return self._state == State.RUNNING

    def _mark_job_started(self, job_data: JobData) -> None:
        self.active_translation_jobs += 1
        connection_name = job_data.get("connection_name")
        if connection_name:
            self._active_jobs_per_connection[connection_name] = (
                self._active_jobs_per_connection.get(connection_name, 0) + 1
            )

    def _mark_job_finished(self, job_data: JobData) -> None:
        if self.active_translation_jobs <= 0:
            logger.warning("active_translation_jobs underflow prevented.")
            self.active_translation_jobs = 0
        else:
            self.active_translation_jobs -= 1

        connection_name = job_data.get("connection_name")
        if not connection_name:
            return

        current = self._active_jobs_per_connection.get(connection_name, 0)
        if current <= 1:
            self._active_jobs_per_connection.pop(connection_name, None)
        else:
            self._active_jobs_per_connection[connection_name] = current - 1

    def _pop_pending_job_at(self, index: int) -> JobData:
        self.pending_translation_jobs.rotate(-index)
        job_data = self.pending_translation_jobs.popleft()
        self.pending_translation_jobs.rotate(index)
        return job_data

    def _handle_job_dispatch_failed(
        self,
        job_data: JobData,
        error_text: str,
        exception_obj: Exception,
    ) -> None:
        exc_info = (type(exception_obj), exception_obj, exception_obj.__traceback__)
        logger.error(
            "Dispatch failed before job start: %s", error_text, exc_info=exc_info
        )
        self.completed_jobs_for_progress += 1
        self.batch_progress_updated.emit(
            self.completed_jobs_for_progress,
            self.total_jobs_for_progress,
        )
        if self._state == State.RUNNING:
            if self.pending_translation_jobs:
                self.translation_timer.start(100)
            elif self.active_translation_jobs == 0:
                self._finalize_batch("completed with dispatch errors")

    def _handle_job_completed(
        self,
        job_data: JobData,
        final_processed_translation: str,
        thinking_text_output: str,
        usage_metadata: UsageMetadata,
        _duration: float,
    ) -> None:
        if self._state in (State.IDLE, State.STOPPED):
            return
        self._mark_job_finished(job_data)
        self.completed_jobs_for_progress += 1
        original_item = job_data["original_item"]
        item_id = original_item["id"]
        source_text = original_item["source_text"]
        source_lang = job_data["source_lang"]
        target_lang = job_data["target_lang"]
        connection_name = job_data.get("connection_name")
        strategy = self.strategies.get(connection_name) if connection_name else None
        if strategy:
            job_data_dict = dict(job_data)
            usage_metadata_dict = dict(usage_metadata) if usage_metadata else {}
            strategy.on_job_completed(job_data_dict, usage_metadata_dict)
            count: int = int(settings.current_settings.get("ux_t_count", 0))
            cast(dict[str, Any], settings.current_settings)["ux_t_count"] = count + 1
        
        if connection_name and connection_name in self._connection_error_counts:
            self._connection_error_counts[connection_name] = 0
        logger.info(
            f"Job completed for '{item_id}'. Cmp/Tot: {self.completed_jobs_for_progress}/{self.total_jobs_for_progress}. Act: {self.active_translation_jobs}. State: {self._state.name}"
        )
        self.app.cache_manager.update_cache(
            source_text, final_processed_translation, source_lang, target_lang
        )
        update_data: dict[str, str | None] = {
            "item_id": item_id,
            "final_translation": final_processed_translation,
        }
        self.item_translated.emit(update_data)
        if job_data["generation_params"].get("enable_model_thinking", False):
            model_key = (job_data.get("connection_name"), job_data.get("model_name"))
            if not thinking_text_output:
                self._thinking_failure_counts[model_key] = (
                    self._thinking_failure_counts.get(model_key, 0) + 1
                )
                threshold = settings.current_settings.get(
                    "thinking_failure_threshold", 3
                )
                if self._thinking_failure_counts[model_key] >= threshold:
                    self.thinking_misconfigured.emit(model_key[0], model_key[1])
                    self._thinking_failure_counts[model_key] = 0
            elif model_key in self._thinking_failure_counts:
                self._thinking_failure_counts[model_key] = 0
        self.batch_progress_updated.emit(
            self.completed_jobs_for_progress, self.total_jobs_for_progress
        )
        if self._state == State.RUNNING:
            if self.pending_translation_jobs:
                self.translation_timer.start(100)
            elif self.active_translation_jobs == 0:
                self._finalize_batch("completed")
        elif self._state == State.CANCELING:
            if self.app.progress_dialog:
                self.app.progress_dialog.set_label_text(
                    f"Finishing {self.active_translation_jobs} active request(s)..."
                )
            if self.active_translation_jobs == 0:
                self._finalize_batch("cancelled")

    def _handle_job_failed(
        self,
        job_data: JobData,
        _error_str: str,
        _t: str,
        _f: str,
        exception_obj: Exception,
        extra_details: Dict[str, int] | None = None,
    ) -> None:
        extra_details = extra_details or {}
        if self._state in (State.IDLE, State.STOPPED):
            return
        self._mark_job_finished(job_data)
        item_id: str = job_data["original_item"]["id"]
        logger.warning(
            f"Job failed for '{item_id}'. Error: {_error_str}. Type: {_t}. Details: {_f}. Cmp/Tot: {self.completed_jobs_for_progress}/{self.total_jobs_for_progress}. Act: {self.active_translation_jobs}. State: {self._state.name}"
        )
        connection_name = job_data.get("connection_name")
        strategy = self.strategies.get(connection_name) if connection_name else None
        if strategy:
            job_data_dict = dict(job_data)
            logger.debug(
                f"Converting JobData to dict for strategy.on_job_failed. Item ID: {item_id}"
            )
            strategy.on_job_failed(job_data_dict, exception_obj, extra_details)
        is_retriable = False
        if litellm and litellm_exceptions:
            if hasattr(exception_obj, 'status_code'):
                status_code = exception_obj.status_code
                if status_code == 410:
                    is_retriable = False
                    logger.info(f"Model is gone (410) for '{item_id}'. Not retrying.")
                else:
                    is_retriable = litellm._should_retry(status_code)
            if not is_retriable:
                is_retriable = isinstance(
                    exception_obj,
                    (litellm_exceptions.RateLimitError, litellm_exceptions.Timeout),
                )
        
        if self._state == State.RUNNING and self.active_connections and connection_name:
            failover_count = job_data.get("failover_count", 0)
            max_failovers = len(self.active_connections) - 1
            
            if failover_count < max_failovers:
                other_connections = [
                    (conn, model) for conn, model in self.active_connections 
                    if conn != connection_name
                ]
                if other_connections:
                    next_conn, next_model = other_connections[0]
                    original_item = job_data["original_item"]
                    source_lang = job_data["source_lang"]
                    target_lang = job_data["target_lang"]
                    is_regeneration = job_data["is_regeneration"]
                    new_job_data = self._build_job_data_for_connection(
                        next_conn, next_model, original_item, source_lang, target_lang, is_regeneration
                    )
                    if new_job_data:
                        new_job_data["failover_count"] = failover_count + 1
                        self.pending_translation_jobs.append(new_job_data)
                        logger.info(f"Failover: Re-queueing job '{item_id}' from '{connection_name}' to '{next_conn}' (attempt {failover_count + 1}/{max_failovers}).")
                        self.translation_timer.start(100)
                        return
            else:
                logger.warning(f"Failover limit reached for job '{item_id}'. All connections tried.")
        
        if self._state == State.RUNNING and is_retriable:
            self.pending_translation_jobs.append(job_data)
            logger.info(f"Retriable error for '{item_id}'. Re-queueing job.")
            if not self.translation_timer.isActive():
                self.translation_timer.start(100)
        else:
            self.completed_jobs_for_progress += 1
            self.batch_progress_updated.emit(
                self.completed_jobs_for_progress, self.total_jobs_for_progress
            )
        
        if connection_name and connection_name in self._connection_error_counts:
            self._connection_error_counts[connection_name] += 1
            if self._connection_error_counts[connection_name] >= 3:
                self.active_connections = [
                    (c, m) for c, m in self.active_connections if c != connection_name
                ]
                self._connection_error_counts.pop(connection_name, None)
                self.connection_auto_disabled.emit(connection_name)
                logger.warning(
                    f"Connection '{connection_name}' auto-disabled after 3 consecutive errors."
                )
        if self._state == State.RUNNING:
            if self.pending_translation_jobs and not self.translation_timer.isActive():
                self.translation_timer.start(100)
            elif not self.pending_translation_jobs and self.active_translation_jobs == 0:
                self._finalize_batch("completed with errors")
        elif self._state == State.CANCELING:
            if self.app.progress_dialog:
                self.app.progress_dialog.set_label_text(
                    f"Finishing {self.active_translation_jobs} active request(s)..."
                )
            if self.active_translation_jobs == 0:
                self._finalize_batch("cancelled with errors")

    def update_rpm_display_and_check_cooldown(self) -> None:
        if self.active_connections:
            connections_data = []
            for conn_name, _ in self.active_connections:
                strategy = self.strategies.get(conn_name)
                if strategy:
                    status = strategy.get_status_lines()
                    connections_data.append({
                        "name": conn_name,
                        "status": status,
                    })
            if connections_data:
                self.rpm_status_updated.emit({"connections": connections_data})
            else:
                self.rpm_status_updated.emit({
                    "message": translate("widget.rpm_status.no_active_connections"),
                    "color": "#f1fa8c",
                })
            if self.pending_translation_jobs and not self.translation_timer.isActive():
                self._dispatch_next_job_to_pool()
            return

        active_strategy = (
            self.strategies.get(self.active_connection_name)
            if self.active_connection_name
            else None
        )
        if active_strategy:
            status_data = active_strategy.get_status_lines()
            self.rpm_status_updated.emit(status_data)
        else:
            self.rpm_status_updated.emit({
                "message": translate("widget.rpm_status.select_model"),
                "color": "#FFFFFF",
            })
        if self.pending_translation_jobs and not self.translation_timer.isActive():
            self._dispatch_next_job_to_pool()

    def apply_rpm_settings_effects(self) -> None:
        self._initialize_strategies()
        update_interval: int = settings.current_settings.get(
            "rpm_monitor_update_interval_ms", 1000
        )
        if self.rpm_monitor_timer.isActive():
            self.rpm_monitor_timer.stop()
        self.rpm_monitor_timer.start(update_interval)
        self.update_rpm_display_and_check_cooldown()

    def _dispatch_next_job_to_pool(self) -> None:
        if not self.pending_translation_jobs:
            return
        if not self.app.progress_dialog:
            return
        if self.active_translation_jobs >= self.max_api_jobs:
            logger.debug(
                f"API job dispatch deferred: limit reached ({self.active_translation_jobs}/{self.max_api_jobs})"
            )
            return
        retry_delay_ms: int | None = None
        pending_count = len(self.pending_translation_jobs)

        for index in range(pending_count):
            job_data = self.pending_translation_jobs[index]
            connection_name = job_data.get("connection_name")
            strategy = self.strategies.get(connection_name) if connection_name else None

            if not strategy:
                logger.error(
                    f"No dispatch strategy found for connection '{connection_name}'."
                )
                self._finalize_batch(f"failed (no strategy: {connection_name})")
                return

            readiness = strategy.get_dispatch_readiness()

            if readiness.fatal_reason:
                logger.error(
                    f"Dispatch strategy '{connection_name}' is not usable: {readiness.fatal_reason}"
                )
                self._finalize_batch(readiness.fatal_reason)
                return

            if not readiness.ready:
                retry_delay_ms = (
                    readiness.retry_delay_ms
                    if retry_delay_ms is None
                    else min(retry_delay_ms, readiness.retry_delay_ms)
                )
                continue

            selected_job = self._pop_pending_job_at(index)
            if not strategy.dispatch_job(selected_job):
                self._handle_job_dispatch_failed(
                    selected_job,
                    "Strategy refused job after reporting ready and did not consume it.",
                    RuntimeError("dispatch_job returned False"),
                )
            return

        if retry_delay_ms is not None and self.pending_translation_jobs:
            self.translation_timer.start(max(50, retry_delay_ms))

    def start_translation_batch(
        self,
        items_to_translate: list[TranslatableItem],
        _op_name: str = "Translating",
        target_lang: str = "",
        force_regen: bool = False,
    ) -> int:
        if self._state != State.IDLE:
            logger.warning(
                f"TranslationManager is not IDLE (state: {self._state.name}). Ignoring start request."
            )
            return 0
        
        if not self.active_connections and not self.active_connection_name:
            _ = QtWidgets.QMessageBox.information(
                self.app,
                translate("manager.no_connection_selected.title"),
                translate("manager.no_connection_selected.text"),
            )
            return 0
        prepared_jobs = self.prepare_jobs(items_to_translate, target_lang, force_regen)
        if not prepared_jobs:
            if not force_regen:
                _ = QtWidgets.QMessageBox.information(
                    self.app,
                    translate("manager.already_translated.title"),
                    translate("manager.already_translated.text"),
                )
            return 0
        self._state = State.RUNNING
        self.pending_translation_jobs.extend(prepared_jobs)
        self.total_jobs_for_progress = len(prepared_jobs)
        self.completed_jobs_for_progress = 0
        logger.info(
            f"Starting new batch of {self.total_jobs_for_progress} jobs. State changed to RUNNING."
        )
        self.translation_timer.start(0)
        return self.total_jobs_for_progress

    def cancel_batch_translation(self, silent: bool = False) -> None:
        if self._state == State.RUNNING:
            self._state = State.CANCELING
            if not silent:
                logger.warning(
                    "Graceful shutdown initiated. State changed to CANCELING."
                )
            self.pending_translation_jobs.clear()
            if self.app.progress_dialog:
                self.app.progress_dialog.set_label_text(
                    f"Finishing {self.active_translation_jobs} active request(s)..."
                )
                self.app.progress_dialog.set_button_text("Cancel All")
            if self.active_translation_jobs == 0:
                self._finalize_batch("cancelled")
        elif self._state == State.CANCELING:
            self._state = State.STOPPED
            if not silent:
                logger.warning("Hard cancel initiated. State changed to STOPPED.")
            self._finalize_batch("stopped")

    def reset_state(self) -> None:
        self.cancel_batch_translation(silent=True)
        self._initialize_strategies()
        logger.debug("TranslationManager state has been reset.")
    
    def _build_job_data_for_connection(
        self,
        conn_name: str,
        model_name: str,
        item: TranslatableItem,
        src_lang: str,
        tgt_lang: str,
        force_regen: bool,
    ) -> dict[str, Any] | None:
        
        active_model_for_connection = settings.current_settings.get("active_model_for_connection", {})
        if conn_name in active_model_for_connection:
            model_name = active_model_for_connection[conn_name]
        
        custom_connections = cast(
            list[CustomConnectionProfile],
            settings.current_settings.get("custom_connections", []),
        )
        profile = next(
            (c for c in custom_connections if c.get("name") == conn_name),
            None,
        )
        if not profile:
            return None
        model_config = next(
            (
                m
                for m in profile.get("configured_models", [])
                if m.get("model_id") == model_name
            ),
            None,
        )
        if not model_config:
            if not profile.get("configured_models"):
                return None
            model_config = profile["configured_models"][0]
            model_name = model_config.get("model_id", model_name)
        job_data: dict[str, Any] = {
            "provider": profile.get("provider"),
            "connection_name": conn_name,
            "model_name": model_name,
            "generation_params": model_config.get("generation_params", profile.get("generation_params")),
            "thinking_config": model_config.get(
                "thinking_config",
                {"mode": "unknown", "enabled": True, "enable_cmd": "", "disable_cmd": ""},
            ),
            "timeout": profile.get("timeout", 600),
            "original_item": item,
            "source_lang": src_lang,
            "target_lang": tgt_lang,
            "is_regeneration": force_regen,
            "failover_count": 0,
        }
        if profile.get("api_key"):
            job_data["api_key"] = profile.get("api_key")
        if profile.get("base_url"):
            job_data["base_url"] = profile.get("base_url")
        if profile.get("headers"):
            job_data["headers"] = profile.get("headers")
        if model_config.get("parsing_rules"):
            job_data["parsing_rules"] = model_config.get("parsing_rules")
        if model_config.get("additional_params"):
            job_data["additional_params"] = model_config.get("additional_params")
        return job_data

    def prepare_jobs(
        self, items: list[TranslatableItem], tgt_lang: str, force_regen: bool = False
    ) -> list[JobData]:
        jobs: list[dict[str, Any]] = []
        src_lang = settings.current_settings.get("selected_source_language")
        if not all([tgt_lang, src_lang]):
            _ = QtWidgets.QMessageBox.critical(
                self.app,
                translate("manager.language_error.title"),
                translate("manager.language_error.text"),
            )
            return cast(list[JobData], jobs)

        if self.active_connections:
            custom_connections = cast(
                list[CustomConnectionProfile],
                settings.current_settings.get("custom_connections", []),
            )
            item_idx = 0
            for item in items:
                if not force_regen and self.app.cache_manager.get_from_cache(
                    item["source_text"], cast(str, src_lang), tgt_lang
                ):
                    continue
                conn_name, model_name = self.active_connections[
                    item_idx % len(self.active_connections)
                ]
                item_idx += 1
                job_data = self._build_job_data_for_connection(
                    conn_name, model_name, item, cast(str, src_lang), tgt_lang, force_regen
                )
                if job_data and "failover_count" not in job_data:
                    job_data["failover_count"] = 0
                if job_data:
                    model_id_for_check = f"{job_data['provider']}/{job_data['model_name']}"
                    if model_id_for_check in self.models_without_thoughts_support:
                        job_gen_params = job_data["generation_params"].copy()
                        job_gen_params["enable_model_thinking"] = False
                        job_data["generation_params"] = job_gen_params
                    jobs.append(job_data)
            return cast(list[JobData], jobs)

        active_connection_name = settings.current_settings.get("active_connection_name")
        base_job_data: dict[str, Any] | None = None
        if active_connection_name == "Google Gemini":
            active_models: dict[str, str] = settings.current_settings.get(
                "active_model_for_connection", {}
            )
            gemini_model_name = active_models.get(
                "Google Gemini", settings.current_settings.get("gemini_model")
            )
            base_job_data = {
                "provider": "gemini",
                "connection_name": "Google Gemini",
                "model_name": gemini_model_name,
                "generation_params": settings.current_settings.get(
                    "gemini_generation_params"
                ),
            }
        
        else:
            custom_connections = cast(
                list[CustomConnectionProfile],
                settings.current_settings.get("custom_connections", []),
            )
            profile = next(
                (
                    c
                    for c in custom_connections
                    if c.get("name") == active_connection_name
                ),
                None,
            )
            if not profile:
                return cast(list[JobData], jobs)
            active_model_id = settings.current_settings.get(
                "active_model_for_connection", {}
            ).get(active_connection_name)
            model_config = next(
                (
                    m
                    for m in profile.get("configured_models", [])
                    if m.get("model_id") == active_model_id
                ),
                None,
            )
            if not model_config:
                if not profile.get("configured_models"):
                    return cast(list[JobData], jobs)
                model_config = profile["configured_models"][0]
            base_job_data = {
                "provider": profile.get("provider"),
                "connection_name": active_connection_name,
                "model_name": model_config.get("model_id"),
                "generation_params": model_config.get("generation_params", profile.get("generation_params")),
                "thinking_config": model_config.get(
                    "thinking_config",
                    {"mode": "unknown", "enabled": True, "enable_cmd": "", "disable_cmd": ""},
                ),
                "timeout": profile.get("timeout", 600),
            }
            if profile.get("api_key"):
                base_job_data["api_key"] = profile.get("api_key")
            if profile.get("base_url"):
                base_job_data["base_url"] = profile.get("base_url")
            if profile.get("headers"):
                base_job_data["headers"] = profile.get("headers")
            if model_config.get("parsing_rules"):
                base_job_data["parsing_rules"] = model_config.get("parsing_rules")
            if model_config.get("additional_params"):
                base_job_data["additional_params"] = model_config.get(
                    "additional_params"
                )
                logger.debug(
                    f"Loaded additional_params for job: {base_job_data['additional_params']}"
                )
        if not (
            base_job_data
            and base_job_data.get("provider")
            and base_job_data.get("model_name")
        ):
            _ = QtWidgets.QMessageBox.warning(
                self.app,
                translate("manager.incomplete_connection.title"),
                translate(
                    "manager.incomplete_connection.text",
                    connection_name=active_connection_name,
                ),
            )
            return cast(list[JobData], jobs)
        model_id_for_check = (
            f"{base_job_data['provider']}/{base_job_data['model_name']}"
        )
        for item in items:
            if not force_regen and self.app.cache_manager.get_from_cache(
                item["source_text"], cast(str, src_lang), tgt_lang
            ):
                continue
            job_data_dict: dict[str, Any] = {
                **base_job_data,
                "original_item": item,
                "source_lang": cast(str, src_lang),
                "target_lang": tgt_lang,
                "is_regeneration": force_regen,
                "failover_count": 0,
            }
            if model_id_for_check in self.models_without_thoughts_support:
                job_gen_params = job_data_dict["generation_params"].copy()
                job_gen_params["enable_model_thinking"] = False
                job_data_dict["generation_params"] = job_gen_params
            jobs.append(job_data_dict)
        return cast(list[JobData], jobs)
