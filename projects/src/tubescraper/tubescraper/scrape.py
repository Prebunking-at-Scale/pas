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


def destination_path(details: dict[Any, Any]) -> str:
    return f"{details['channel_id']}/{details['id']}.{details['ext']}"


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
    download = True
    for i, entry in enumerate(entries):
        log.bind(entry=entry)
        log.info(f"processing {i + 1} of {len(entries)} for {target}...")

        # Ideally we'd do some cursor checks here, however we don't get any
        # timestamp information as part of the entry, so we have to download
        # videos until we reach the cursor (or something older than it). We
        # can however stop if we've seen a video before
        existing_video = api_client.get_video(entry["id"], PLATFORM)
        download = download and not existing_video
        buf = io.BytesIO() if download else None

        try:
            if existing_video:
                # If we've seen less than a 10% growth in views, don't query for likes,
                # comments, etc.
                previous_views = int(existing_video.get("views", 0))
                current_views = int(entry.get("view_count", 0))
                log.info(f"prev views: {previous_views}, curr: {current_views}")
                if previous_views and (current_views / previous_views) < 1.1:
                    update_video_stats(entry, existing_video["id"])
                    continue

            details = video_details(entry["id"], buf)
            timestamp = datetime.fromtimestamp(details["timestamp"])
            if timestamp <= cursor:
                # Stop further video downloads if we're at the cursor value,
                # but continue re-scraping metadata
                download = False

            if not next_cursor or timestamp > next_cursor:
                next_cursor = timestamp

            if not existing_video and buf:
                blob_path = destination_path(details)
                storage_client.upload_blob(blob_path, buf)
                register_download(details, org_ids, blob_path)
                log.info("download successful", event_metric="download_success")

            if existing_video:
                update_video_stats(details, existing_video["id"])
                log.info("updating video details", video_id=existing_video["id"])

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
