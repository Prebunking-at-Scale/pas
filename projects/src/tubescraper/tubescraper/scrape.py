import io
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog
from scraper_common.storage import StorageClient

from tubescraper.coreapi import (
    PLATFORM,
    api_client,
    register_download,
    update_video_stats,
)
from tubescraper.youtube import video_details


logger: structlog.BoundLogger = structlog.get_logger(__name__)


def blob_name(details: dict[Any, Any]) -> str:
    return f"{details['channel_id']}/{details['id']}.{details['ext']}"


def rescrape_short(video: dict[Any, Any]) -> None:
    try:
        details = video_details(video["source_url"])
    except Exception:
        # Even if the above fails, we still want to update the last
        # scrape time to prevent us from trying to scrape this
        # video forever
        details = {}
    update_video_stats(details, video["id"])


def scrape_shorts(
    entries: list[dict[Any, Any]],
    cursor: datetime,
    storage_client: StorageClient,
    target: str,
    org_ids: list[UUID],
) -> datetime | None:
    log = logger.new(target=target, cursor=cursor)
    next_cursor = None

    log.debug(f"{len(entries)} shorts found for {target}")
    for i, entry in enumerate(entries):
        log.bind(entry=entry)
        log.info(f"processing {i + 1} of {len(entries)} for {target}...")

        # Ideally we'd do some cursor checks here, however we don't get any
        # timestamp information as part of the entry, so we have to download
        # videos until we reach the cursor (or something older than it). We
        # can however stop if we've seen a video before
        existing_video = api_client.get_video(entry["id"], PLATFORM)
        buf = io.BytesIO() if not existing_video else None

        try:
            if existing_video:
                # If we've seen less than a 10% growth in views, don't query for likes,
                # comments, etc.

                # This looks odd, but some videos really do have 0 views, and that
                # causes issues (like division by 0) and we're trying to avoid that.
                previous_views = max(int(existing_video.get("views", 0)), 1)
                current_views = int(entry.get("view_count", 0))
                log.debug(f"prev views: {previous_views}, curr: {current_views}")
                if current_views / previous_views >= 1.1:
                    update_video_stats(entry, existing_video["id"])
                continue

            details = video_details(entry["id"], buf)
            if buf:
                destination_path = storage_client.upload_blob(blob_name(details), buf)
                register_download(details, org_ids, destination_path)
                log.info("download successful", event_metric="download_success")

            timestamp = datetime.fromtimestamp(details["timestamp"])
            if not next_cursor or timestamp > next_cursor:
                next_cursor = timestamp

        except Exception as ex:
            log.error(
                "exception with downloading, skipping entry",
                event_metric="download_failure",
                exc_info=ex,
            )
        finally:
            if buf:
                buf.close()

    return next_cursor
