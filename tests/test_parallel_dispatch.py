import time
from types import SimpleNamespace

import pytest
from PySide6 import QtCore

import omni_trans_core.translation_manager as translation_manager_module
from omni_trans_core import settings
from omni_trans_core.interfaces import DispatchReadiness
from omni_trans_core.strategies import LiteLLMStrategy
from omni_trans_core.translation_manager import State, TranslationManager


class FakeThreadPool:
    def maxThreadCount(self) -> int:
        return 4


class FakeCacheManager:
    def __init__(self) -> None:
        self.updates = []

    def update_cache(self, *args) -> None:
        self.updates.append(args)

    def get_from_cache(self, *args):
        return None


class FakeApp(QtCore.QObject):
    def __init__(self) -> None:
        super().__init__()
        self.thread_pool = FakeThreadPool()
        self.progress_dialog = object()
        self.cache_manager = FakeCacheManager()
        self.model_inspector_window = None


class FakeStrategy:
    def __init__(
        self,
        readiness: DispatchReadiness,
        consume_job: bool = True,
    ) -> None:
        self.readiness = readiness
        self.consume_job = consume_job
        self.dispatched_jobs = []
        self.reset_called = False

    def get_dispatch_readiness(self) -> DispatchReadiness:
        return self.readiness

    def dispatch_job(self, job_data: dict) -> bool:
        if self.consume_job:
            self.dispatched_jobs.append(job_data)
        return self.consume_job

    def get_status_lines(self) -> dict:
        return {}

    def on_job_failed(self, job_data: dict, error: Exception, extra_details: dict):
        pass

    def on_job_completed(self, job_data: dict, usage_metadata: dict):
        pass

    def reset(self) -> None:
        self.reset_called = True


@pytest.fixture
def manager(qapp):
    app = FakeApp()
    manager = TranslationManager(app, object(), object())
    yield manager
    manager.reset_batch_state()
    manager.rpm_monitor_timer.stop()


def make_job(connection_name: str, item_id: str | None = None) -> dict:
    item_id = item_id or f"item-{connection_name}"
    return {
        "original_item": {
            "id": item_id,
            "source_text": f"source-{item_id}",
            "context": None,
            "original_data": {},
        },
        "source_lang": "en",
        "target_lang": "uk",
        "is_regeneration": False,
        "connection_name": connection_name,
        "generation_params": {},
        "model_name": "model",
        "provider": "provider",
        "failover_count": 0,
    }


def test_dispatcher_skips_blocked_front_job(manager):
    blocked_job = make_job("blocked")
    ready_job = make_job("ready")
    blocked_strategy = FakeStrategy(DispatchReadiness(False, 500))
    ready_strategy = FakeStrategy(DispatchReadiness(True))

    manager._state = State.RUNNING
    manager.pending_translation_jobs.extend([blocked_job, ready_job])
    manager.strategies = {
        "blocked": blocked_strategy,
        "ready": ready_strategy,
    }

    manager._dispatch_next_job_to_pool()

    assert ready_strategy.dispatched_jobs == [ready_job]
    assert blocked_strategy.dispatched_jobs == []
    assert list(manager.pending_translation_jobs) == [blocked_job]


def test_litellm_wait_for_response_blocks_only_same_connection(manager):
    manager.active_translation_jobs = 1
    manager._active_jobs_per_connection["conn-a"] = 1

    strategy_a = LiteLLMStrategy(
        manager,
        "conn-a",
        {"wait_for_response": True, "global_limits": {}, "configured_models": []},
    )
    strategy_b = LiteLLMStrategy(
        manager,
        "conn-b",
        {"wait_for_response": True, "global_limits": {}, "configured_models": []},
    )

    assert not strategy_a.get_dispatch_readiness().ready
    assert strategy_b.get_dispatch_readiness().ready


def test_per_connection_active_counter_starts_and_finishes(manager):
    job = make_job("conn-a")

    manager._mark_job_started(job)

    assert manager.active_translation_jobs == 1
    assert manager._active_jobs_per_connection == {"conn-a": 1}

    manager._mark_job_finished(job)

    assert manager.active_translation_jobs == 0
    assert manager._active_jobs_per_connection == {}

    manager._mark_job_finished(job)

    assert manager.active_translation_jobs == 0
    assert manager._active_jobs_per_connection == {}


def test_dispatch_start_failure_does_not_underflow_active_counter(manager):
    reasons = []
    job = make_job("conn-a")

    manager._state = State.RUNNING
    manager.total_jobs_for_progress = 1
    manager.batch_finished.connect(reasons.append)

    manager._handle_job_dispatch_failed(job, "boom", RuntimeError("boom"))

    assert manager.active_translation_jobs == 0
    assert manager._active_jobs_per_connection == {}
    assert reasons == ["completed with dispatch errors"]


def test_missing_strategy_finalizes_batch_via_manager(manager):
    reasons = []

    manager._state = State.RUNNING
    manager.pending_translation_jobs.append(make_job("missing"))
    manager.batch_finished.connect(reasons.append)

    manager._dispatch_next_job_to_pool()

    assert reasons == ["failed (no strategy: missing)"]
    assert manager._state == State.IDLE
    assert not manager.pending_translation_jobs


def test_retriable_failure_requeues_and_restarts_dispatch_timer(manager, monkeypatch):
    class RetriableException(Exception):
        status_code = 500

    class FakeLiteLLM:
        @staticmethod
        def _should_retry(status_code: int) -> bool:
            return True

    monkeypatch.setattr(translation_manager_module, "litellm", FakeLiteLLM)
    monkeypatch.setattr(
        translation_manager_module,
        "litellm_exceptions",
        SimpleNamespace(RateLimitError=RetriableException, Timeout=RetriableException),
    )
    job = make_job("conn-a")

    manager._state = State.RUNNING
    manager.total_jobs_for_progress = 1
    manager._mark_job_started(job)

    manager._handle_job_failed(job, "retry", "type", "details", RetriableException())

    assert manager.active_translation_jobs == 0
    assert manager._active_jobs_per_connection == {}
    assert list(manager.pending_translation_jobs) == [job]
    assert manager.translation_timer.isActive()


def test_litellm_rate_limit_uses_model_specific_limits(manager, monkeypatch):
    monkeypatch.setitem(
        settings.current_settings,
        "active_model_for_connection",
        {"conn-a": "model-a"},
    )
    strategy = LiteLLMStrategy(
        manager,
        "conn-a",
        {
            "wait_for_response": True,
            "global_limits": {"rpm": 100, "rpd": None, "tpm": None},
            "configured_models": [
                {
                    "model_id": "model-a",
                    "limits": {
                        "use_global_limits": False,
                        "rpm": 1,
                        "rpd": None,
                        "tpm": None,
                    },
                }
            ],
        },
    )

    strategy.usage_tracker["requests"].append(time.monotonic())

    assert strategy._is_rate_limited()
