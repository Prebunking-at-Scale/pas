import urllib.parse
from typing import Any

import requests
import structlog
from requests.exceptions import HTTPError

from scraper_common.types import ChannelFeed, Cursor, KeywordFeed, Platform, Video

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class CoreAPIClient:
    """Client for interacting with the Core API for media feed and cursor management."""

    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-API-TOKEN": self.api_key}

    def fetch_channel_feeds(self) -> list[ChannelFeed]:
        """Fetches channel feed data from the core API."""
        with requests.get(
            f"{self.api_url}/media_feeds/channels",
            headers=self._headers,
        ) as resp:
            resp.raise_for_status()
            data = resp.json()["data"]
            return [ChannelFeed(**feed) for feed in data]

    def fetch_keyword_feeds(self) -> list[KeywordFeed]:
        """Fetches keyword feed data from the core API."""
        with requests.get(
            f"{self.api_url}/media_feeds/keywords",
            headers=self._headers,
        ) as resp:
            resp.raise_for_status()
            data = resp.json()["data"]
            return [KeywordFeed(**feed) for feed in data]

    def fetch_cursor(self, target: str, platform: Platform) -> dict[str, Any] | None:
        """Fetches the current cursor for a given target and platform.

        Args:
            target: The channel or keyword identifier.
            platform: The platform (youtube, tiktok, instagram).

        Returns:
            The cursor dict as stored in the API, or None if not found.
        """
        try:
            safe_target = self._make_safe_cursor_target(target)
            with requests.get(
                f"{self.api_url}/media_feeds/cursors/{safe_target}/{platform}",
                headers=self._headers,
            ) as resp:
                resp.raise_for_status()
                data = resp.json()["data"]
                cursor = Cursor(**data)
                return cursor.cursor
        except HTTPError as ex:
            if ex.response.status_code == 404:
                return None
            raise ex

    def update_cursor(
        self, target: str, platform: Platform, cursor: dict[str, Any]
    ) -> None:
        """Updates the stored cursor for a given target and platform.

        Args:
            target: The channel or keyword identifier.
            platform: The platform (youtube, tiktok, instagram).
            cursor: The cursor dict to store.
        """
        log = logger.bind()
        safe_target = self._make_safe_cursor_target(target)
        log.debug("updating cursor", cursor=cursor, target=target)

        with requests.post(
            url=f"{self.api_url}/media_feeds/cursors/{safe_target}/{platform}",
            json=cursor,
            headers=self._headers,
        ) as resp:
            resp.raise_for_status()

    def get_video(
        self, platform_video_id: str, platform: Platform
    ) -> dict[str, Any] | None:
        """Check if a video entry already exists in the API."""
        id_field = f"{platform}_id"
        query = {"metadata": f'$.{id_field} == "{platform_video_id}"'}
        with requests.post(
            f"{self.api_url}/videos/filter",
            json=query,
            headers=self._headers,
        ) as resp:
            data = resp.json()
            videos = data.get("data")
            if not videos:
                return None
            if len(videos) > 1:
                logger.warning(
                    f"found more than one ({len(videos)}) video for {platform}: {platform_video_id}"
                )
            return videos[0]

    def check_entry_exists(self, platform_video_id: str, platform: Platform) -> bool:
        """Check if a video entry already exists in the API."""
        return self.get_video(platform_video_id, platform) is not None

    def _build_api_payload(self, video: Video) -> dict[str, Any]:
        """Build the API payload from a Video, constructing metadata."""
        data = video.model_dump(
            mode="json", exclude={"id", "platform_video_id", "org_ids"}
        )
        data["metadata"] = {
            "for_organisation": [str(org_id) for org_id in video.org_ids],
            f"{video.platform}_id": video.platform_video_id,
        }
        return data

    def register_video(self, video: Video) -> None:
        """Register a video entry with the API."""
        data = self._build_api_payload(video)
        log = logger.bind(video_data=data)
        try:
            with requests.post(
                f"{self.api_url}/videos",
                json=data,
                headers=self._headers,
            ) as resp:
                log.debug("registered video with API", data=data)
                resp.raise_for_status()
        except Exception as ex:
            log.error("couldn't post to video api", exc_info=ex, data=data)
            raise

    def update_video_stats(
        self,
        id: str,
        views: int | None,
        likes: int | None,
        comments: int | None,
        channel_followers: int | None,
    ) -> None:
        """Register a video entry with the API."""
        log = logger.bind(video_id=id)
        data = {
            "views": views,
            "likes": likes,
            "comments": comments,
            "channel_followers": channel_followers,
        }
        try:
            with requests.patch(
                f"{self.api_url}/videos/{id}",
                json=data,
                headers=self._headers,
            ) as resp:
                log.debug("updating video stats with API", data=data)
                resp.raise_for_status()
        except Exception as ex:
            log.error("couldn't post to video stats api", exc_info=ex, data=data)
            raise

    def register_video_entry(self, video: Video) -> bool:
        """Check if video exists and register if not."""
        log = logger.bind(
            video_id=video.platform_video_id, destination_path=video.destination_path
        )

        try:
            if self.check_entry_exists(video.platform_video_id, video.platform):
                log.debug("video already exists, skipping")
                return False
        except Exception:
            log.warning(f"couldn't check if id exists {video.platform_video_id}")

        try:
            self.register_video(video)
            log.debug(f"registered {video.platform_video_id} with API")
            return True
        except Exception as ex:
            log.error(
                f"couldn't post to video api, video_id: {video.platform_video_id}",
                exc_info=ex,
            )
            return False

    @staticmethod
    def _make_safe_cursor_target(target: str) -> str:
        """Make a target string safe for use in URLs."""
        target = target.replace("/", "-").strip()
        return urllib.parse.quote(target, safe="")
