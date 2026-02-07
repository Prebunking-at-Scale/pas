import json
import os
from typing import Any
from uuid import UUID

import structlog
from scraper_common import ChannelFeed, CoreAPIClient, Platform, Video

from instascraper.instagram import Reel

API_URL = os.environ.get("API_URL", "http://localhost:3000/")
API_KEY = json.loads(os.environ.get("API_KEYS", '["abc123"]'))[0]
PLATFORM: Platform = "instagram"

api_client = CoreAPIClient(API_URL, API_KEY)

logger: structlog.BoundLogger = structlog.get_logger(__name__)


def fetch_channel_feeds() -> list[ChannelFeed]:
    return api_client.fetch_channel_feeds()


def get_video(platform_video_id: str) -> dict[str, Any] | None:
    return api_client.get_video(platform_video_id, PLATFORM)


def register_download(reel: Reel, org_ids: list[UUID], destination_path: str) -> bool:
    video = Video(
        platform_video_id=reel.id,
        org_ids=org_ids,
        channel=reel.profile.username,
        channel_followers=reel.profile.followers,
        comments=reel.comment_count,
        description=reel.description,
        destination_path=destination_path,
        likes=reel.likes_count,
        platform=PLATFORM,
        source_url=f"https://instagram.com/reel/{reel.shortcode}",
        title=f"Instagram video by {reel.profile.username}",
        uploaded_at=reel.timestamp,
        views=reel.view_count,
    )

    return api_client.register_video_entry(video)


def update_video_stats(reel: Reel, video_id: str) -> bool:
    api_client.update_video_stats(
        id=video_id,
        views=reel.view_count,
        likes=reel.likes_count,
        comments=reel.comment_count,
        channel_followers=reel.profile.followers,
    )
    return True


def fetch_cursor(target: str) -> str | None:
    cursor = api_client.fetch_cursor(target, PLATFORM)
    if cursor:
        return cursor.get("last_reel_id")
    return None


def update_cursor(target: str, last_reel_id: str) -> None:
    api_client.update_cursor(target, PLATFORM, {"last_reel_id": last_reel_id})
