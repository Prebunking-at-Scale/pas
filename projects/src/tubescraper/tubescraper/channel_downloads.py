import mimetypes
import os
from pathlib import Path, PurePath
from typing import Any, Callable

import structlog
import yt_dlp
import yt_dlp.utils
from google.cloud.storage import Bucket
from tubescraper.hardcoded_channels import OrgName
from tubescraper.register import register_download
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
    archivefile: str,
    bucket: Bucket,
    orgs: list[OrgName],
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
        "break_on_reject": True,
        "outtmpl": {
            "default": f"{output_directory}/%(id)s.%(channel_id)s.%(timestamp)s.%(ext)s"
        },
        "progress_hooks": [progress_hook_register(bucket, orgs)],
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


def progress_hook_register(
    bucket: Bucket, orgs: list[OrgName]
) -> Callable[[dict[str, Any]], None]:
    def hook(d: dict[Any, Any]) -> None:
        if d["status"] == "finished":
            if backup_youtube_video(bucket, d["info_dict"]):
                register_download(d["info_dict"], orgs)

    return hook


def fix_archivefile(bucket: Bucket, archivefile: str, channel_id: str) -> None:
    """
    Ensure the yt-dlp archive file exists. If missing, reconstruct it by
    listing objects in the given bucket under the channel prefix and writing
    video IDs in yt-dlp archive format.
    """
    log = logger.bind(archive_file=archivefile, channel_id=channel_id)

    if os.path.exists(archivefile):
        log.info("Archive file already exists, skipping build")
        return

    log.info("Building archive file from bucket contents")
    prefix_path = str(STORAGE_PATH_PREFIX / channel_id) + "/"
    filenames = [PurePath(blob.name).name for blob in bucket.list_blobs(prefix=prefix_path)]
    log.debug("Collected filenames from bucket", count=len(filenames))

    with open(archivefile, "w") as fh:
        for filename in filenames:
            video_id, *_ = filename.split(".")
            fh.write(f"youtube {video_id}\n")

    log.info("Archive file successfully built", entries=len(filenames))
    return


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


def backup_youtube_video(bucket: Bucket, info: dict[str, Any]) -> bool:
    """Uploads downloaded files from a channel to Google Cloud Storage.

    Args:
        bucket (Bucket): GCS bucket to upload to.
        channel_name (str): Name of the YouTube channel for path organisation.
        source_directory (str): Local directory containing files to upload.
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


def backup_archivefile(bucket: Bucket, archivefile: str) -> None:
    """Uploads a download archive file to Google Cloud Storage."""
    logger.debug("backing up archive to storage bucket", archive_file=archivefile)

    if not os.path.exists(archivefile):
        return

    backup_path = str(STORAGE_PATH_PREFIX / archivefile)
    blob = bucket.blob(backup_path)
    blob.upload_from_filename(archivefile)
