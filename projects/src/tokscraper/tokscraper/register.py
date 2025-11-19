import json
import os
import random
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import requests
import structlog
from requests.exceptions import HTTPError
from tokscraper.types import CORE_API, Cursor

logger: structlog.BoundLogger = structlog.get_logger(__name__)

API_URL = os.environ["API_URL"]
API_KEYS = os.environ["API_KEYS"]
API_KEY = json.loads(API_KEYS).pop()
STORAGE_PATH_PREFIX = Path("tokscraper")
PROXY_COUNT = int(os.environ["PROXY_COUNT"])
PROXY_USERNAME = os.environ["PROXY_USERNAME"]
PROXY_PASSWORD = os.environ["PROXY_PASSWORD"]


def proxy_details() -> tuple[str, int]:
    proxy_id = random.randrange(1, PROXY_COUNT, 1)
    logger.debug(f"using proxy id {proxy_id}")
    return (
        f"http://{PROXY_USERNAME}-{proxy_id}:{PROXY_PASSWORD}@p.webshare.io:80/",
        proxy_id,
    )


def check_entry_exists(video_id: str) -> bool:
    query = {"metadata": f'$.tiktok_id == "{video_id}"'}
    with requests.post(
        f"{API_URL}/videos/filter",
        json=query,
        headers={"X-API-TOKEN": API_KEY},
    ) as resp:
        data = resp.json()
        if data.get("data"):
            return True
    return False


def register_download(
    entry: dict[Any, Any], org_ids: list[UUID], destination_path: str
) -> None:
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

    log = log.bind(destination_path=destination_path)

    uploaded_at = None
    if upload_date := entry.get("upload_date"):
        uploaded_at = datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=timezone.utc)

    data: dict[str, Any] = {
        "channel": entry.get("channel"),
        "channel_followers": entry.get("channel_follower_count") or 0,
        "comments": entry.get("comment_count") or 0,
        "description": entry.get("description"),
        "destination_path": destination_path,
        "likes": entry.get("like_count") or 0,
        "platform": "tiktok",
        "source_url": entry.get("url"),
        "title": entry.get("title"),
        "uploaded_at": (
            uploaded_at.isoformat() if isinstance(uploaded_at, datetime) else uploaded_at
        ),
        "views": entry.get("view_count") or 0,
        "metadata": {
            "for_organisation": [str(id) for id in org_ids],
            "tiktok_id": entry_id,
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


def make_safe_cursor_target(target: str) -> str:
    target = target.replace("/", "-").strip()
    return urllib.parse.quote(target, safe="")


def fetch_cursor(target: str, platform: str = "tiktok") -> datetime | None:
    """Fetches the current cursor for a given channel and platform from the core API.

    Args:
        target (str): The channel identifier.
        platform (str): The platform name, e.g., "tiktok".

    Returns:
        datetime: The cursor timestamp for the given channel and platform.
        None: No cursor exists for this channel/platform.

    """
    try:
        target = make_safe_cursor_target(target)
        with requests.get(
            f"{CORE_API}/media_feeds/cursors/{target}/{platform}",
            headers={"X-API-TOKEN": API_KEY},
        ) as resp:
            resp.raise_for_status()
            data = resp.json()["data"]
            cursor = Cursor(**data)
            if "last_video_datetime" in cursor.cursor:
                if cursor_date := cursor.cursor.get("last_video_datetime"):
                    return datetime.fromisoformat(cursor_date)
    except HTTPError as ex:
        if ex.response.status_code == 404:
            return None
        raise ex


def update_cursor(target: str, dt: datetime, platform: str = "tiktok") -> None:
    """Updates the stored cursor for a given channel and platform in the core API.

    Args:
        target (str): The channel identifier.
        platform (str): The platform name, e.g., "tiktok".
        dt (datetime): The new cursor timestamp to store.

    """
    log = logger.bind()
    target = make_safe_cursor_target(target)
    log.debug("updating cursor", cursor=dt, target=target)
    with requests.post(
        url=f"{CORE_API}/media_feeds/cursors/{target}/{platform}",
        json={
            "last_video_datetime": dt.isoformat(),
        },
        headers={"X-API-TOKEN": API_KEY},
    ) as resp:
        resp.raise_for_status()
    return
