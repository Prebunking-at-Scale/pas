import mimetypes
import os
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from uuid import UUID

import requests
import structlog
import yt_dlp
from google.cloud.storage import Bucket
from tubescraper.register import API_KEY, register_download, update_cursor
from tubescraper.types import CORE_API, ChannelFeed
from yt_dlp.networking.impersonate import ImpersonateTarget
from yt_dlp.utils import DownloadError, RejectedVideoReached

logger: structlog.BoundLogger = structlog.get_logger(__name__)


POT_PROVIDER_URL = os.environ["POT_PROVIDER_URL"]
PROXY_USERNAME = os.environ["PROXY_USERNAME"]
PROXY_PASSWORD = os.environ["PROXY_PASSWORD"]
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


def download_channel(
    channel_id: str,
    output_directory: str,
    cursor: datetime,
    download_hook: Callable[[dict[Any, Any]], None],
) -> dict[Any, Any] | None:
    """Downloads YouTube Shorts from a specified channel using yt_dlp with custom options.

    This function connects to YouTube and downloads Shorts content from the specified
    channel.  It uses a datetime cursor to avoid re-downloading already processed
    content. Video and subtitle options are configured to ensure consistent output and
    error resilience.  It extracts both manual and auto-generated subtitles. Translated
    subtitles are skipped via extractor arguments.

    Args:
        channel_id (str):
            The YouTube channel ID
        output_directory (str):
            The directory path where downloaded files will be saved.
        cursor (datetime):
            The datetime threshold for filtering content. Only videos uploaded after
            this date will be downloaded.
        download_hook (Callable[[dict[Any, Any]], None]):
            A callback function that receives download progress information from yt_dlp.

    Returns:
        dict[Any, Any] | None:
            A dictionary containing the extracted video information if successful,
            or None if no videos were found or if download was rejected/failed.

    """
    log = logger.bind()

    opts = {
        "fragment_retries": 10,
        "playlistreverse": True,  # for cursor
        "dateafter": cursor.date(),
        "break_on_reject": True,
        "outtmpl": {
            "default": f"{output_directory}/%(id)s.%(channel_id)s.%(timestamp)s.%(ext)s"
        },
        "progress_hooks": [download_hook],
        "postprocessors": [
            {"key": "FFmpegConcat", "only_multi_video": True, "when": "playlist"}
        ],
        "playlist_items": "1:100",
        "impersonate": ImpersonateTarget(client="chrome"),
        "retries": 10,
        "sleep_interval": 10.0,
        "max_sleep_interval": 20.0,
        "sleep_interval_requests": 0.75,
        "writeautomaticsub": False,
        "writesubtitles": False,
        "extractor_args": {
            "youtube": {
                "player_client": ["web", "web_embedded"],
                "player_skip": ["configs", "initial_data"],
                "skip": ["dash", "hls", "translated_subs", "subs"],
            },
            "youtubepot-bgutilhttp": {"base_url": [POT_PROVIDER_URL]},
        },
        "color": {"stderr": "never", "stdout": "never"},
        # "quiet": True,
        # "no_warnings": True,
        # "noprogress": True,
        "verbose": True,
        "ignoreerrors": "only_download",
        "proxy": f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@p.webshare.io:80/",
        "format": "18",
    }
    with yt_dlp.YoutubeDL(params=opts) as ydl:
        log.debug(f"yt_dlp downloading {channel_id}", channel_id=channel_id)

        info = {}
        try:
            info = ydl.extract_info(f"https://youtube.com/channel/{channel_id}/shorts")
            if not info:
                raise Exception("ydl: no info dict?")
            return dict(info)
        except RejectedVideoReached:
            log.debug("rejected video reached, end of date range or video seen 👍")
        except DownloadError as ex:
            log.error("yt_dlp download error", exc_info=ex)
        except Exception as ex:
            log.error("non-download error with shorts scraping?", exc_info=ex)
    return None


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

    def hook(d: dict[Any, Any]) -> None:
        if d.get("status") == "finished":
            status = backup_youtube_video(bucket, d["info_dict"])
            if status:
                register_download(d["info_dict"], org_ids)

                timestamp = d["info_dict"]["timestamp"]
                dt = datetime.fromtimestamp(timestamp)
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
