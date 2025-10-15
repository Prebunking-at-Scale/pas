import contextlib
import io
import mimetypes
import os
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, cast
from uuid import UUID

import requests
import structlog
import yt_dlp
from google.cloud.storage import Bucket
from tubescraper.register import API_KEY, proxy_addr, register_download, update_cursor
from tubescraper.types import CORE_API, ChannelFeed
from yt_dlp.networking.impersonate import ImpersonateTarget
from yt_dlp.utils import DownloadError
from yt_dlp.YoutubeDL import RejectedVideoReached

logger: structlog.BoundLogger = structlog.get_logger(__name__)


POT_PROVIDER_URL = os.environ["POT_PROVIDER_URL"]
STORAGE_PATH_PREFIX = Path("tubescraper")


def id_for_channel(s: str) -> str:
    opts = {
        "extract_flat": False,
        "fragment_retries": 10,
        "ignoreerrors": "only_download",
        "noprogress": True,
        "playlist_items": "0",
        "retries": 10,
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


def backup_channel_entries(
    bucket: Bucket, channel: str, cursor: datetime, org_ids: list[UUID]
) -> None:
    log = logger.new()

    # returns list[object] because yt_dlp types are really inconsistent across extractors
    latest_seen = cursor
    prefix_path = str(STORAGE_PATH_PREFIX / channel) + "/"

    log = log.bind(cursor=latest_seen, prefix_path=prefix_path)

    opts = {
        "daterange": yt_dlp.utils.DateRange(cursor.strftime("%Y%m%d"), "99991231"),
        "playlist_items": "1:200",
        "retries": 10,
        "sleep_interval": 10.0,
        "max_sleep_interval": 20.0,
        "sleep_interval_requests": 1.0,
        "impersonate": ImpersonateTarget(client="chrome"),
        "ignoreerrors": "only_download",
        "logtostderr": True,
        "proxy": proxy_addr(),
        "lazy_playlist": True,
        "extract_flat": True,
        "extractor_args": {
            "youtubepot-bgutilhttp": {"base_url": [POT_PROVIDER_URL]},
        },
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        log.info(f"downloading entries for {channel} to {prefix_path}")
        info = ydl.extract_info(
            # the sp parameter is a pre-computed search query that gives
            # videos of length under 4 minutes, sorted by most recent.
            f"https://youtube.com/channel/{channel}/shorts",
            download=False,
        )

        if not info:
            raise yt_dlp.utils.DownloadError("Empty info dict")

        entries = info.get("entries")
        if not isinstance(entries, list):
            raise yt_dlp.utils.DownloadError("No or malformed entries")

        entries.reverse()

        log.debug(f"{len(entries)} entries found. iterating...")
        for i, entry in enumerate(entries):
            log.bind(entry=entry)

            log.info(f"processing {i} of {len(entries)} for channel {channel}...")
            if not entry:
                log.debug("entry is none, continuing...")
                continue

            if "/shorts/" not in entry.get("url", ""):
                log.debug("ignoring non-short entry, continuing...")
                continue

            # 18 (360p mp4) is the only format that doesn't require ffmpeg post-processing.
            # if we use any other format yt-dlp has to merge video and audio streams
            # separately, which results in the output not correctly being written to stdout
            # (something to do with subprocesses? not sure) so this is something to consider
            # when making a change here
            ctx = {
                "outtmpl": "-",
                "logtostderr": True,
                "format": "18",
                "proxy": proxy_addr(),
                "extractor_args": {
                    "youtube": {
                        "player_client": ["tv_simply"],
                        "player_skip": ["configs", "initial_data"],
                        "skip": ["dash", "hls", "translated_subs", "subs"],
                    },
                    "youtubepot-bgutilhttp": {"base_url": [POT_PROVIDER_URL]},
                },
                "daterange": yt_dlp.utils.DateRange(cursor.strftime("%Y%m%d"), "99991231"),
                # "match_filter": yt_dlp.match_filter_func(
                #     None, [f"upload_date < {int(cursor.strftime("%Y%m%d"))}"]
                # ),
            }
            buf = io.BytesIO()
            with contextlib.redirect_stdout(buf), yt_dlp.YoutubeDL(ctx) as video:  # type: ignore
                log.debug(f"downloading to buffer {id(buf)}")
                try:
                    downloaded = video.extract_info(entry["id"])  # fmt: skip  # extract_info again to use the POT server (duh?)
                    downloaded = cast(dict[Any, Any], downloaded)
                except RejectedVideoReached as ex:
                    log.error("video out of date range, skipping", exc_info=ex)
                    continue
                except DownloadError as ex:
                    log.error("yt_dlp download error, skipping", exc_info=ex)
                    continue
                except Exception as ex:
                    log.error(
                        "non-download error with shorts scraping?, skipping",
                        exc_info=ex,
                    )
                    continue

                log.debug(f"video buffered. buffer size: {buf.tell()}")
                buf.seek(0)

                if not downloaded:
                    log.debug("downloaded is none, continuing...")
                    continue

                # "default": f"{output_directory}/%(id)s.%(channel_id)s.%(timestamp)s.%(ext)s"
                blob_path = (
                    prefix_path
                    + f"{downloaded["id"]}.{downloaded["channel_id"]}.{downloaded["timestamp"]}"
                )

                log.bind(blob_path=blob_path)
                log.debug(f"uploading blob to path {blob_path}")
                bucket.blob(blob_path).upload_from_file(buf, content_type="video/mp4")
                buf.close()

                register_download(downloaded, org_ids)
                if timestamp := downloaded.get("timestamp"):
                    dt = datetime.fromtimestamp(timestamp)
                elif upload_date := downloaded.get("upload_date"):
                    dt = datetime.strptime(upload_date, "%Y%m%d")
                else:
                    log.error("short without timestamp/upload date? skipping")
                    continue
                update_cursor(channel, dt)


def backup_youtube_video(bucket: Bucket, info: dict[str, Any]) -> bool:
    """Uploads downloaded files from a channel to Google Cloud Storage.

    Args:
        bucket (Bucket): GCS bucket to upload to.
        info (dict): yt-dlp's info dict output.
    """
    channel_id = info.get("channel_id", "unknown")
    filename = info.get("filename")

    log = logger.bind(channel_id=channel_id, filename=filename)

    if not filename:
        log.error(f"filename missing for video {info.get("id")}")
        return False

    basename = os.path.basename(filename)

    source_path: str = str(filename)
    target_path: str = str(STORAGE_PATH_PREFIX / channel_id / basename)
    type, _ = mimetypes.guess_file_type(source_path)

    log = log.bind(
        filename=filename,
        basename=basename,
        source_path=source_path,
        target_path=target_path,
        content_type=type,
    )

    log.debug(f"backing up {filename} to {target_path}")

    blob = bucket.blob(target_path)
    blob.upload_from_filename(source_path, content_type=type)
    return True


def channel_download_hook(bucket: Bucket, org_ids: list[UUID]) -> Callable[..., Any]:
    """Creates a yt_dlp download hook that uploads finished videos to storage and updates cursors.

    Args:
        bucket (Bucket): The Google Cloud Storage bucket for uploads.
        org_id (UUID): The organisation ID the channel was downloaded for.

    Returns:
        Callable[..., Any]: A function suitable for use as a yt_dlp progress hook.

    """

    log = logger.bind()

    def hook(d: dict[Any, Any]) -> None:
        if d.get("status") == "finished":
            status = backup_youtube_video(bucket, d["info_dict"])
            if status:
                register_download(d["info_dict"], org_ids)

                if timestamp := d["info_dict"].get("timestamp"):
                    dt = datetime.fromtimestamp(timestamp)
                elif upload_date := d["info_dict"].get("upload_date"):
                    dt = datetime.strptime(upload_date, "%Y%m%d")
                else:
                    log.error("short without timestamp/upload date? skipping")
                    return
                update_cursor(d["info_dict"]["channel_id"], dt)

    return hook


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
        if feed.platform != "youtube":
            continue
        result[feed.channel] = result.get(feed.channel, []) + [feed.organisation_id]

    return result
