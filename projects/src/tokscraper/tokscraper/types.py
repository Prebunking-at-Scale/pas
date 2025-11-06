import abc
import os
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

CORE_API = os.environ["API_URL"]

Platform = Literal["youtube", "instagram", "tiktok"]


class MediaFeed(BaseModel, abc.ABC):  # pyright: ignore
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
