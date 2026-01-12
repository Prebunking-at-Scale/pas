import abc
import json
import os
import urllib.parse
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from instascraper.instagram import Reel
import requests
import structlog
from pydantic import BaseModel
from requests.exceptions import HTTPError

API_URL = os.environ.get("API_URL", "http://localhost:3000/")
API_KEY = json.loads(os.environ.get("API_KEYS", '["abc123"]'))[0]

logger: structlog.BoundLogger = structlog.get_logger(__name__)


Platform = Literal["youtube", "instagram", "tiktok"]


class MediaFeed(BaseModel, abc.ABC):
    id: UUID
    organisation_id: UUID
    is_archived: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ChannelFeed(MediaFeed):
    channel: str
    platform: Platform


class KeywordFeed(MediaFeed):
    topic: str
    keywords: list[str]


class Cursor(BaseModel):
    id: UUID
    target: str
    platform: Platform
    cursor: dict = {}
    created_at: datetime | None = None
    updated_at: datetime | None = None


def fetch_channel_feeds() -> list[ChannelFeed]:
    with requests.get(
        f"{API_URL}/media_feeds/channels",
        headers={"X-API-TOKEN": API_KEY},
    ) as resp:
        resp.raise_for_status()
        data = resp.json()["data"]
        return [ChannelFeed(**feed) for feed in data]


def check_entry_exists(video_id: str) -> bool:
    query = {"metadata": f'$.instagram_id == "{video_id}"'}
    with requests.post(
        f"{API_URL}/videos/filter",
        json=query,
        headers={"X-API-TOKEN": API_KEY},
    ) as resp:
        data = resp.json()
        if data.get("data"):
            return True
    return False


def register_download(reel: Reel, org_ids: list[UUID], destination_path: str) -> None:
    log = logger.bind(reel=reel, destination_path=destination_path)

    try:
        if check_entry_exists(reel.id):
            return None
    except Exception:
        log.warning(f"couldn't check if id exists {reel.id}")

    data: dict[str, Any] = {
        "channel": reel.profile.username,
        "channel_followers": reel.profile.followers,
        "comments": reel.comment_count,
        "description": reel.description,
        "destination_path": destination_path,
        "likes": reel.likes_count,
        "platform": "instagram",
        "source_url": reel.video_url,
        "title": f"Instagram video by {reel.profile.username}",
        "uploaded_at": reel.timestamp,
        "views": reel.view_count,
        "metadata": {
            "for_organisation": [str(id) for id in org_ids],
            "instagram_id": reel.id,
        },
    }

    try:
        with requests.post(
            f"{API_URL}/videos", json=data, headers={"X-API-TOKEN": API_KEY}
        ) as resp:
            log.debug(f"registered {reel.id} with API", data=data)
            resp.raise_for_status()

    except Exception as ex:
        log.error(
            f"couldn't post to video api, video_id: {reel.id}",
            exc_info=ex,
            entry=reel,
        )


def _make_safe_cursor_target(target: str) -> str:
    target = target.replace("/", "-").strip()
    return urllib.parse.quote(target, safe="")


def fetch_cursor(target: str, platform: str = "instagram") -> str | None:
    try:
        target = _make_safe_cursor_target(target)
        with requests.get(
            f"{API_URL}/media_feeds/cursors/{target}/{platform}",
            headers={"X-API-TOKEN": API_KEY},
        ) as resp:
            resp.raise_for_status()
            data = resp.json()["data"]
            cursor = Cursor(**data)
            return cursor.cursor.get("last_reel_id")
    except HTTPError as ex:
        if ex.response.status_code == 404:
            return None
        raise ex


def update_cursor(target: str, cursor: str, platform: str = "instagram") -> None:
    log = logger.bind()
    target = _make_safe_cursor_target(target)
    log.debug("updating cursor", cursor=cursor, target=target)
    with requests.post(
        url=f"{API_URL}/media_feeds/cursors/{target}/{platform}",
        json={"last_reel_id": cursor},
        headers={"X-API-TOKEN": API_KEY},
    ) as resp:
        resp.raise_for_status()
    return
