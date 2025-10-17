import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import requests
import structlog
from requests.exceptions import HTTPError
from tubescraper.types import CORE_API, Cursor

logger: structlog.BoundLogger = structlog.get_logger(__name__)

API_URL = os.environ["API_URL"]
API_KEYS = os.environ["API_KEYS"]
API_KEY = json.loads(API_KEYS).pop()
STORAGE_PATH_PREFIX = Path("tubescraper")
PROXY_COUNT = int(os.environ["PROXY_COUNT"])
PROXY_USERNAME = os.environ["PROXY_USERNAME"]
PROXY_PASSWORD = os.environ["PROXY_PASSWORD"]


def proxy_addr() -> str:
    proxy_id = random.randrange(1, PROXY_COUNT, 1)
    logger.debug(f"using proxy id {proxy_id}")
    return f"http://{PROXY_USERNAME}-{proxy_id}:{PROXY_PASSWORD}@p.webshare.io:80/"


def check_entry_exists(video_id: str) -> bool:
    query = {"metadata": f'$.youtube_id == "{video_id}"'}
    with requests.post(
        f"{API_URL}/videos/filter",
        json=query,
        headers={"X-API-TOKEN": API_KEY},
    ) as resp:
        data = resp.json()
        if data.get("data"):
            return True
    return False


def register_download(entry: dict[Any, Any], org_ids: list[UUID]) -> None:
    log = logger.bind(entry=entry)

    if not entry:
        return None

    entry_id = entry.get("id")
    if entry_id is None:
        log.error("found channel entry without video_id? continuing")
        return None

    try:
        if check_entry_exists(entry_id):
            return None
    except Exception:
        log.warning(f"Couldn't check if id exists {entry.get('id')}")

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
        "channel_followers": entry.get("channel_follower_count"),
        "comments": entry.get("comment_count") or 0,
        "description": entry.get("description"),
        "destination_path": filepath,
        "likes": entry.get("like_count") or 0,
        "platform": "youtube",
        "source_url": entry.get("webpage_url"),
        "title": entry.get("title"),
        "uploaded_at": (
            uploaded_at.isoformat() if isinstance(uploaded_at, datetime) else uploaded_at
        ),
        "views": entry.get("view_count") or 0,
        "metadata": {
            "for_organisation": [str(id) for id in org_ids],
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


def fetch_cursor(target: str, platform: str = "youtube") -> datetime | None:
    """Fetches the current cursor for a given channel and platform from the core API.

    Args:
        target (str): The channel identifier.
        platform (str): The platform name, e.g., "youtube".

    Returns:
        datetime: The cursor timestamp for the given channel and platform.
        None: No cursor exists for this channel/platform.

    """
    try:
        with requests.get(
            f"{CORE_API}/media_feeds/cursors/{target}/{platform}",
            headers={"X-API-TOKEN": API_KEY},
        ) as resp:
            resp.raise_for_status()
            data = resp.json()["data"]
            cursor = Cursor(**data)
            cursor_date = str(cursor.cursor)
            return datetime.fromisoformat(cursor_date)
    except HTTPError as ex:
        if ex.response.status_code == 404:
            return None
        raise ex


def update_cursor(target: str, dt: datetime, platform: str = "youtube") -> None:
    """Updates the stored cursor for a given channel and platform in the core API.

    Args:
        target (str): The channel identifier.
        platform (str): The platform name, e.g., "youtube".
        dt (datetime): The new cursor timestamp to store.

    """
    with requests.post(
        url=f"{CORE_API}/media_feeds/cursors/{target}/{platform}",
        json=dt.isoformat(),
        headers={"X-API-TOKEN": API_KEY},
    ) as resp:
        resp.raise_for_status()
    return
