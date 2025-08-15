import contextlib
import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import structlog
import yt_dlp
from google.cloud.storage import Bucket

logger: structlog.BoundLogger = structlog.get_logger(__name__)

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
    return {Path(blob.name).stem for blob in bucket.list_blobs(prefix=prefix_path)}


def backup_keyword_entries(
    bucket: Bucket,
    keyword: str,
    cursor: datetime,
    existing: set[str],
) -> datetime:
    log = logger.bind()

    # returns list[object] because yt_dlp types are really inconsistent across extractors
    latest_seen = cursor
    prefix_path = str(STORAGE_PATH_PREFIX / keyword) + "/"

    log = log.bind(cursor=latest_seen, prefix_path=prefix_path)

    opts = {
        "dateafter": cursor.date(),
        "ignoreerrors": "only_download",
        "logtostderr": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        log.info(f"downloading entries for {keyword} to {prefix_path}")
        info = ydl.extract_info(f"ytsearchdate100:{keyword}", download=False)
        if not info:
            raise yt_dlp.utils.DownloadError("Empty info dict")

        entries = info.get("entries")
        if not isinstance(entries, list):
            raise yt_dlp.utils.DownloadError("No or malformed entries")

        log.debug(f"{len(entries)} entries found. iterating...")
        for entry in entries:
            log.bind(entry=entry)

            if not entry:
                log.debug(f"entry is none, continuing...")
                continue

            if entry.get("media_type") != "short":
                log.debug(f"ignoring non-short entry, continuing...")
                continue

            if entry["id"] in existing:
                log.debug(f"entry exists, continuing...")
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
            }
            buf = io.BytesIO()
            with contextlib.redirect_stdout(buf), yt_dlp.YoutubeDL(ctx) as video:
                log.debug(f"downloading to buffer {id(buf)}")
                video.download([entry["id"]])
            log.debug(f"video buffered. buffer size: {buf.tell()}")
            buf.seek(0)

            blob_path = prefix_path + str(entry["id"])

            log.bind(blob_path=blob_path)
            log.debug(f"uploading blob to path {blob_path}")
            bucket.blob(blob_path).upload_from_file(buf, content_type="video/mp4")

            upload_date = datetime.strptime(entry["upload_date"], "%Y%m%d")
            upload_date_utc = upload_date.replace(tzinfo=timezone.utc)
            latest_seen = max(latest_seen, upload_date_utc)
    return latest_seen


def check_entry_exists(video_id: str) -> bool:
    query = {"metadata": f'$.youtube_id == "{video_id}"'}
    with requests.post(
        f"{API_URL}/videos/filter",
        json=query,
        headers={"X-API-TOKEN": API_KEY},
    ) as resp:
        data = resp.json()
        if data.get("cursor"):
            return True
    return False
