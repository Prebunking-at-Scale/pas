import io
import json
import random
import re
import time
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any

import structlog
from curl_cffi.requests import Session
from pydantic import BaseModel, Field
from scraper_common import proxy_config
from structlog.contextvars import bind_contextvars

logger: structlog.BoundLogger = structlog.get_logger(__name__)

SLEEP_MAX = 8
SLEEP_MIN = 4


class InstagramError(Exception):
    pass


class RateLimitError(InstagramError):
    pass


def _get_public_headers() -> dict:
    return {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-IG-App-ID": "936619743392459",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.instagram.com/",
    }


def _random_proxy() -> tuple[str, int] | tuple[None, None]:
    if not proxy_config.is_configured:
        logger.warning("proxy not configured - not using proxy")
        return None, None
    proxy_url, proxy_id = proxy_config.get_proxy_details()
    bind_contextvars(proxy_id=proxy_id)
    return proxy_url, proxy_id


def _random_sleep() -> None:
    sleep_for = random.uniform(SLEEP_MIN, SLEEP_MAX)
    logger.info(f"sleeping for {sleep_for:.2f} seconds to avoid rate limits")
    time.sleep(sleep_for)


def new_session() -> Session:
    session = Session(impersonate="chrome")
    session.headers.update(_get_public_headers())
    proxy_url, proxy_id = _random_proxy()
    if proxy_url:
        session.proxies = {"http": proxy_url, "https": proxy_url}
    session.proxy_id = proxy_id  # type: ignore[attr-defined]
    logger.info("warming up session with instagram.com")
    resp = session.get("https://www.instagram.com/", timeout=10)
    resp.raise_for_status()
    csrf = session.cookies.get("csrftoken")
    if csrf:
        session.headers["X-CSRFToken"] = csrf
    else:
        logger.info("could not get CSRFToken")
    return session


class Reel(BaseModel):
    id: str
    profile: "Profile"
    shortcode: str
    view_count: int
    likes_count: int
    comment_count: int
    # Only on the reel's own page, so None until fetch_reel has been called.
    timestamp: str | None = None
    description: str = ""
    video_url: str | None = None
    raw: dict[str, Any]

    def video_bytes(self, session: Session) -> io.BytesIO:
        if not self.video_url:
            raise InstagramError(f"no video url for reel {self.shortcode}")
        logger.info("fetching video", user=self.profile.username, video_id=self.id)
        _random_sleep()
        resp = session.get(self.video_url, timeout=600)
        if resp.status_code in (401, 429):
            raise RateLimitError(f"Rate limited (HTTP {resp.status_code})")
        resp.raise_for_status()
        return io.BytesIO(resp.content)


class Profile(BaseModel):
    id: str
    username: str
    display_name: str
    followers: int
    following: int
    # Excluded from repr and dumps because each reel points back to its profile.
    reels: list[Reel] = Field(default_factory=list, repr=False, exclude=True)
    raw: dict[str, Any]


def _page_json(html: str) -> Iterator[Any]:
    """Yield the JSON blobs Instagram embeds in its pages for logged-out viewers."""
    for blob in re.findall(
        r'<script type="application/json"[^>]*>(.*?)</script>', html, re.S
    ):
        try:
            yield json.loads(blob)
        except json.JSONDecodeError:
            continue


def _find(html: str, match: Callable[[dict[str, Any]], bool]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            if match(obj):
                found.append(obj)
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    for blob in _page_json(html):
        walk(blob)
    return found


def _fetch_page(url: str, session: Session) -> str:
    resp = session.get(url, timeout=10, headers={"Accept": "text/html"})
    if resp.status_code in (401, 429):
        raise RateLimitError(f"Rate limited (HTTP {resp.status_code})")
    # Instagram sends some IPs to the login page instead of the public page.
    if "/accounts/login" in str(resp.url):
        raise RateLimitError("redirected to login")
    resp.raise_for_status()
    return resp.text


def fetch_profile(username: str, session: Session) -> Profile:
    """Fetch a user's details and their 12 most recent reels from the reels tab."""
    logger.info("fetching profile", username=username)
    html = _fetch_page(f"https://www.instagram.com/{username}/reels/", session)

    users = _find(
        html,
        lambda o: (
            str(o.get("username", "")).lower() == username.lower()
            and "follower_count" in o
        ),
    )
    if not users:
        raise InstagramError(f"could not find profile data for {username}")
    user = users[0]

    profile = Profile(
        id=user["pk"],
        username=user["username"],
        display_name=user.get("full_name") or "",
        followers=user.get("follower_count") or 0,
        following=user.get("following_count") or 0,
        raw=user,
    )

    clips = _find(
        html, lambda o: o.get("pk") == user["pk"] and "polaris_clips_connection" in o
    )
    edges = clips[0]["polaris_clips_connection"]["edges"] if clips else []
    profile.reels = [
        Reel(
            id=node["pk"],
            profile=profile,
            shortcode=node["code"],
            view_count=node.get("play_count") or 0,
            likes_count=node.get("like_count") or 0,
            comment_count=node.get("comment_count") or 0,
            raw=node,
        )
        for node in (edge["node"] for edge in edges)
    ]
    return profile


def fetch_reel(reel: Reel, session: Session) -> Reel:
    """Add the video url, upload time and caption from the reel's own page."""
    logger.info("fetching reel", user=reel.profile.username, video_id=reel.id)
    _random_sleep()
    html = _fetch_page(f"https://www.instagram.com/reel/{reel.shortcode}/", session)

    media = _find(
        html,
        lambda o: o.get("code") == reel.shortcode and bool(o.get("video_versions")),
    )
    if not media:
        raise InstagramError(f"could not find video data for reel {reel.shortcode}")
    node = media[0]

    caption = node.get("caption") or {}
    return reel.model_copy(
        update={
            "video_url": node["video_versions"][0]["url"],
            "timestamp": datetime.fromtimestamp(node["taken_at"]).isoformat(),
            "description": caption.get("text") or "",
        }
    )
