import contextlib
import io
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import requests
import structlog
import yt_dlp
from google.cloud.storage import Bucket
from tokscraper.register import API_KEY, proxy_details, register_download, update_cursor
from tokscraper.types import CORE_API, ChannelFeed
from yt_dlp.networking.impersonate import ImpersonateTarget
from yt_dlp.utils import DownloadError
from yt_dlp.YoutubeDL import RejectedVideoReached

logger: structlog.BoundLogger = structlog.get_logger(__name__)


STORAGE_PATH_PREFIX = Path("tokscraper")

type BufferedEntry = tuple[dict[Any, Any], io.BytesIO]


def download_video_for_daterange(
    entry: dict[Any, Any],
    cursor: datetime,
    buf: io.BytesIO,
) -> BufferedEntry:
    log = logger.bind()

    for attempt in range(1, 4):
        proxy_addr, proxy_id = proxy_details()
        log = log.bind(proxy_id=proxy_id)
        ctx = {
            "outtmpl": "-",
            "logtostderr": True,
            "format": "w*",
            "proxy": proxy_addr,
            "daterange": yt_dlp.utils.DateRange(cursor.strftime("%Y%m%d"), "99991231"),
            "break_on_reject": True,
        }
        with contextlib.redirect_stdout(buf), yt_dlp.YoutubeDL(ctx) as video:  # type: ignore
            log.debug(f"downloading to buffer {id(buf)}")
            try:
                downloaded = video.extract_info(
                    f"https://tiktok.com/@{entry['uploader']}/video/{entry['id']}"
                )
                downloaded = cast(dict[Any, Any], downloaded)
            except RejectedVideoReached as ex:
                log.error("video out of date range, ending iteration", exc_info=ex)
                raise ex
            except DownloadError as ex:
                log.error(f"yt_dlp download error, attempt {attempt}", exc_info=ex)
                if 3 <= attempt:
                    raise Exception from ex
                continue

            log.debug(f"video buffered. buffer size: {buf.tell()}")
            _ = buf.seek(0)
            return (downloaded, buf)
    raise Exception("should be unreachable")


def generate_blob_path(prefix_path: str, downloaded: dict[Any, Any]) -> str:
    return (
        prefix_path
        + f"{downloaded['id']}.{downloaded['channel_id']}.{downloaded['timestamp']}.{downloaded['ext']}"
    )


def upload_blob(bucket: Bucket, blob_path: str, buf: io.BytesIO) -> None:
    log = logger.bind(blob_path=blob_path)
    log.debug(f"uploading blob to path {blob_path}")
    bucket.blob(blob_path).upload_from_file(buf, content_type="video/mp4")


def backup_channel_entries(
    bucket: Bucket, channel: str, cursor: datetime, org_ids: list[UUID]
) -> None:
    """Downloads and archives TikTok videos from a channel.

    Updates the cursor only once at the end with the maximum timestamp seen.
    """
    log = logger.new()

    # Track the newest timestamp we've seen to update cursor at the end
    latest_seen = cursor
    prefix_path = str(STORAGE_PATH_PREFIX / channel) + "/"

    proxy_addr, proxy_id = proxy_details()
    log = log.bind(cursor=cursor, prefix_path=prefix_path, proxy_id=proxy_id)

    opts = {
        "daterange": yt_dlp.utils.DateRange(cursor.strftime("%Y%m%d"), "99991231"),
        "playlist_items": "1:200",
        "retries": 10,
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
        log.info(f"downloading entries for {channel} to {prefix_path}")
        info = ydl.extract_info(f"https://tiktok.com/{channel}", download=False)

        if not info:
            raise ValueError("Empty info dict")

        entries = info.get("entries")
        if not isinstance(entries, list):
            raise ValueError("No or malformed entries")

        log.debug(f"{len(entries)} entries found. iterating...")
        for i, entry in enumerate(entries):
            log.bind(entry=entry)

            log.info(f"processing {i} of {len(entries)} for channel {channel}...")
            if not entry:
                log.debug("entry is none, continuing...")
                continue

            try:
                buf = io.BytesIO()
                downloaded, buf = download_video_for_daterange(entry, cursor, buf)
                blob_path = generate_blob_path(prefix_path, downloaded)
                upload_blob(bucket, blob_path, buf)
                buf.close()

                log.info("download successful", event_metric="download_success")
                register_download(downloaded, org_ids, blob_path)

                if timestamp := downloaded.get("timestamp"):
                    dt = datetime.fromtimestamp(timestamp)
                elif upload_date := downloaded.get("upload_date"):
                    dt = datetime.strptime(upload_date, "%Y%m%d")
                else:
                    log.error("short without timestamp/upload date? skipping")
                    continue

                # Track the maximum timestamp, don't update cursor yet
                if dt > latest_seen:
                    latest_seen = dt

            except RejectedVideoReached:
                # stop downloading new entries
                break

            except Exception as ex:
                log.error(
                    "exception with downloading, skipping entry",
                    event_metric="download_failure",
                    exc_info=ex,
                )
                continue

        # Update cursor once at the end with the newest timestamp seen
        if latest_seen > cursor:
            log.info(f"updating cursor from {cursor} to {latest_seen}")
            update_cursor(channel, latest_seen)


def fetch_channel_feeds() -> list[ChannelFeed]:
    """Fetches channel feed data from the core API.

    Returns:
        list[ChannelFeed]:
            A list of ChannelFeed objects parsed from the API response.

    """
    with requests.get(
        f"{CORE_API}/media_feeds/channels",
        headers={"X-API-TOKEN": API_KEY},
    ) as resp:
        resp.raise_for_status()
        data = resp.json()["data"]
        return [ChannelFeed(**feed) for feed in data]


type ChannelWatchers = dict[str, list[UUID]]


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
