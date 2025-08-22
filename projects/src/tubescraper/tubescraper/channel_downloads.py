import mimetypes
import os
from pathlib import Path
from typing import Any

import structlog
import yt_dlp
import yt_dlp.utils
from google.cloud.storage import Bucket
from yt_dlp.networking.impersonate import ImpersonateTarget
from yt_dlp.utils import DownloadError

logger: structlog.BoundLogger = structlog.get_logger(__name__)


POT_PROVIDER_URL = os.environ["POT_PROVIDER_URL"]
PROXY_USERNAME = os.environ["PROXY_USERNAME"]
PROXY_PASSWORD = os.environ["PROXY_PASSWORD"]
STORAGE_PATH_PREFIX = Path("tubescraper")


def download_channel(
    channel_name: str, output_directory: str, archivefile: str
) -> dict[Any, Any] | None:
    """Downloads YouTube Shorts from a specified channel using yt_dlp with custom options.

    This function connects to YouTube and downloads Shorts content from the specified
    channel.  It uses a download archive to avoid re-downloading already processed
    content. Video and subtitle options are configured to ensure consistent output and
    error resilience.  It extracts both manual and auto-generated subtitles. Translated
    subtitles are skipped via extractor arguments.

    Args:
        channel_name (str):
            The custom URL name of the YouTube channel (e.g., '@ChannelName').
        output_directory (str):
            The directory path where downloaded files will be saved.
        archivefile (str):
            The file path to the download archive used to track downloaded content.
            Archive will be created if it does not exist.

    Raises:
        DownloadError:
            Some yt-dlp specific error downloading from YouTube.
        Exception:
            If the extracted info from YouTube is not a dictionary, indicating a potential failure in retrieving
            channel data.

    """
    log = logger.bind()

    opts = {
        "download_archive": archivefile,
        "fragment_retries": 10,
        "daterange": yt_dlp.utils.DateRange("today-1month", "today"),  # type: ignore
        "outtmpl": {
            "default": f"{output_directory}/%(id)s.%(channel_id)s.%(timestamp)s.%(ext)s"
        },
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
        channel_source = channel_name
        if not channel_source.startswith("@"):
            channel_source = f"channel/{channel_name}"
        log.debug(f"yt_dlp downloading {channel_source}", channel_source=channel_source)

        info = {}
        try:
            info = ydl.extract_info(f"https://youtube.com/{channel_source}/shorts")
            if not info:
                raise Exception("ydl: no info dict?")
            return dict(info)
        except DownloadError as ex:
            log.error("yt_dlp download error", exc_info=ex)
        except Exception as ex:
            log.error("non-download error with shorts scraping?", exc_info=ex)


def download_archivefile(bucket: Bucket, archivefile: str) -> None:
    """Downloads a yt_dlp archive file from GCS if it exists.

    Args:
        bucket (Bucket): The GCS bucket to download from.
        path (Path): Local path to save the archive file.
    """
    log = logger.bind(archive_file=archivefile)

    archive_path = str(STORAGE_PATH_PREFIX / archivefile)
    archive_blob = bucket.get_blob(archive_path)
    if (archive_blob and not archive_blob.exists()) or not archive_blob:
        log.debug(f"no archive for channel at {archivefile}")
        return

    log.debug(f"downloading archive from {archive_path}")
    archive_blob.download_to_filename(filename=archivefile)


def backup_channel(bucket: Bucket, channel_name: str, source_directory: str) -> None:
    """Uploads downloaded files from a channel to Google Cloud Storage.

    Args:
        bucket (Bucket): GCS bucket to upload to.
        channel_name (str): Name of the YouTube channel for path organisation.
        source_directory (str): Local directory containing files to upload.
    """
    log = logger.bind(channel_name=channel_name, source_directory=source_directory)
    for filename in os.listdir(source_directory):
        source_path: str = str(Path(source_directory, filename))
        target_path: str = str(STORAGE_PATH_PREFIX / channel_name / filename)

        blob = bucket.blob(target_path)
        type, _ = mimetypes.guess_file_type(source_path)

        log = log.bind(filename=filename, target_path=target_path, content_type=type)
        log.debug(f"backing up {filename} to {target_path}")
        blob.upload_from_filename(source_path, content_type=type)


def backup_archivefile(bucket: Bucket, archivefile: str) -> None:
    """Uploads a download archive file to Google Cloud Storage."""
    logger.debug("backing up archive to storage bucket", archive_file=archivefile)

    if not os.path.exists(archivefile):
        return

    backup_path = str(STORAGE_PATH_PREFIX / archivefile)
    blob = bucket.blob(backup_path)
    blob.upload_from_filename(archivefile)
