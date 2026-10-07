import os
import random
import time

import structlog

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class ProxyConfig:
    """Configuration for proxy connections, loaded from environment variables.

    Environment variables:
        PROXY_COUNT: Number of available proxies to choose from (default: 0)
        PROXY_USERNAME: Proxy authentication username (default: "")
        PROXY_PASSWORD: Proxy authentication password (default: "")
    """

    def __init__(self) -> None:
        self.count = int(os.environ.get("PROXY_COUNT", 0))
        self.username = os.environ.get("PROXY_USERNAME", "")
        self.password = os.environ.get("PROXY_PASSWORD", "")
        self._inactive_until: dict[int, float] = {}
        self._consecutive_blocks: dict[int, int] = {}

    @property
    def is_configured(self) -> bool:
        """Check if proxy is properly configured."""
        return bool(self.count and self.username and self.password)

    def deactivate_proxy(self, proxy_id: int, duration: float) -> None:
        """Mark a proxy as inactive for a period of time."""
        self._inactive_until[proxy_id] = time.monotonic() + duration
        logger.warning(
            "proxy deactivated",
            proxy_id=proxy_id,
            duration_seconds=duration,
        )

    def bench_proxy(self, proxy_id: int, base: float, max_duration: float) -> float:
        """Deactivate a blocked proxy for `base` seconds, doubling with each further
        block in a row up to `max_duration`. Returns the duration used."""
        blocks = self._consecutive_blocks.get(proxy_id, 0) + 1
        self._consecutive_blocks[proxy_id] = blocks
        duration = min(base * 2 ** (blocks - 1), max_duration)
        self.deactivate_proxy(proxy_id, duration)
        return duration

    def proxy_succeeded(self, proxy_id: int) -> None:
        """Reset a proxy's backoff after a request through it works."""
        self._consecutive_blocks.pop(proxy_id, None)

    def _active_proxy_ids(self) -> list[int]:
        now = time.monotonic()
        expired = [pid for pid, until in self._inactive_until.items() if now >= until]
        for pid in expired:
            del self._inactive_until[pid]
        return [
            pid
            for pid in range(1, self.count + 1)
            if pid not in self._inactive_until
        ]

    def get_proxy_details(self) -> tuple[str, int]:
        """Generate proxy connection details.

        Returns:
            A tuple of (proxy_url, proxy_id).

        Raises:
            ValueError: If proxy is not configured.
        """
        if not self.is_configured:
            raise ValueError(
                "Proxy not configured. Set PROXY_COUNT, PROXY_USERNAME, and PROXY_PASSWORD."
            )

        active = self._active_proxy_ids()
        if not active:
            earliest = min(self._inactive_until.values())
            wait = earliest - time.monotonic()
            if wait > 0:
                logger.warning("all proxies inactive, waiting", wait_seconds=f"{wait:.1f}")
                time.sleep(wait)
            active = self._active_proxy_ids()

        proxy_id = random.choice(active)
        logger.debug(f"using proxy id {proxy_id}")
        return (
            f"http://{self.username}-{proxy_id}:{self.password}@p.webshare.io:80/",
            proxy_id,
        )

    def get_proxy_dict(self) -> dict[str, str] | None:
        """Generate proxy connection details as a dict for requests library.

        Returns:
            A dict with 'http' and 'https' keys, or None if proxy is not configured.
        """
        if not self.is_configured:
            logger.warning(
                "PROXY_COUNT, PROXY_USERNAME or PROXY_PASSWORD unset - not using proxy"
            )
            return None

        proxy_url, proxy_id = self.get_proxy_details()
        logger.info(f"using proxy id {proxy_id}")
        return {
            "http": proxy_url,
            "https": proxy_url,
        }


# Default instance loaded from environment
proxy_config = ProxyConfig()
