import litellm
from PySide6 import QtCore

from omni_trans_core.strategies import LiteLLMStrategy


class FakeThreadPool:
    def __init__(self) -> None:
        self.started = []

    def start(self, runnable) -> None:
        self.started.append(runnable)


class FakeTimer:
    def __init__(self) -> None:
        self.active = False
        self.delay = None

    def isActive(self) -> bool:
        return self.active

    def start(self, delay: int) -> None:
        self.active = True
        self.delay = delay


class FakeManager(QtCore.QObject):
    def __init__(self) -> None:
        super().__init__()
        self.thread_pool = FakeThreadPool()
        self.pending_translation_jobs = []
        self.translation_timer = FakeTimer()
        self._active_jobs_per_connection = {}
        self.started_jobs = []

    def is_running(self) -> bool:
        return True

    def _mark_job_started(self, job_data) -> None:
        self.started_jobs.append(job_data)

    def _handle_job_dispatch_failed(self, job_data, message, error) -> None:
        raise AssertionError(message)


def _make_strategy(rpm: int = 10):
    manager = FakeManager()
    strategy = LiteLLMStrategy(
        manager,
        "Google Gemini",
        {
            "name": "Google Gemini",
            "provider": "gemini",
            "api_key": "key-a",
            "api_keys": ["key-a", "key-b"],
            "global_limits": {"rpm": rpm},
            "configured_models": [{"model_id": "gemini-2.5-flash"}],
            "wait_for_response": True,
        },
    )
    strategy.create_runnable = lambda job: object()
    return manager, strategy


def _make_job():
    return {
        "original_item": {"source_text": "hello"},
        "model_name": "gemini-2.5-flash",
        "connection_name": "Google Gemini",
    }


def test_keys_rotate_round_robin():
    _, strategy = _make_strategy()
    jobs = [_make_job() for _ in range(3)]

    for job in jobs:
        assert strategy.dispatch_job(job)

    assert [job["api_key"] for job in jobs] == ["key-a", "key-b", "key-a"]
    assert strategy.key_pool.stats()["keys"] == 2


def test_all_keys_busy_defers_dispatch():
    _, strategy = _make_strategy(rpm=1)

    assert strategy.dispatch_job(_make_job())
    assert strategy.dispatch_job(_make_job())

    readiness = strategy.get_dispatch_readiness()
    assert readiness.ready is False
    assert readiness.retry_delay_ms > 0


def test_rate_limit_cools_the_used_key():
    manager, strategy = _make_strategy()
    job = _make_job()
    assert strategy.dispatch_job(job)
    used_key = job["api_key"]

    error = litellm.RateLimitError(
        message="429",
        llm_provider="gemini",
        model="gemini-2.5-flash",
    )
    strategy.on_job_failed(job, error, {})

    assert strategy.key_pool.stats()["cooling"] == 1
    assert strategy.key_pool.next_key() != used_key
    assert manager.translation_timer.delay is not None


def test_success_clears_cooldown():
    _, strategy = _make_strategy()
    job = _make_job()
    assert strategy.dispatch_job(job)
    used_key = job["api_key"]

    strategy.key_pool.mark_failed(used_key, cooldown_seconds=60)
    assert strategy.key_pool.stats()["cooling"] == 1

    strategy.on_job_completed(job, {})
    assert strategy.key_pool.stats()["cooling"] == 0
