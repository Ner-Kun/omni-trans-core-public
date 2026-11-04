import collections
import logging
import threading
import time

logger = logging.getLogger("CORE.key_pool")

RPM_WINDOW_SECONDS = 60
RETRY_JITTER_MS = 50
FALLBACK_RETRY_DELAY_MS = 1000


def _mask_key(api_key: str) -> str:
    if not api_key:
        return "N/A_KEY"
    if len(api_key) <= 7:
        return "****"
    return f"{api_key[:3]}...{api_key[-4:]}"


class KeyPool:
    """Round-robin API key pool with per-key RPM tracking and cooldown.

    Blank and duplicate keys are dropped. Mutations for unknown keys are
    ignored instead of raising.
    """

    def __init__(
        self,
        keys: list[str],
        rpm_limit: int | None = None,
        cooldown_seconds: int = 61,
    ) -> None:
        self._keys: list[str] = list(dict.fromkeys(key for key in keys if key))
        self._rpm_limit: int | None = rpm_limit if rpm_limit and rpm_limit > 0 else None
        self._cooldown_seconds = cooldown_seconds
        self._request_times: dict[str, collections.deque[float]] = {
            key: collections.deque() for key in self._keys
        }
        self._cooldown_until: dict[str, float] = {}
        self._next_index = 0
        self._lock = threading.Lock()

    @property
    def keys(self) -> list[str]:
        with self._lock:
            return list(self._keys)

    @property
    def has_keys(self) -> bool:
        return bool(self._keys)

    def next_key(self) -> str | None:
        with self._lock:
            now = time.monotonic()
            key_count = len(self._keys)
            for offset in range(key_count):
                index = (self._next_index + offset) % key_count
                key = self._keys[index]
                if self._is_cooling_unlocked(key, now):
                    continue
                if self._is_rpm_limited_unlocked(key, now):
                    continue
                self._next_index = (index + 1) % key_count
                return key
            return None

    def record_request(self, key: str) -> None:
        with self._lock:
            timestamps = self._request_times.get(key)
            if timestamps is None:
                logger.debug("Ignoring request for unknown key %s.", _mask_key(key))
                return
            now = time.monotonic()
            _cull_unlocked(timestamps, now)
            timestamps.append(now)

    def current_rpm(self, key: str) -> int:
        with self._lock:
            return self._current_rpm_unlocked(key, time.monotonic())

    def mark_success(self, key: str) -> None:
        with self._lock:
            if key not in self._request_times:
                logger.debug("Ignoring success for unknown key %s.", _mask_key(key))
                return
            self._cooldown_until.pop(key, None)

    def mark_failed(self, key: str, cooldown_seconds: int | None = None) -> None:
        with self._lock:
            if key not in self._request_times:
                logger.debug("Ignoring failure for unknown key %s.", _mask_key(key))
                return
            seconds = self._cooldown_seconds if cooldown_seconds is None else cooldown_seconds
            if seconds <= 0:
                self._cooldown_until.pop(key, None)
                return
            self._cooldown_until[key] = time.monotonic() + seconds

    def next_retry_delay_ms(self) -> int:
        """Shortest wait until a busy key frees up, plus 50 ms jitter."""
        with self._lock:
            if not self._keys:
                return FALLBACK_RETRY_DELAY_MS
            now = time.monotonic()
            wait_times_ms: list[int] = []
            for key in self._keys:
                cooldown_until = self._cooldown_until.get(key)
                if cooldown_until and cooldown_until > now:
                    wait_times_ms.append(
                        int((cooldown_until - now) * 1000) + RETRY_JITTER_MS
                    )
                    continue
                if self._rpm_limit is None:
                    continue
                timestamps = self._request_times[key]
                _cull_unlocked(timestamps, now)
                if len(timestamps) >= self._rpm_limit:
                    wait_times_ms.append(
                        max(
                            RETRY_JITTER_MS,
                            int((timestamps[0] + RPM_WINDOW_SECONDS - now) * 1000)
                            + RETRY_JITTER_MS,
                        )
                    )
            return min(wait_times_ms) if wait_times_ms else FALLBACK_RETRY_DELAY_MS

    def stats(self) -> dict[str, int]:
        """Key counts; a cooling key is not also counted as RPM-limited."""
        with self._lock:
            now = time.monotonic()
            cooling = 0
            rpm_limited = 0
            available = 0
            for key in self._keys:
                if self._is_cooling_unlocked(key, now):
                    cooling += 1
                elif self._is_rpm_limited_unlocked(key, now):
                    rpm_limited += 1
                else:
                    available += 1
            return {
                "keys": len(self._keys),
                "available": available,
                "cooling": cooling,
                "rpm_limited": rpm_limited,
            }

    def __repr__(self) -> str:
        stats = self.stats()
        return (
            f"KeyPool(keys={stats['keys']}, available={stats['available']}, "
            f"cooling={stats['cooling']}, rpm_limited={stats['rpm_limited']})"
        )

    def _is_cooling_unlocked(self, key: str, now: float) -> bool:
        cooldown_until = self._cooldown_until.get(key)
        return bool(cooldown_until and cooldown_until > now)

    def _is_rpm_limited_unlocked(self, key: str, now: float) -> bool:
        if self._rpm_limit is None:
            return False
        return self._current_rpm_unlocked(key, now) >= self._rpm_limit

    def _current_rpm_unlocked(self, key: str, now: float) -> int:
        timestamps = self._request_times.get(key)
        if not timestamps:
            return 0
        _cull_unlocked(timestamps, now)
        return len(timestamps)


def _cull_unlocked(timestamps: collections.deque[float], now: float) -> None:
    cutoff = now - RPM_WINDOW_SECONDS
    while timestamps and timestamps[0] < cutoff:
        timestamps.popleft()
