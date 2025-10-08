import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import requests
import structlog
from tokscraper.types import CORE_API, Cursor

logger: structlog.BoundLogger = structlog.get_logger(__name__)

API_URL = os.environ["API_URL"]
API_KEYS = os.environ["API_KEYS"]
API_KEY = json.loads(API_KEYS).pop()
STORAGE_PATH_PREFIX = Path("tokscraper")


def register_download(entry: dict[Any, Any], org_id: UUID) -> None:
    log = logger.bind(entry=entry)

    if not entry:
        return None

    entry_id = entry.get("id")
    if entry_id is None:
        log.error("found channel entry without video_id? continuing")
        return None

    if not entry.get("video_ext"):
        log.warning(f"we didn't download video {entry_id}, skipping")
        return None

    channel_id = entry.get("channel_id", "")
    if not channel_id:
        log.warning(f"no channel_id set for video {entry_id}, setting it to 'unknown'")
        channel_id = "unknown"

    filename = f"{entry.get('id')}.{entry.get('channel_id')}.{entry.get('timestamp')}.{entry.get('ext')}"
    filepath = str(STORAGE_PATH_PREFIX / channel_id / filename)
    log = log.bind(filename=filename, filepath=filepath)

    uploaded_at = None
    if upload_date := entry.get("upload_date"):
        uploaded_at = datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=timezone.utc)

    data: dict[str, Any] = {
        "channel": entry.get("uploader_id"),
        "channel_followers": entry.get("channel_follower_count") or 0,
        "comments": entry.get("comment_count") or 0,
        "description": entry.get("description"),
        "destination_path": filepath,
        "likes": entry.get("like_count") or 0,
        "platform": "tiktok",
        "source_url": entry.get("webpage_url"),
        "title": entry.get("title"),
        "uploaded_at": (
            uploaded_at.isoformat() if isinstance(uploaded_at, datetime) else uploaded_at
        ),
        "views": entry.get("view_count") or 0,
        "metadata": {
            "for_organisation": [org_id],
            "youtube_id": entry_id,
        },
    }

    try:
        with requests.post(
            f"{API_URL}/videos", json=data, headers={"X-API-TOKEN": API_KEY}
        ) as resp:
            log.debug(f"registered {entry.get('id')} with API", data=data)
            resp.raise_for_status()

    except Exception as ex:
        log.error(
            f"couldn't post to video api, video_id: {entry['id']}",
            exc_info=ex,
            entry=entry,
        )


def fetch_cursor(target: str, platform: str) -> datetime | None:
    """Fetches the current cursor for a given channel and platform from the core API.

    Args:
        target (str): The channel identifier.
        platform (str): The platform name, e.g., "youtube".

    Returns:
        datetime: The cursor timestamp for the given channel and platform.

    """
    try:
        with requests.get(
            f"{CORE_API}/cursors/{target}/{platform}",
            headers={"X-API-TOKEN": API_KEY},
        ) as resp:
            resp.raise_for_status()
            cursor = Cursor(**resp.json())
            cursor_date = str(cursor.cursor)
            return datetime.fromisoformat(cursor_date)
    except requests.HTTPError as ex:
        if ex.response.status_code == 404:
            return None
        raise ex


def update_cursor(target: str, platform: str, dt: datetime) -> None:
    """Updates the stored cursor for a given channel and platform in the core API.

    Args:
        target (str): The channel identifier.
        platform (str): The platform name, e.g., "youtube".
        dt (datetime): The new cursor timestamp to store.

    """
    with requests.post(
        url=f"{CORE_API}/cursors/{target}/{platform}",
        json=dt.isoformat(),
        headers={"X-API-TOKEN": API_KEY},
    ) as resp:
        resp.raise_for_status()
    return
