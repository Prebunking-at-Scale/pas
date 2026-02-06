from datetime import datetime
from uuid import uuid4

import pytest
import responses
from instascraper.coreapi import (
    API_URL,
    ChannelFeed,
    fetch_channel_feeds,
)


@pytest.fixture
def mock_channel_feeds():
    org_id_1 = str(uuid4())
    org_id_2 = str(uuid4())
    return {
        "data": [
            {
                "id": str(uuid4()),
                "organisation_id": org_id_1,
                "channel": "user_1",
                "platform": "instagram",
                "is_archived": False,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
            {
                "id": str(uuid4()),
                "organisation_id": org_id_1,
                "channel": "user_2",
                "platform": "instagram",
                "is_archived": True,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
            {
                "id": str(uuid4()),
                "organisation_id": org_id_1,
                "channel": "user_3",
                "platform": "instagram",
                "is_archived": False,
                "created_at": None,
                "updated_at": None,
            },
            {
                "id": str(uuid4()),
                "organisation_id": org_id_2,
                "channel": "user_3",
                "platform": "instagram",
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
        f"{API_URL}/media_feeds/channels",
        json=mock_channel_feeds,
        status=200,
    )

    result = fetch_channel_feeds()

    assert len(result) == len(mock_channel_feeds["data"])
    assert all(isinstance(feed, ChannelFeed) for feed in result)
    assert result[0].channel == "user_1"
    assert result[0].platform == "instagram"
    assert result[1].is_archived is True
    assert result[2].created_at is None


@responses.activate
def test_fetch_channel_feeds_model_validation(mock_channel_feeds):
    _ = responses.add(
        responses.GET,
        f"{API_URL}/media_feeds/channels",
        json=mock_channel_feeds,
        status=200,
    )

    result = fetch_channel_feeds()
    assert len(result)

    feed = result[0]
    assert isinstance(feed, ChannelFeed)
    assert feed.channel == mock_channel_feeds["data"][0]["channel"]
    assert feed.platform == mock_channel_feeds["data"][0]["platform"]
    assert str(feed.organisation_id) == mock_channel_feeds["data"][0]["organisation_id"]
