import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import structlog
from tubescraper.hardcoded_channels import OrgName

logger: structlog.BoundLogger = structlog.get_logger(__name__)

API_URL = os.environ["API_URL"]
API_KEYS = os.environ["API_KEYS"]
API_KEY = json.loads(API_KEYS).pop()
STORAGE_PATH_PREFIX = Path("tubescraper")


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


def register_downloads(
    info: dict[str, Any],
    orgs: list[OrgName],
) -> None:
    log = logger.bind()

    entries = info.get("entries", [])
    log.debug(f"registering {len(entries)} videos with API")
    for entry in entries:
        register_download(entry, orgs)


def register_download(entry: dict[Any, Any], orgs: list[OrgName]) -> None:
    log = logger.bind(entry=entry)

    if not entry:
        return

    entry_id = entry.get("id")
    if entry_id is None:
        log.error("found channel entry without video_id? continuing")
        return

    try:
        if check_entry_exists(entry_id):
            return
    except Exception:
        log.warning(f"Couldn't check if id exists {entry.get('id')}")

    channel_id = entry.get("channel_id", "")
    if not channel_id:
        log.warning(f"no channel_id set for video {entry_id}, setting it to 'unknown'")
        channel_id = "unknown"

    filename = f"{entry.get('id')}.{entry.get('channel_id')}.{entry.get('timestamp')}.{entry.get('ext')}"
    filepath = str(STORAGE_PATH_PREFIX / channel_id / filename)
    log = log.bind(filename=filename, filepath=filepath)

    uploaded_at = None
    if upload_date := entry.get("upload_date"):
        uploaded_at = datetime.strptime(upload_date, "%Y%m%d").replace(
            tzinfo=timezone.utc
        )

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
            uploaded_at.isoformat()
            if isinstance(uploaded_at, datetime)
            else uploaded_at
        ),
        "views": entry.get("view_count") or 0,
        "metadata": {
            "for_organisation": orgs,
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
