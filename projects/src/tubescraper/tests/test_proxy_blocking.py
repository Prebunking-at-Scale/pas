from unittest.mock import patch

import pytest
from tubescraper.youtube import PROXY_BLOCK_DURATION, bench_proxy_if_blocked
from yt_dlp.utils import DownloadError


@pytest.mark.parametrize(
    "message",
    [
        "ERROR: [youtube] abc123: Sign in to confirm you’re not a bot.",
        "ERROR: unable to download video data: HTTP Error 403: Forbidden",
        "ERROR: [youtube] abc123: HTTP Error 429: Too Many Requests",
    ],
)
def test_blocked_errors_deactivate_proxy(message):
    with patch("tubescraper.youtube.proxy_config") as proxy_config:
        bench_proxy_if_blocked(DownloadError(message), proxy_id=7)
    proxy_config.deactivate_proxy.assert_called_once_with(7, PROXY_BLOCK_DURATION)


@pytest.mark.parametrize(
    "message",
    [
        "ERROR: [youtube] abc123: Video unavailable",
        "ERROR: [youtube] abc123: Requested format is not available",
        "ERROR: [youtube] abc123: This video is private",
    ],
)
def test_other_errors_keep_proxy_active(message):
    with patch("tubescraper.youtube.proxy_config") as proxy_config:
        bench_proxy_if_blocked(DownloadError(message), proxy_id=7)
    proxy_config.deactivate_proxy.assert_not_called()
