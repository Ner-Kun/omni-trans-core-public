import threading
import time
import httpx
import logging
from typing import Optional
from dataclasses import dataclass



logger = logging.getLogger('CORE.proxy_manager')

DEFAULT_TIMEOUT = 10
VALIDATE_URL = "http://httpbin.org/ip"
MAX_RETRIES = 3

@dataclass
class ProxyEntry:
    protocol: str
    host: str
    port: int
    username: str = ""
    password: str = ""
    source: str = "custom"
    fails: int = 0
    successes: int = 0
    speed_ms: int = 0

    @property
    def url(self) -> str:
        if self.username and self.password:
            return f"{self.protocol}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.protocol}://{self.host}:{self.port}"

    def __hash__(self):
        return hash(self.url)

    def __eq__(self, other):
        if isinstance(other, ProxyEntry):
            return self.url == other.url
        return False


class _ProxyPool:

    def __init__(self):
        self._lock = threading.Lock()
        self._pool: list[ProxyEntry] = []
        self._index = 0
        self._total_successes = 0
        self._total_failures = 0

    def set_proxies(self, entries: list[ProxyEntry]):
        with self._lock:
            self._pool = entries
            self._index = 0
            self._pool.sort(key=lambda e: e.speed_ms if e.speed_ms > 0 else float('inf'))
        logger.info(f"Proxy pool updated: {len(entries)} proxies")

    def get_next(self) -> Optional[ProxyEntry]:
        with self._lock:
            if not self._pool:
                return None
            entry = self._pool[self._index % len(self._pool)]
            self._index += 1
            return entry

    def mark_success(self, proxy_url: str, speed_ms: int = None):
        with self._lock:
            for entry in self._pool:
                if entry.url == proxy_url:
                    entry.fails = 0
                    entry.successes += 1
                    self._total_successes += 1
                    if speed_ms is not None:
                        if entry.speed_ms == 0:
                            entry.speed_ms = speed_ms
                        else:
                            entry.speed_ms = int(0.3 * speed_ms + 0.7 * entry.speed_ms)
                    break

    def mark_failed(self, proxy_url: str):
        with self._lock:
            for entry in self._pool:
                if entry.url == proxy_url:
                    entry.fails += 1
                    self._total_failures += 1
                    break

    def size(self) -> int:
        return len(self._pool)

    def get_stats(self) -> dict:
        return {
            "pool_size": self.size(),
            "total_successes": self._total_successes,
            "total_failures": self._total_failures,
        }

class _ProxyValidator:

    def validate(self, proxy_url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[bool, str, int]:
        success, msg, speed = self._validate_with_scheme(proxy_url, "http", timeout)
        if success:
            return success, msg, speed
        return self._validate_with_scheme(proxy_url, "https", timeout)

    def _validate_with_scheme(self, proxy_url: str, scheme: str, timeout: int) -> tuple[bool, str, int]:
        try:
            start_time = time.time()
            with httpx.Client(proxy=proxy_url, timeout=timeout) as client:
                resp = client.get(VALIDATE_URL)
                elapsed_ms = int((time.time() - start_time) * 1000)
                if resp.status_code == 200:
                    data = resp.json()
                    ip = data.get("origin", "unknown")
                    return True, f"OK (IP: {ip})", elapsed_ms
                return False, f"HTTP {resp.status_code}", elapsed_ms
        except httpx.ConnectTimeout:
            return False, "Connection timeout", timeout * 1000
        except httpx.ProxyError as e:
            return False, f"Proxy error: {e}", timeout * 1000
        except Exception as e:
            return False, str(e), timeout * 1000

class ProxyManager:

    def __init__(self):
        self._lock = threading.Lock()
        self._enabled = False
        self._pool = _ProxyPool()
        self._validator = _ProxyValidator()

    def configure(self, enabled: bool = False, custom_proxies: list[dict] = None) -> None:
        with self._lock:
            self._enabled = enabled
            entries = []
            for raw in (custom_proxies or []):
                entry = ProxyEntry(
                    protocol=raw.get("protocol", "http"),
                    host=raw.get("host", ""),
                    port=int(raw.get("port", 0)),
                    username=raw.get("username", ""),
                    password=raw.get("password", ""),
                )
                entries.append(entry)
            self._pool.set_proxies(entries)
            logger.info(f"Proxy manager configured: enabled={enabled}, proxies={len(entries)}")

    def get_proxy(self) -> Optional[str]:
        if not self._enabled:
            return None
        entry = self._pool.get_next()
        return entry.url if entry else None

    def get_proxy_with_retry(self, max_retries: int = MAX_RETRIES) -> tuple[Optional[str], Optional[httpx.Client]]:
        if not self._enabled:
            return None, None

        tried = set()
        for attempt in range(max_retries):
            proxy_url = self.get_proxy()
            if not proxy_url or proxy_url in tried:
                break
            tried.add(proxy_url)

            try:
                client = httpx.Client(proxy=proxy_url, timeout=60)
                client.get(VALIDATE_URL, timeout=10)
                return proxy_url, client
            except Exception:
                self._pool.mark_failed(proxy_url)
                if client:
                    client.close()
                continue

        return None, None

    def mark_success(self, proxy_url: str, speed_ms: int = None) -> None:
        self._pool.mark_success(proxy_url, speed_ms)

    def mark_failed(self, proxy_url: str) -> None:
        self._pool.mark_failed(proxy_url)

    def validate_proxy(self, proxy_url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[bool, str, int]:
        return self._validator.validate(proxy_url, timeout)

    def get_stats(self) -> dict:
        stats = self._pool.get_stats()
        stats["enabled"] = self._enabled
        return stats


proxy_manager = ProxyManager()
