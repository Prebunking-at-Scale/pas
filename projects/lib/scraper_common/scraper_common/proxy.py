import os
import random

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

    @property
    def is_configured(self) -> bool:
        """Check if proxy is properly configured."""
        return bool(self.count and self.username and self.password)

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

        proxy_id = random.randrange(1, self.count + 1)
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
