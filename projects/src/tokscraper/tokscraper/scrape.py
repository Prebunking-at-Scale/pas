import contextlib
import io
from collections.abc import Iterable
from datetime import datetime
from typing import Any, cast
from uuid import UUID

import structlog
import yt_dlp
from scraper_common import ChannelFeed, StorageClient, proxy_config
from tenacity import retry, stop_after_attempt

from tokscraper.coreapi import (
    PLATFORM,
    api_client,
    register_download,
    update_video_stats,
)

type ChannelWatchers = dict[str, list[UUID]]

logger: structlog.BoundLogger = structlog.get_logger(__name__)


@retry(reraise=True, stop=stop_after_attempt(3))
def video_details(url: str, buf: io.BytesIO | None = None) -> dict[Any, Any]:
    proxy_addr, proxy_id = proxy_config.get_proxy_details()
    log = logger.bind(proxy_id=proxy_id)

    download = True
    if not buf:
        download = False
        buf = io.BytesIO()

    ctx = {
        "outtmpl": "-",
        "logtostderr": True,
        "format": "w*",
        "proxy": proxy_addr,
    }
    buf.seek(0)
    with contextlib.redirect_stdout(buf), yt_dlp.YoutubeDL(ctx) as video:  # type: ignore
        details = video.extract_info(url, download=download)
        details = cast(dict[Any, Any], details)
    log.debug(f"downloaded bytes: {buf.tell()}")
    buf.seek(0)
    return details


def blob_name(channel_name, downloaded: dict[Any, Any]) -> str:
    return f"{channel_name}/{downloaded['id']}.{downloaded['ext']}"


def rescrape_short(video: dict[Any, Any]) -> None:
    """Rescrape a video to update its stats."""
    log = logger.bind(video_id=video["id"])
    try:
        details = video_details(video["source_url"])
    except Exception as ex:
        log.warning("failed to fetch video details for rescrape", exc_info=ex)
        # Even if the above fails, we still want to update the last
        # scrape time to prevent us from trying to scrape this
        # video forever
        details = {}
    update_video_stats(details, video["id"])


def download_channel_shorts(
    channel: str,
    cursor: datetime,
    storage_client: StorageClient,
    org_ids: list[UUID],
    num: int = 200,
) -> datetime | None:
    proxy_addr, proxy_id = proxy_config.get_proxy_details()
    log = logger.new(channel=channel, cursor=cursor, proxy_id=proxy_id)

    next_cursor = None
    opts = {
        "playlist_items": f"1:{num}",
        "retries": 5,
        "sleep_interval": 10.0,
        "max_sleep_interval": 20.0,
        "sleep_interval_requests": 1.0,
        "ignoreerrors": "only_download",
        "logtostderr": True,
        "proxy": proxy_addr,
        "lazy_playlist": True,
        "extract_flat": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        log.info(f"fetching entries for {channel}")
        info = ydl.extract_info(f"https://tiktok.com/{channel}", download=False)
        if not info:
            raise ValueError("Empty info dict")

        entries = info.get("entries")
        if not isinstance(entries, list):
            raise ValueError("No or malformed entries")

        log.debug(f"{len(entries)} entries found..")
        for i, entry in enumerate(entries):
            log.bind(entry=entry)
            log.info(f"processing {i + 1} of {len(entries)} for channel {channel}...")
            if not entry:
                log.info("entry is none, continuing...")
                continue

            buf = io.BytesIO()
            try:
                existing_video = api_client.get_video(entry["id"], PLATFORM)
                if existing_video:
                    update_video_stats(entry)
                    continue

                details = video_details(
                    f"https://tiktok.com/{channel}/video/{entry['id']}", buf
                )
                destination_path = blob_name(channel, details)
                destination_path = storage_client.upload_blob(destination_path, buf)
                register_download(details, org_ids, destination_path)
                log.info("download successful", event_metric="download_success")

                timestamp = datetime.fromtimestamp(entry["timestamp"])
                if not next_cursor or timestamp > next_cursor:
                    next_cursor = timestamp

            except Exception as ex:
                log.error(
                    "exception with downloading, skipping entry",
                    event_metric="download_failure",
                    exc_info=ex,
                )
            finally:
                buf.close()

        return next_cursor


def preprocess_channel_feeds(feeds: Iterable[ChannelFeed]) -> ChannelWatchers:
    result: ChannelWatchers = {}
    for feed in feeds:
        if feed.platform != "tiktok":
            continue

        channel = feed.channel
        if not channel.startswith("@"):
            channel = f"@{channel}"

        result[channel] = result.get(channel, []) + [feed.organisation_id]

    return result
