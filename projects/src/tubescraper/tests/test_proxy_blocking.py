from unittest.mock import patch

import pytest
from tubescraper import youtube
from tubescraper.youtube import (
    PROXY_BLOCK_BASE,
    PROXY_BLOCK_MAX,
    bench_proxy_if_blocked,
    block_duration,
    proxy_succeeded,
)
from yt_dlp.utils import DownloadError

BOT_CHECK = "ERROR: [youtube] abc123: Sign in to confirm you’re not a bot."


@pytest.fixture(autouse=True)
def reset_backoff():
    youtube._consecutive_blocks.clear()


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
    proxy_config.deactivate_proxy.assert_called_once_with(7, PROXY_BLOCK_BASE)


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


def test_block_duration_doubles_up_to_max():
    assert block_duration(1) == PROXY_BLOCK_BASE
    assert block_duration(2) == PROXY_BLOCK_BASE * 2
    assert block_duration(3) == PROXY_BLOCK_BASE * 4
    assert block_duration(50) == PROXY_BLOCK_MAX


def test_repeated_blocks_back_off():
    with patch("tubescraper.youtube.proxy_config") as proxy_config:
        for _ in range(3):
            bench_proxy_if_blocked(DownloadError(BOT_CHECK), proxy_id=7)
    durations = [c.args[1] for c in proxy_config.deactivate_proxy.call_args_list]
    assert durations == [PROXY_BLOCK_BASE, PROXY_BLOCK_BASE * 2, PROXY_BLOCK_BASE * 4]


def test_success_resets_backoff():
    with patch("tubescraper.youtube.proxy_config") as proxy_config:
        bench_proxy_if_blocked(DownloadError(BOT_CHECK), proxy_id=7)
        bench_proxy_if_blocked(DownloadError(BOT_CHECK), proxy_id=7)
        proxy_succeeded(7)
        bench_proxy_if_blocked(DownloadError(BOT_CHECK), proxy_id=7)
    assert proxy_config.deactivate_proxy.call_args.args == (7, PROXY_BLOCK_BASE)


def test_backoff_is_per_proxy():
    with patch("tubescraper.youtube.proxy_config") as proxy_config:
        bench_proxy_if_blocked(DownloadError(BOT_CHECK), proxy_id=7)
        bench_proxy_if_blocked(DownloadError(BOT_CHECK), proxy_id=8)
    durations = [c.args for c in proxy_config.deactivate_proxy.call_args_list]
    assert durations == [(7, PROXY_BLOCK_BASE), (8, PROXY_BLOCK_BASE)]
