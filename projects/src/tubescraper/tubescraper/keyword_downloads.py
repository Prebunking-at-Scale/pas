import contextlib
import io
import json
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import structlog
import yt_dlp
from google.cloud.storage import Bucket
from tubescraper.channel_downloads import POT_PROVIDER_URL
from tubescraper.hardcoded_channels import OrgName
from tubescraper.register import register_download
from yt_dlp import DownloadError, ImpersonateTarget

logger: structlog.BoundLogger = structlog.get_logger(__name__)

API_URL = os.environ["API_URL"]
API_KEYS = os.environ["API_KEYS"]
API_KEY = json.loads(API_KEYS).pop()
PROXY_COUNT = int(os.environ["PROXY_COUNT"])
PROXY_USERNAME = os.environ["PROXY_USERNAME"]
PROXY_PASSWORD = os.environ["PROXY_PASSWORD"]
STORAGE_PATH_PREFIX = Path("tubescraper/keywords")


def proxy_addr() -> str:
    proxy_id = random.randrange(1, PROXY_COUNT, 1)
    logger.debug(f"using proxy id {proxy_id}")
    return f"http://{PROXY_USERNAME}-{proxy_id}:{PROXY_PASSWORD}@p.webshare.io:80/"


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


def download_existing_ids_for_keyword(bucket: Bucket, keyword: str) -> set[str]:
    prefix_path = str(STORAGE_PATH_PREFIX / keyword) + "/"
    return {Path(blob.name).stem for blob in bucket.list_blobs(prefix=prefix_path)}


def backup_keyword_entries(
    bucket: Bucket,
    keyword: str,
    cursor: datetime,
    existing: set[str],
    orgs: list[OrgName],
) -> datetime:
    log = logger.new()

    # returns list[object] because yt_dlp types are really inconsistent across extractors
    latest_seen = cursor
    prefix_path = str(STORAGE_PATH_PREFIX / keyword) + "/"

    log = log.bind(cursor=latest_seen, prefix_path=prefix_path)

    opts = {
        # "dateafter": cursor.date(),
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
        log.info(f"downloading entries for {keyword} to {prefix_path}")
        info = ydl.extract_info(
            f'https://www.youtube.com/results?search_query="{keyword}"&sp=CAISBggEEAEYAQ%253D%253D',
            download=False,
        )

        if not info:
            raise yt_dlp.utils.DownloadError("Empty info dict")

        entries = info.get("entries")
        if not isinstance(entries, list):
            raise yt_dlp.utils.DownloadError("No or malformed entries")

        log.debug(f"{len(entries)} entries found. iterating...")
        for i, entry in enumerate(entries):
            log.bind(entry=entry)

            log.info(f"processing {i} of {len(entries)} for keyword {keyword}...")
            if not entry:
                log.debug("entry is none, continuing...")
                continue

            if "/shorts/" not in entry.get("url", ""):
                log.debug("ignoring non-short entry, continuing...")
                continue

            if entry["id"] in existing:
                log.debug("entry exists, continuing...")
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
            }
            buf = io.BytesIO()
            with contextlib.redirect_stdout(buf), yt_dlp.YoutubeDL(ctx) as video:
                log.debug(f"downloading to buffer {id(buf)}")
                try:
                    downloaded = video.extract_info(entry["id"])  # fmt: skip  # extract_info again to use the POT server (duh?)
                except DownloadError as ex:
                    log.error("yt_dlp download error, skipping", exc_info=ex)
                    continue
                except Exception as ex:
                    log.error(
                        "non-download error with shorts scraping?, skipping", exc_info=ex
                    )
                    continue

                log.debug(f"video buffered. buffer size: {buf.tell()}")
                buf.seek(0)

                if not downloaded:
                    log.debug("downloaded is none, continuing...")
                    continue

                blob_path = prefix_path + str(downloaded["id"])

                log.bind(blob_path=blob_path)
                log.debug(f"uploading blob to path {blob_path}")
                bucket.blob(blob_path).upload_from_file(buf, content_type="video/mp4")
                buf.close()

                register_download(downloaded, orgs)

    return latest_seen
