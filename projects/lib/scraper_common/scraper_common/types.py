import abc
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, AliasPath, BaseModel, Field

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


class Video(BaseModel):
    id: UUID | None = None
    platform: Platform
    platform_video_id: str
    title: str | None
    description: str | None
    source_url: str | None
    org_ids: list[UUID]
    channel: str | None
    channel_followers: int | None
    views: int | None
    comments: int | None
    likes: int | None
    destination_path: str
    uploaded_at: str | None
