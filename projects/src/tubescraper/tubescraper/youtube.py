import contextlib
import io
import os
from typing import Any, cast

import structlog
import yt_dlp
from scraper_common import proxy_config
from structlog.contextvars import bind_contextvars
from tenacity import retry, stop_after_attempt
from yt_dlp.networking.impersonate import ImpersonateTarget

logger: structlog.BoundLogger = structlog.get_logger(__name__)

POT_PROVIDER_URL = os.environ.get("POT_PROVIDER_URL", "")


def id_for_channel(s: str) -> str:
    proxy_addr, proxy_id = proxy_config.get_proxy_details()
    bind_contextvars(proxy_id=proxy_id)
    opts = {
        "extract_flat": False,
        "proxy": proxy_addr,
        "ignoreerrors": "only_download",
        "noprogress": True,
        "impersonate": ImpersonateTarget(client="chrome"),
        "playlist_items": "0",
        "retries": 3,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        if not s.startswith("@"):
            s = f"channel/{s}"
        info = ydl.extract_info(f"https://youtube.com/{s}")
        if not info:
            logger.warning("No info dict returned from yt-dlp", channel_identifier=s)
            raise ValueError("No info dict from yt_dlp")

        if res := info.get("channel_id"):
            return res  # type: ignore
        raise ValueError("Channel without channel ID? Something's wrong")


@retry(reraise=True, stop=stop_after_attempt(3))
def channel_shorts(channel_id: str, num: int = 200) -> list[dict[Any, Any]]:
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
    with yt_dlp.YoutubeDL(opts) as ydl:
        logger.info(f"fetching entries for {channel_id}")
        info = ydl.extract_info(
            f"https://youtube.com/channel/{channel_id}/shorts",
            download=False,
        )

        if not info:
            raise ValueError("Empty info dict")

        entries = info.get("entries")
        if not isinstance(entries, list):
            raise ValueError("No or malformed entries")

    filtered = list(filter(None, entries))
    filtered = [x for x in filtered if "/shorts/" in x.get("url", "")]

    return filtered


@retry(reraise=True, stop=stop_after_attempt(3))
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
    with yt_dlp.YoutubeDL(opts) as ydl:
        logger.info(f"downloading entries for {keyword}")
        info = ydl.extract_info(
            # the sp parameter is a pre-computed search query that only matches shorts
            # uploaded in the last week
            f'https://www.youtube.com/results?search_query="{keyword}"&sp=CAISBggDEAkYAQ%253D%253D',
            download=False,
        )

        if not info:
            raise ValueError("Empty info dict")

        entries = info.get("entries")
        if not isinstance(entries, list):
            raise ValueError("No or malformed entries")

    filtered = list(filter(None, entries))
    return filtered


@retry(reraise=True, stop=stop_after_attempt(3))
def video_details(entry_id: str, buf: io.BytesIO | None = None) -> dict[Any, Any]:
    """Get details about a video. If buf is specified, download the video file
    into the buffer."""
    proxy_addr, proxy_id = proxy_config.get_proxy_details()
    bind_contextvars(proxy_id=proxy_id)

    download = True
    if not buf:
        download = False
        buf = io.BytesIO()

    # 18 (360p mp4) is the only format that doesn't require ffmpeg post-processing.
    # if we use any other format yt-dlp has to merge video and audio streams
    # separately, which results in the output not correctly being written to stdout
    # (something to do with subprocesses? not sure) so this is something to consider
    # when making a change here
    ctx = {
        "outtmpl": "-",
        "logtostderr": True,
        "format": "18",
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
    buf.seek(0)
    with contextlib.redirect_stdout(buf), yt_dlp.YoutubeDL(ctx) as video:  # type: ignore
        details = video.extract_info(entry_id, download=download)
        details = cast(dict[Any, Any], details)
    logger.debug(f"downloaded bytes: {buf.tell()}")
    buf.seek(0)
    return details
