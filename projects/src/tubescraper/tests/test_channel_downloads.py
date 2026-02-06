from datetime import datetime
from typing import Iterable
from uuid import UUID, uuid4

import pytest
import requests
import responses
from scraper_common import ChannelFeed
from tubescraper.coreapi import api_client

CORE_API = api_client.api_url


def preprocess_channel_feeds(feeds: Iterable[ChannelFeed]) -> dict[str, list[UUID]]:
    result: dict[str, list[UUID]] = {}
    for feed in feeds:
        if feed.platform != "youtube":
            continue
        result[feed.channel] = result.get(feed.channel, []) + [feed.organisation_id]

    return result


@pytest.fixture
def mock_channel_feeds():
    org_id_1 = str(uuid4())
    org_id_2 = str(uuid4())
    return {
        "data": [
            {
                "id": str(uuid4()),
                "organisation_id": org_id_1,
                "channel": "channel_1",
                "platform": "youtube",
                "is_archived": False,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
            {
                "id": str(uuid4()),
                "organisation_id": org_id_1,
                "channel": "channel_2",
                "platform": "instagram",
                "is_archived": True,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
            {
                "id": str(uuid4()),
                "organisation_id": org_id_1,
                "channel": "channel_3",
                "platform": "tiktok",
                "is_archived": False,
                "created_at": None,
                "updated_at": None,
            },
            {
                "id": str(uuid4()),
                "organisation_id": org_id_2,
                "channel": "channel_3",
                "platform": "tiktok",
                "is_archived": False,
                "created_at": None,
                "updated_at": None,
            },
        ],
    }


@responses.activate
def test_fetch_channel_feeds(mock_channel_feeds):
    _ = responses.add(
        responses.GET,
        f"{CORE_API}/media_feeds/channels",
        json=mock_channel_feeds,
        status=200,
    )

    result = api_client.fetch_channel_feeds()

    assert len(result) == len(mock_channel_feeds["data"])
    assert all(isinstance(feed, ChannelFeed) for feed in result)
    assert result[0].channel == "channel_1"
    assert result[0].platform == "youtube"
    assert result[1].is_archived is True
    assert result[2].created_at is None


@responses.activate
def test_fetch_channel_feeds_empty():
    _ = responses.add(responses.GET, f"{CORE_API}/media_feeds/channels", json={}, status=200)

    with pytest.raises(KeyError):
        _ = api_client.fetch_channel_feeds()


@responses.activate
def test_fetch_channel_feeds_connection_error():
    with pytest.raises(requests.exceptions.ConnectionError):
        _ = api_client.fetch_channel_feeds()


@responses.activate
def test_fetch_channel_feeds_model_validation(mock_channel_feeds):
    _ = responses.add(
        responses.GET,
        f"{CORE_API}/media_feeds/channels",
        json=mock_channel_feeds,
        status=200,
    )

    result = api_client.fetch_channel_feeds()
    assert len(result)

    feed = result[0]
    assert isinstance(feed, ChannelFeed)
    assert feed.channel == mock_channel_feeds["data"][0]["channel"]
    assert feed.platform == mock_channel_feeds["data"][0]["platform"]


@responses.activate
def test_channel_feed_deduplication(mock_channel_feeds):
    _ = responses.add(
        responses.GET,
        f"{CORE_API}/media_feeds/channels",
        json=mock_channel_feeds,
        status=200,
    )

    feeds = api_client.fetch_channel_feeds()
    result = preprocess_channel_feeds(feeds)

    for feed in feeds:
        assert (
            feed.organisation_id in result[feed.channel]
            if feed.platform == "youtube"
            else True
        )
