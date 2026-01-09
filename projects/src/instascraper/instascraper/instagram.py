import io
import json
from datetime import datetime
import os
import random
import time
from typing import Any

import requests
from pydantic import BaseModel
import structlog
from tenacity import after_log, retry, stop_after_attempt

logger: structlog.BoundLogger = structlog.get_logger(__name__)

PROXY_COUNT = int(os.environ.get("PROXY_COUNT", 0))
PROXY_USERNAME = os.environ.get("PROXY_USERNAME")
PROXY_PASSWORD = os.environ.get("PROXY_PASSWORD")


class InstagramError(Exception):
    pass


def _get_public_headers() -> dict:
    """Some sensible default headers for public Instagram API requests."""
    return {
        # This is the usage agent for a Google Home Hub Max...
        "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 CrKey/1.54.250320",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-IG-App-ID": "936619743392459",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.instagram.com/",
    }


def _random_proxy() -> dict[str, str] | None:
    if not PROXY_COUNT or not PROXY_USERNAME or not PROXY_PASSWORD:
        logger.warn(
            "PROXY_COUNT, PROXY_USERNAME or PROXY_PASSWORD unset - not using proxy"
        )
        return None

    proxy_id = random.randrange(1, PROXY_COUNT, 1)
    logger.info(f"using proxy id {proxy_id}")
    proxy = f"http://{PROXY_USERNAME}-{proxy_id}:{PROXY_PASSWORD}@p.webshare.io:80/"
    return {
        "http": proxy,
        "https": proxy,
    }


def _random_sleep() -> None:
    sleep_for = random.uniform(4, 8)
    logger.info(f"sleeping for {sleep_for:.2f} seconds to avoid rate limits")
    time.sleep(sleep_for)


class Reel(BaseModel):
    id: str
    profile: "Profile"
    shortcode: str
    view_count: int
    likes_count: int
    comment_count: int
    timestamp: str
    description: str
    video_url: str
    raw: dict[str, Any]

    @retry(reraise=True, stop=stop_after_attempt(3))
    def video_bytes(self) -> io.BytesIO:
        logger.info("fetching video", user=self.profile.username, video_id=self.id)
        _random_sleep()
        resp = requests.get(
            self.video_url,
            headers=_get_public_headers(),
            proxies=_random_proxy(),
            timeout=600,
        )
        resp.raise_for_status()
        return io.BytesIO(resp.content)


class Profile(BaseModel):
    id: str
    username: str
    display_name: str
    followers: int
    following: int
    raw: dict[str, Any]

    @property
    def reels(self) -> list[Reel]:
        """Fetch up to the 12 most recent reels posted by the user.

        "up to" because we're only able to fetch the 12 most recent posts (inc. images)
        and then have to filter out any non-video posts"""
        timeline_media = self.raw.get("edge_owner_to_timeline_media", {})
        if not timeline_media:
            InstagramError(f"Could not get media for {self.username}")

        reels = []
        for edge in timeline_media.get("edges", []):
            node = edge.get("node", {})
            if node.get("__typename") != "GraphVideo":
                continue

            description = (
                node.get("edge_media_to_caption", {})
                .get("edges", [{}])[0]
                .get("node")
                .get("text")
            )

            taken_at = datetime.fromtimestamp(node.get("taken_at_timestamp"))

            reels.append(
                Reel(
                    id=node.get("id"),
                    profile=self,
                    shortcode=node.get("shortcode"),
                    view_count=node.get("video_view_count"),
                    likes_count=node.get("edge_liked_by", {}).get("count"),
                    comment_count=node.get("edge_media_to_comment", {}).get("count"),
                    timestamp=taken_at.isoformat(),
                    description=description,
                    video_url=node.get("video_url"),
                    raw=node,
                )
            )

        return reels


@retry(reraise=True, stop=stop_after_attempt(3))
def fetch_profile(username: str) -> Profile:
    """Fetch user data including media using public web API (no authentication required)."""
    logger.info("fetching profile", username=username)
    _random_sleep()
    resp = requests.get(
        f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}",
        headers=_get_public_headers(),
        proxies=_random_proxy(),
        timeout=10,
    )
    resp.raise_for_status()

    json_resp = resp.json()
    if "error" in json_resp:
        raise InstagramError(json_resp["error"])

    if "data" not in json_resp or "user" not in json_resp["data"]:
        raise InstagramError("unexpected response:\n", json.dumps(json_resp, indent=2))

    user = resp.json()["data"]["user"]
    return Profile(
        id=user["id"],
        username=user["username"],
        display_name=user["full_name"],
        followers=user["edge_followed_by"]["count"],
        following=user["edge_follow"]["count"],
        raw=user,
    )
