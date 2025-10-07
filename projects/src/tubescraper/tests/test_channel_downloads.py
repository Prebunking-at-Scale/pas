from datetime import datetime
from uuid import uuid4

import pytest
import requests
from tubescraper.channel_downloads import fetch_channel_feeds
from tubescraper.types import CORE_API, ChannelFeed


@pytest.fixture
def mock_channel_feeds():
    org_id = str(uuid4())
    return [
        {
            "id": str(uuid4()),
            "organisation_id": org_id,
            "channel": "channel_1",
            "platform": "youtube",
            "is_archived": False,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        },
        {
            "id": str(uuid4()),
            "organisation_id": org_id,
            "channel": "channel_2",
            "platform": "instagram",
            "is_archived": True,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        },
        {
            "id": str(uuid4()),
            "organisation_id": org_id,
            "channel": "channel_3",
            "platform": "tiktok",
            "is_archived": False,
            "created_at": None,
            "updated_at": None,
        },
    ]


import responses


@responses.activate
def test_fetch_channel_feeds(mock_channel_feeds):
    _ = responses.add(
        responses.GET, f"{CORE_API}/media-feeds/channels", json=mock_channel_feeds, status=200
    )

    result = fetch_channel_feeds()

    assert len(result) == 3
    assert all(isinstance(feed, ChannelFeed) for feed in result)
    assert result[0].channel == "channel_1"
    assert result[0].platform == "youtube"
    assert result[1].is_archived is True
    assert result[2].created_at is None


@responses.activate
def test_fetch_channel_feeds_empty():
    _ = responses.add(responses.GET, f"{CORE_API}/media-feeds/channels", json=[], status=200)
    result = fetch_channel_feeds()

    assert result == []
    assert isinstance(result, list)


@responses.activate
def test_fetch_channel_feeds_connection_error():
    with pytest.raises(requests.exceptions.ConnectionError):
        _ = fetch_channel_feeds()


@responses.activate
def test_fetch_channel_feeds_model_validation(mock_channel_feeds):
    _ = responses.add(
        responses.GET, f"{CORE_API}/media-feeds/channels", json=mock_channel_feeds, status=200
    )

    result = fetch_channel_feeds()
    assert len(result)

    feed = result[0]
    assert isinstance(feed, ChannelFeed)
    assert feed.channel == mock_channel_feeds[0]["channel"]
    assert feed.platform == mock_channel_feeds[0]["platform"]
