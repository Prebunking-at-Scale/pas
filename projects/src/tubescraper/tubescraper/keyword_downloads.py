import contextlib
import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import yt_dlp
from google.cloud.storage import Bucket
from yt_dlp.utils import DateRange

API_URL = os.environ["API_URL"]
API_KEYS = os.environ["API_KEYS"]
API_KEY = json.loads(API_KEYS).pop()
STORAGE_PATH_PREFIX = Path("tubescraper/keywords")


def download_cursor(bucket: Bucket, keyword: str) -> datetime:
    cursor_path = str(STORAGE_PATH_PREFIX / keyword / "cursor")
    cursor_blob = bucket.blob(cursor_path)
    if not cursor_blob.exists():
        return datetime.now(timezone.utc) - timedelta(days=1)
    cursor = cursor_blob.download_as_text()
    return datetime.fromisoformat(cursor).replace(tzinfo=timezone.utc)


def backup_cursor(bucket: Bucket, keyword: str, cursor: datetime):
    cursor_path = str(STORAGE_PATH_PREFIX / keyword / "cursor")
    cursor_blob = bucket.blob(cursor_path)
    cursor_blob.upload_from_string(cursor.isoformat())


def download_existing_ids(bucket: Bucket, keyword: str) -> set[str]:
    prefix_path = str(STORAGE_PATH_PREFIX / keyword) + "/"
    return {blob.name.stem for blob in bucket.list_blobs(prefix=prefix_path)}


def backup_keyword_entries(
    bucket: Bucket,
    output_directory: str,
    keyword: str,
    cursor: datetime,
    existing: set[str],
) -> datetime:
    # returns list[object] because yt_dlp types are really inconsistent across extractors
    latest_seen = cursor
    prefix_path = str(STORAGE_PATH_PREFIX / keyword) + "/"

    opts = {
        "format": "worstvideo[ext=mp4]+worstaudio[ext=m4a]/mp4",
        "daterange": DateRange(cursor.date()),
        "skip_download": True,
        "outtmpl": {
            "default": f"{output_directory}/%(id)s.%(channel_id)s.%(timestamp)s.%(ext)s"
        },
        'ignoreerrors': 'only_download'
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearchdate100:{keyword}", download=False)
        if not info:
            raise yt_dlp.utils.DownloadError("Empty info dict")

        entries = info.get("entries")
        if not isinstance(entries, list):
            raise yt_dlp.utils.DownloadError("No or malformed entries")

        for entry in entries:
            if entry["id"] in existing:
                continue

            _ = ydl.process_info(entry)
            blob_path = prefix_path + str(entry["id"])
            bucket.blob(blob_path).upload_from_file(
                ,
                rewind=True,
                content_type="video/mp4",
            )

            upload_date = datetime.strptime(entry["upload_date"], "%Y%m%d")
            upload_date_utc = upload_date.replace(tzinfo=timezone.utc)
            latest_seen = max(latest_seen, upload_date_utc)
    return latest_seen
