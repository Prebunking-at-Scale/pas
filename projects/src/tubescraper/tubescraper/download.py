import mimetypes
import os
from pathlib import Path

import yt_dlp
from google.cloud.storage import Bucket

STORAGE_PATH_PREFIX = Path("tubescraper")


def download_channel(channel_name: str, output_directory: str, archive_path: Path) -> None:
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
        archive_path (Path):
            The file path to the download archive used to track downloaded content.
            Archive will be created if it does not exist.

    Raises:
        Exception: If the extracted info from YouTube is not a dictionary, indicating a potential failure
                   in retrieving channel data.

    """

    opts = {
        "download_archive": archive_path,
        "extract_flat": "discard_in_playlist",
        "fragment_retries": 10,
        # "ignoreerrors": "only_download",
        "outtmpl": {
            "default": f"{output_directory}/%(id)s.%(channel_id)s.%(timestamp)s.%(ext)s"
        },
        "postprocessors": [
            {"key": "FFmpegConcat", "only_multi_video": True, "when": "playlist"}
        ],
        "retries": 10,
        "subtitlesformat": "vtt/srt",
        "subtitleslangs": ["en.*"],
        "writeautomaticsub": True,
        "writesubtitles": True,
        "extractor_args": {"youtube": {"skip": ["translated_subs"]}},
        "color": {"stderr": "never", "stdout": "never"},
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        channel_source = channel_name
        if not channel_source.startswith("@"):
            channel_source = f"channel/{channel_name}"

        try:
            info = ydl.extract_info(f"https://youtube.com/{channel_source}/shorts")
            if not isinstance(info, dict):
                raise Exception("ydl: no info dict?")
        except yt_dlp.DownloadError:
            pass


def download_archivefile(bucket: Bucket, path: Path) -> None:
    """Downloads a yt_dlp archive file from GCS if it exists.

    Args:
        bucket (Bucket): The GCS bucket to download from.
        path (Path): Local path to save the archive file.
    """
    archive_path: Path = STORAGE_PATH_PREFIX / path
    archive_blob = bucket.get_blob(archive_path)
    if not archive_blob:
        return

    archive_blob.download_to_filename(filename=path)


def backup_channel(bucket: Bucket, channel_name: str, source_directory: str) -> None:
    """Uploads downloaded files from a channel to Google Cloud Storage.

    Args:
        bucket (Bucket): GCS bucket to upload to.
        channel_name (str): Name of the YouTube channel for path organisation.
        source_directory (str): Local directory containing files to upload.
    """
    for filename in os.listdir(source_directory):
        source_path: Path = Path(source_directory, filename)
        target_path: Path = STORAGE_PATH_PREFIX / channel_name / filename

        blob = bucket.blob(target_path)
        type, _ = mimetypes.guess_file_type(source_path)
        blob.upload_from_file(source_path, content_type=type)


def backup_archivefile(bucket: Bucket, path: Path) -> None:
    """Uploads a download archive file to Google Cloud Storage."""
    blob = bucket.blob(path)
    blob.upload_from_filename(path)
