import litellm

from omni_trans_core.runnables import CustomJobRunnable


class FakeSignal:
    def __init__(self) -> None:
        self.emitted = []

    def emit(self, *args) -> None:
        self.emitted.append(args)


class FakeSignals:
    def __init__(self) -> None:
        for name in (
            "job_completed",
            "job_failed",
            "inspector_update",
            "thinking_unexpected",
            "thinking_mode_discovered",
        ):
            setattr(self, name, FakeSignal())


class FakeFormatter:
    def format_prompt(self, **kwargs):
        return [{"role": "user", "content": "hello"}]


class FakeParser:
    def parse(self, response, job_data):
        return "translation", "", {}


def _job(model_name: str, *, thinking: bool = True, level: str = "high"):
    return {
        "provider": "gemini",
        "model_name": model_name,
        "api_key": "key-a",
        "base_url": "",
        "headers": {},
        "generation_params": {
            "enable_model_thinking": thinking,
            "thinking_budget_value": -1,
            "thinking_level": level,
            "temperature": 1.0,
            "max_output_tokens": 128,
        },
        "thinking_config": {
            "mode": "auto",
            "enabled": thinking,
            "enable_cmd": "",
            "disable_cmd": "",
        },
        "original_item": {"id": "1", "source_text": "hello", "context": ""},
        "source_lang": "English",
        "target_lang": "Russian",
        "is_regeneration": False,
    }


def _run(monkeypatch, job_data):
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(litellm, "completion", fake_completion)
    monkeypatch.setattr(
        "omni_trans_core.runnables.proxy_manager.get_proxy", lambda: None
    )

    signals = FakeSignals()
    runnable = CustomJobRunnable(
        job_data, signals, FakeFormatter(), FakeParser()
    )
    runnable.run()
    assert signals.job_failed.emitted == []
    return captured


def test_gemini_25_uses_dynamic_thinking_budget(monkeypatch):
    captured = _run(monkeypatch, _job("gemini-2.5-flash"))

    assert captured["model"] == "gemini/gemini-2.5-flash"
    assert captured["thinking"] == {"type": "enabled", "budget_tokens": -1}
    assert captured["api_key"] == "key-a"
    assert "api_base" not in captured


def test_gemini_3_uses_reasoning_effort(monkeypatch):
    captured = _run(monkeypatch, _job("gemini-3-pro-preview", level="high"))

    assert captured["model"] == "gemini/gemini-3-pro-preview"
    assert captured["reasoning_effort"] == "high"
    assert "thinking" not in captured


def test_thinking_disabled_for_gemini_25_sets_zero_budget(monkeypatch):
    captured = _run(monkeypatch, _job("gemini-2.5-flash", thinking=False))

    assert captured["thinking"] == {"type": "enabled", "budget_tokens": 0}


def test_thinking_disabled_for_gemini_3_sets_none_effort(monkeypatch):
    captured = _run(monkeypatch, _job("gemini-3-pro-preview", thinking=False))

    assert captured["reasoning_effort"] == "none"
    assert "thinking" not in captured
