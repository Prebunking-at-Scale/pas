from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import requests
import responses
from scraper_common import KeywordFeed

from tubescraper.coreapi import api_client

CORE_API = api_client.api_url


def preprocess_keyword_feeds(feeds: list[KeywordFeed]) -> dict[str, list[UUID]]:
    """Deduplicates organisation ids from the feeds."""
    result: dict[str, list[UUID]] = {}
    for feed in feeds:
        for keyword in feed.keywords:
            result[keyword] = result.get(keyword, []) + [feed.organisation_id]

    return result


@pytest.fixture
def keyword_data():
    org_id_1 = str(uuid4())
    org_id_2 = str(uuid4())
    return {
        "data": [
            {
                "id": str(uuid4()),
                "organisation_id": org_id_1,
                "topic": "sports",
                "keywords": ["football", "basketball"],
                "is_archived": False,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
            {
                "id": str(uuid4()),
                "organisation_id": org_id_1,
                "topic": "music",
                "keywords": ["rock", "jazz"],
                "is_archived": True,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
            {
                "id": str(uuid4()),
                "organisation_id": org_id_1,
                "topic": "tech",
                "keywords": ["ai", "cloud"],
                "is_archived": False,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
            {
                "id": str(uuid4()),
                "organisation_id": org_id_2,
                "topic": "tech",
                "keywords": ["ai", "python"],
                "is_archived": False,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
        ]
    }


@responses.activate
def test_keyword_fetch(keyword_data: dict[str, Any]):
    _ = responses.add(
        responses.GET,
        f"{CORE_API}/media_feeds/keywords",
        json=keyword_data,
        status=200,
    )

    feeds = api_client.fetch_keyword_feeds()
    assert isinstance(feeds, list)
    assert all(isinstance(f, KeywordFeed) for f in feeds)
    assert "football" in feeds[0].keywords
    assert feeds[0].topic == "sports"
    assert feeds[1].is_archived


@responses.activate
def test_keyword_fetch_empty():
    _ = responses.add(
        responses.GET,
        f"{CORE_API}/media_feeds/keywords",
        json={},
        status=200,
    )

    with pytest.raises(KeyError):
        _ = api_client.fetch_keyword_feeds()


@responses.activate
def test_keyword_fetch_raises_connection_error():
    with pytest.raises(requests.exceptions.ConnectionError):
        _ = api_client.fetch_keyword_feeds()


@responses.activate
def test_keyword_feed_validation(keyword_data: dict[str, Any]):
    _ = responses.add(
        responses.GET,
        f"{CORE_API}/media_feeds/keywords",
        json=keyword_data,
        status=200,
    )

    feeds = api_client.fetch_keyword_feeds()
    sample = feeds[1]
    expected = keyword_data["data"][1]
    assert sample.topic == expected["topic"]
    assert sample.keywords == expected["keywords"]
    assert sample.is_archived is True


@responses.activate
def test_keyword_feed_deduplication(keyword_data: dict[str, Any]):
    _ = responses.add(
        responses.GET,
        f"{CORE_API}/media_feeds/keywords",
        json=keyword_data,
        status=200,
    )

    feeds = api_client.fetch_keyword_feeds()
    result = preprocess_keyword_feeds(feeds)

    # all keywords in result
    for feed in feeds:
        for keyword in feed.keywords:
            assert keyword in result.keys()
            assert feed.organisation_id in result[keyword]
