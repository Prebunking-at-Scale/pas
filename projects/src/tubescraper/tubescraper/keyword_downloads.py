import contextlib
import io
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import requests
import structlog
import yt_dlp
from google.cloud.storage import Bucket
from tubescraper.channel_downloads import POT_PROVIDER_URL
from tubescraper.register import API_KEY, proxy_addr, register_download, update_cursor
from tubescraper.types import CORE_API, KeywordFeed
from yt_dlp import DownloadError, ImpersonateTarget
from yt_dlp.utils import RejectedVideoReached

logger: structlog.BoundLogger = structlog.get_logger(__name__)

STORAGE_PATH_PREFIX = Path("tubescraper/keywords")


def backup_keyword_entries(
    bucket: Bucket,
    keyword: str,
    cursor: datetime,
    org_ids: list[UUID],
) -> None:
    log = logger.new()

    # returns list[object] because yt_dlp types are really inconsistent across extractors
    latest_seen = cursor
    prefix_path = str(STORAGE_PATH_PREFIX / keyword) + "/"

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
        log.info(f"downloading entries for {keyword} to {prefix_path}")
        info = ydl.extract_info(
            # the sp parameter is a pre-computed search query that gives
            # videos of length under 4 minutes, sorted by most recent.
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
                "break_on_reject": True,
            }
            buf = io.BytesIO()
            with contextlib.redirect_stdout(buf), yt_dlp.YoutubeDL(ctx) as video:  # type: ignore
                log.debug(f"downloading to buffer {id(buf)}")
                try:
                    downloaded = video.extract_info(entry["id"])  # fmt: skip  # extract_info again to use the POT server (duh?)
                    downloaded = cast(dict[Any, Any], downloaded)
                except RejectedVideoReached as ex:
                    log.error("video out of date range, skipping", exc_info=ex)
                    break  # stop iteration
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

                blob_path = prefix_path + str(downloaded["id"])

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
                if dt > cursor:
                    update_cursor(keyword, dt)


def fetch_keyword_feeds() -> list[KeywordFeed]:
    with requests.get(
        f"{CORE_API}/media_feeds/keywords",
        headers={"X-API-TOKEN": API_KEY},
    ) as resp:
        resp.raise_for_status()
        data = resp.json()["data"]
        return [KeywordFeed(**feed) for feed in data]


type KeywordResults = dict[str, list[UUID]]


def preprocess_keyword_feeds(feeds: list[KeywordFeed]) -> KeywordResults:
    """Deduplicates organisation ids from the feeds. We should probably do this in the
    api.
    """
    result: KeywordResults = {}
    for feed in feeds:
        for keyword in feed.keywords:
            result[keyword] = result.get(keyword, []) + [feed.organisation_id]

    return result
