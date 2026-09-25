import io
import os
import tempfile
from typing import Any, cast

import structlog
import yt_dlp
from scraper_common import proxy_config
from structlog.contextvars import bind_contextvars
from tenacity import retry, stop_after_attempt, wait_exponential
from yt_dlp.networking.impersonate import ImpersonateTarget

logger: structlog.BoundLogger = structlog.get_logger(__name__)

POT_PROVIDER_URL = os.environ.get("POT_PROVIDER_URL", "")

# A blocked proxy is benched for PROXY_BLOCK_BASE seconds, doubling with each
# further block in a row up to PROXY_BLOCK_MAX. Some of YouTube's flags on our
# proxies have cleared within an hour, so retrying every few minutes wastes requests.
PROXY_BLOCK_BASE = 30 * 60
PROXY_BLOCK_MAX = 6 * 60 * 60

_consecutive_blocks: dict[int, int] = {}

# Substrings of yt-dlp errors that mean YouTube has flagged the requesting IP,
# rather than there being a problem with the video itself.
BLOCK_SIGNATURES = (
    "Sign in to confirm",
    "HTTP Error 403",
    "HTTP Error 429",
)


def bench_proxy_if_blocked(ex: Exception, proxy_id: int) -> None:
    """Deactivate the proxy for a while if the error looks like an IP block."""
    message = str(ex)
    if any(signature in message for signature in BLOCK_SIGNATURES):
        logger.warning(
            "proxy appears blocked by youtube, deactivating",
            event_metric="proxy_blocked",
            proxy_id=proxy_id,
        )
        blocks = _consecutive_blocks.get(proxy_id, 0) + 1
        _consecutive_blocks[proxy_id] = blocks
        proxy_config.deactivate_proxy(proxy_id, block_duration(blocks))


def block_duration(blocks: int) -> float:
    """How long to bench a proxy that has been blocked `blocks` times in a row."""
    return min(PROXY_BLOCK_BASE * 2 ** (blocks - 1), PROXY_BLOCK_MAX)


def proxy_succeeded(proxy_id: int) -> None:
    """Reset a proxy's backoff after a request through it works."""
    _consecutive_blocks.pop(proxy_id, None)


def channel_url(channel: str) -> str:
    """Build the shorts listing URL for a channel handle or channel ID."""
    path = channel if channel.startswith("@") else f"channel/{channel}"
    return f"https://youtube.com/{path}/shorts"


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(min=30, max=120))
def channel_shorts(channel: str, num: int = 200) -> list[dict[Any, Any]]:
    """fetch channel video entries"""

    proxy_addr, proxy_id = proxy_config.get_proxy_details()
    bind_contextvars(proxy_id=proxy_id)

    opts = {
        "playlist_items": f"1:{num}",
        "retries": 5,
        "sleep_interval": 10.0,
        "max_sleep_interval": 20.0,
        "sleep_interval_requests": 1.0,
        "impersonate": ImpersonateTarget(client="chrome"),
        "ignoreerrors": "only_download",
        "logtostderr": True,
        "proxy": proxy_addr,
        "lazy_playlist": True,
        "extract_flat": True,
        "extractor_args": {
            "youtubepot-bgutilhttp": {"base_url": [POT_PROVIDER_URL]},
        },
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            logger.info(f"fetching entries for {channel}")
            info = ydl.extract_info(channel_url(channel), download=False)
            proxy_succeeded(proxy_id)

            if not info:
                raise ValueError("Empty info dict")

            entries = info.get("entries")
            if not isinstance(entries, list):
                raise ValueError("No or malformed entries")
    except yt_dlp.utils.DownloadError as ex:
        bench_proxy_if_blocked(ex, proxy_id)
        raise

    filtered = list(filter(None, entries))
    filtered = [x for x in filtered if "/shorts/" in x.get("url", "")]

    return filtered


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(min=30, max=120))
def keyword_shorts(keyword, num: int = 200) -> list[dict[Any, Any]]:
    proxy_addr, proxy_id = proxy_config.get_proxy_details()
    bind_contextvars(proxy_id=proxy_id)

    opts = {
        "playlist_items": f"1:{num}",
        "retries": 5,
        "sleep_interval": 10.0,
        "max_sleep_interval": 20.0,
        "sleep_interval_requests": 1.0,
        "impersonate": ImpersonateTarget(client="chrome"),
        "ignoreerrors": "only_download",
        "logtostderr": True,
        "proxy": proxy_addr,
        "lazy_playlist": True,
        "extract_flat": True,
        "extractor_args": {
            "youtubepot-bgutilhttp": {"base_url": [POT_PROVIDER_URL]},
        },
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            logger.info(f"downloading entries for {keyword}")
            info = ydl.extract_info(
                # the sp parameter is a pre-computed search query that only matches
                # shorts uploaded in the last week
                f'https://www.youtube.com/results?search_query="{keyword}"&sp=CAISBggDEAkYAQ%253D%253D',
                download=False,
            )
            proxy_succeeded(proxy_id)

            if not info:
                raise ValueError("Empty info dict")

            entries = info.get("entries")
            if not isinstance(entries, list):
                raise ValueError("No or malformed entries")
    except yt_dlp.utils.DownloadError as ex:
        bench_proxy_if_blocked(ex, proxy_id)
        raise

    filtered = list(filter(None, entries))
    return filtered


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(min=30, max=120))
def video_details(entry_id: str, buf: io.BytesIO | None = None) -> dict[Any, Any]:
    """Get details about a video. If buf is specified, download the video file
    into the buffer."""
    proxy_addr, proxy_id = proxy_config.get_proxy_details()
    bind_contextvars(proxy_id=proxy_id)

    download = buf is not None

    with tempfile.TemporaryDirectory() as tmpdir:
        # YouTube no longer serves format 18 (progressive mp4) to most clients,
        # so video and audio are fetched separately and ffmpeg-merged, which
        # needs a real output file rather than stdout.
        ctx = {
            "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),
            "logtostderr": True,
            "format": "18/bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
            # Prefer the format closest to 480p over the highest resolution,
            # to keep file sizes near what format 18 (360p) used to give us.
            "format_sort": ["res:480"],
            "merge_output_format": "mp4",
            "proxy": proxy_addr,
            "impersonate": ImpersonateTarget(client="chrome"),
            "extractor_args": {
                "youtube": {
                    "player_skip": ["configs", "initial_data"],
                    "skip": ["dash", "hls", "translated_subs", "subs"],
                    "player_js_version": ["actual"],
                },
                "youtubepot-bgutilhttp": {"base_url": [POT_PROVIDER_URL]},
            },
        }
        try:
            with yt_dlp.YoutubeDL(ctx) as video:
                details = video.extract_info(entry_id, download=download)
                proxy_succeeded(proxy_id)
                details = cast(dict[Any, Any], details)
        except yt_dlp.utils.DownloadError as ex:
            bench_proxy_if_blocked(ex, proxy_id)
            raise

        if buf is not None:
            filepath = details["requested_downloads"][0]["filepath"]
            buf.seek(0)
            with open(filepath, "rb") as f:
                buf.write(f.read())
            logger.debug(f"downloaded bytes: {buf.tell()}")
            buf.seek(0)

    return details
