import io
import json
import random
import time
from datetime import datetime
from typing import Any

import structlog
from curl_cffi.requests import Session
from pydantic import BaseModel
from scraper_common import proxy_config
from structlog.contextvars import bind_contextvars

logger: structlog.BoundLogger = structlog.get_logger(__name__)

SLEEP_MAX = 8
SLEEP_MIN = 4


class InstagramError(Exception):
    pass


def _get_public_headers() -> dict:
    return {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-IG-App-ID": "936619743392459",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.instagram.com/",
    }


def _random_proxy() -> str | None:
    if not proxy_config.is_configured:
        logger.warning("proxy not configured - not using proxy")
        return None
    proxy_url, proxy_id = proxy_config.get_proxy_details()
    bind_contextvars(proxy_id=proxy_id)
    return proxy_url


def _random_sleep() -> None:
    sleep_for = random.uniform(SLEEP_MIN, SLEEP_MAX)
    logger.info(f"sleeping for {sleep_for:.2f} seconds to avoid rate limits")
    time.sleep(sleep_for)


def new_session() -> Session:
    session = Session(impersonate="chrome")
    session.headers.update(_get_public_headers())
    proxy = _random_proxy()
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    logger.info("warming up session with instagram.com")
    resp = session.get("https://www.instagram.com/", timeout=10)
    resp.raise_for_status()
    csrf = session.cookies.get("csrftoken")
    if csrf:
        session.headers["X-CSRFToken"] = csrf
    return session


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

    def video_bytes(self, session: Session) -> io.BytesIO:
        logger.info("fetching video", user=self.profile.username, video_id=self.id)
        _random_sleep()
        resp = session.get(self.video_url, timeout=600)
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

            description = ""
            captions = node.get("edge_media_to_caption")
            if captions.get("edges"):
                description = captions.get("edges")[0].get("node", {}).get("text", "")

            taken_at = datetime.fromtimestamp(node.get("taken_at_timestamp"))

            reels.append(
                Reel(
                    id=node.get("id"),
                    profile=self,
                    shortcode=node.get("shortcode"),
                    view_count=node.get("video_view_count")
                    or node.get("play_count", 0),
                    likes_count=node.get("edge_liked_by", {}).get("count"),
                    comment_count=node.get("edge_media_to_comment", {}).get("count"),
                    timestamp=taken_at.isoformat(),
                    description=description,
                    video_url=node.get("video_url"),
                    raw=node,
                )
            )

        return reels


def fetch_profile(username: str, session: Session) -> Profile:
    logger.info("fetching profile", username=username)
    resp = session.get(
        f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}",
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
