import logging
from concurrent.futures import ThreadPoolExecutor

import pytest

import omni_trans_core.key_pool as key_pool_module
from omni_trans_core.key_pool import KeyPool


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(key_pool_module, "time", fake)
    return fake


def test_rotation_order():
    pool = KeyPool(["key-a", "key-b", "key-c"])

    assert [pool.next_key() for _ in range(4)] == [
        "key-a",
        "key-b",
        "key-c",
        "key-a",
    ]


def test_keys_property_returns_copy():
    pool = KeyPool(["key-a"])
    returned = pool.keys
    returned.append("key-b")

    assert pool.keys == ["key-a"]
    assert pool.has_keys


def test_empty_pool_has_no_keys():
    pool = KeyPool([])

    assert not pool.has_keys
    assert pool.keys == []
    assert pool.next_key() is None
    assert pool.next_retry_delay_ms() == 1000


def test_skips_cooling_key(clock):
    pool = KeyPool(["key-a", "key-b"])
    pool.mark_failed("key-a", cooldown_seconds=30)

    assert pool.next_key() == "key-b"
    assert pool.next_key() == "key-b"

    clock.advance(29)
    assert pool.next_key() == "key-b"

    clock.advance(1)
    assert pool.next_key() == "key-a"


def test_skips_rpm_limited_key(clock):
    pool = KeyPool(["key-a", "key-b"], rpm_limit=1)
    pool.record_request("key-a")

    assert pool.next_key() == "key-b"

    pool.record_request("key-b")
    assert pool.next_key() is None

    clock.advance(61)
    assert pool.next_key() == "key-a"


def test_all_busy_returns_none(clock):
    rpm_pool = KeyPool(["key-a", "key-b"], rpm_limit=1)
    rpm_pool.record_request("key-a")
    rpm_pool.record_request("key-b")

    assert rpm_pool.next_key() is None

    cooling_pool = KeyPool(["key-a", "key-b"])
    cooling_pool.mark_failed("key-a", cooldown_seconds=10)
    cooling_pool.mark_failed("key-b", cooldown_seconds=10)

    assert cooling_pool.next_key() is None


def test_next_retry_delay_ms_uses_nearest_cooldown(clock):
    pool = KeyPool(["key-a", "key-b"])
    pool.mark_failed("key-a", cooldown_seconds=10)
    pool.mark_failed("key-b", cooldown_seconds=20)

    assert pool.next_retry_delay_ms() == 10_050

    clock.advance(5)
    assert pool.next_retry_delay_ms() == 5_050


def test_next_retry_delay_ms_waits_for_rpm_window(clock):
    pool = KeyPool(["key-a", "key-b"], rpm_limit=1)
    pool.record_request("key-a")
    pool.mark_failed("key-b", cooldown_seconds=120)

    assert pool.next_retry_delay_ms() == 60_050

    clock.advance(30)
    assert pool.next_retry_delay_ms() == 30_050


def test_next_retry_delay_ms_defaults_when_no_key_is_busy():
    pool = KeyPool(["key-a", "key-b"])

    assert pool.next_retry_delay_ms() == 1000


def test_mark_failed_uses_default_cooldown(clock):
    pool = KeyPool(["key-a"])
    pool.mark_failed("key-a")

    assert pool.next_key() is None

    clock.advance(60.9)
    assert pool.next_key() is None

    clock.advance(0.2)
    assert pool.next_key() == "key-a"


def test_mark_success_clears_cooldown(clock):
    pool = KeyPool(["key-a"])
    pool.mark_failed("key-a", cooldown_seconds=60)

    assert pool.next_key() is None

    pool.mark_success("key-a")
    assert pool.next_key() == "key-a"


def test_unknown_key_is_ignored(caplog):
    pool = KeyPool(["key-a"])

    with caplog.at_level(logging.DEBUG, logger="CORE.key_pool"):
        pool.record_request("missing-key")
        pool.mark_success("missing-key")
        pool.mark_failed("missing-key")

    assert pool.current_rpm("missing-key") == 0
    assert pool.next_key() == "key-a"
    assert len(caplog.records) == 3
    assert all("unknown" in record.message.lower() for record in caplog.records)


def test_stats_counts(clock):
    pool = KeyPool(["key-a", "key-b", "key-c", "key-d"], rpm_limit=2)
    pool.mark_failed("key-a", cooldown_seconds=60)
    pool.record_request("key-b")
    pool.record_request("key-b")

    assert pool.stats() == {
        "keys": 4,
        "available": 2,
        "cooling": 1,
        "rpm_limited": 1,
    }

    clock.advance(61)
    assert pool.stats() == {
        "keys": 4,
        "available": 4,
        "cooling": 0,
        "rpm_limited": 0,
    }


def test_stats_for_empty_pool():
    pool = KeyPool([])

    assert pool.stats() == {
        "keys": 0,
        "available": 0,
        "cooling": 0,
        "rpm_limited": 0,
    }


def test_repr_does_not_expose_keys():
    pool = KeyPool(["secret-key-123456", "another-secret-987654"])

    text = repr(pool)

    assert "secret-key-123456" not in text
    assert "another-secret-987654" not in text
    assert "keys=2" in text


def test_current_rpm_culls_requests_older_than_window(clock):
    pool = KeyPool(["key-a"], rpm_limit=1)
    pool.record_request("key-a")

    assert pool.current_rpm("key-a") == 1

    clock.advance(61)
    assert pool.current_rpm("key-a") == 0
    assert pool.next_key() == "key-a"


@pytest.mark.parametrize("rpm_limit", [None, 0, -5])
def test_unlimited_rpm_never_limits(rpm_limit):
    pool = KeyPool(["key-a"], rpm_limit=rpm_limit)
    for _ in range(500):
        pool.record_request("key-a")

    assert pool.current_rpm("key-a") == 500
    assert pool.next_key() == "key-a"
    assert pool.stats()["rpm_limited"] == 0


def test_concurrent_record_request_is_counted():
    pool = KeyPool(["key-a"])

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(pool.record_request, ["key-a"] * 200))

    assert pool.current_rpm("key-a") == 200
