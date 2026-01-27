import json
import os
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from scraper_common import CoreAPIClient, Platform, Video

logger: structlog.BoundLogger = structlog.get_logger(__name__)

API_URL = os.environ.get("API_URL", "http://localhost:8000/")
API_KEY = json.loads(os.environ.get("API_KEYS", '["abc123"]'))[0]
PLATFORM: Platform = "youtube"

api_client = CoreAPIClient(API_URL, API_KEY)


def register_download(
    entry: dict[Any, Any], org_ids: list[UUID], destination_path: str
) -> bool:
    """Register a downloaded YouTube video with the API.

    Returns:
        True if registered successfully, False otherwise.
    """
    if not entry:
        return False

    entry_id = entry.get("id")
    if entry_id is None:
        logger.error("found channel entry without video_id? continuing")
        return False

    if not entry.get("video_ext"):
        logger.warning(f"we didn't download video {entry_id}, skipping")
        return False

    uploaded_at = datetime.fromtimestamp(entry["timestamp"])
    video = Video(
        platform_video_id=entry_id,
        org_ids=org_ids,
        channel=entry.get("uploader_id"),
        channel_followers=entry.get("channel_follower_count") or 0,
        comments=entry.get("comment_count") or 0,
        description=entry.get("description"),
        destination_path=destination_path,
        likes=entry.get("like_count") or 0,
        platform=PLATFORM,
        source_url=entry.get("webpage_url"),
        title=entry.get("title"),
        uploaded_at=uploaded_at.isoformat(),
        views=entry.get("view_count") or 0,
    )

    return api_client.register_video_entry(video)


def update_video_stats(entry: dict[Any, Any], video_id: str = "") -> bool:
    """Updates the stats for a video.

    Returns:
        True if the stats are updated. False if not (e.g. because it doesn't exist)"""
    if not video_id:
        video = api_client.get_video(entry["id"], PLATFORM)
        if not video:
            return False
        video_id = video["id"]

    api_client.update_video_stats(
        id=video_id,
        views=entry.get("view_count") or 0,
        likes=entry.get("like_count") or 0,
        comments=entry.get("comment_count") or 0,
        channel_followers=entry.get("channel_follower_count") or 0,
    )
    return True


def fetch_cursor(target: str) -> datetime:
    """Fetches the current cursor (last_video_datetime) for a given channel."""
    cursor = api_client.fetch_cursor(target, PLATFORM)
    if cursor and (cursor_date := cursor.get("last_video_datetime")):
        return datetime.fromisoformat(cursor_date)
    return datetime.now() - timedelta(days=14)


def update_cursor(target: str, dt: datetime) -> None:
    """Updates the stored cursor for a given channel."""
    api_client.update_cursor(target, PLATFORM, {"last_video_datetime": dt.isoformat()})
