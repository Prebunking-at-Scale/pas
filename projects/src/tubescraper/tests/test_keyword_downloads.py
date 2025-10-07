from datetime import datetime
from typing import Any
from uuid import uuid4

import pytest
import requests
import responses
from tubescraper.keyword_downloads import fetch_keyword_feeds
from tubescraper.types import CORE_API, KeywordFeed


@pytest.fixture
def keyword_data():
    org_id = str(uuid4())
    return [
        {
            "id": str(uuid4()),
            "organisation_id": org_id,
            "topic": "sports",
            "keywords": ["football", "basketball"],
            "is_archived": False,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        },
        {
            "id": str(uuid4()),
            "organisation_id": org_id,
            "topic": "music",
            "keywords": ["rock", "jazz"],
            "is_archived": True,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        },
        {
            "id": str(uuid4()),
            "organisation_id": org_id,
            "topic": "tech",
            "keywords": ["ai", "cloud"],
            "is_archived": False,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        },
    ]


@responses.activate
def test_keyword_fetch(keyword_data: list[dict[str, Any]]):
    _ = responses.add(
        responses.GET,
        f"{CORE_API}/media-feeds/keywords",
        json=keyword_data,
        status=200,
    )

    feeds = fetch_keyword_feeds()
    assert isinstance(feeds, list)
    assert all(isinstance(f, KeywordFeed) for f in feeds)
    assert "football" in feeds[0].keywords
    assert feeds[0].topic == "sports"
    assert feeds[1].is_archived


@responses.activate
def test_keyword_fetch_empty():
    _ = responses.add(
        responses.GET,
        f"{CORE_API}/media-feeds/keywords",
        json=[],
        status=200,
    )

    feeds = fetch_keyword_feeds()
    assert feeds == []


@responses.activate
def test_keyword_fetch_raises_connection_error():
    with pytest.raises(requests.exceptions.ConnectionError):
        _ = fetch_keyword_feeds()


@responses.activate
def test_keyword_feed_validation(keyword_data: list[dict[str, Any]]):
    _ = responses.add(
        responses.GET,
        f"{CORE_API}/media-feeds/keywords",
        json=keyword_data,
        status=200,
    )

    feeds = fetch_keyword_feeds()
    sample = feeds[1]
    expected = keyword_data[1]
    assert sample.topic == expected["topic"]
    assert sample.keywords == expected["keywords"]
    assert sample.is_archived is True
