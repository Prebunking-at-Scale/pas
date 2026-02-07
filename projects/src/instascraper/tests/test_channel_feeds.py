from datetime import datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from instascraper.coreapi import fetch_channel_feeds
from scraper_common import ChannelFeed


@pytest.fixture
def mock_channel_feeds():
    return [
        ChannelFeed(
            id=uuid4(),
            organisation_id=uuid4(),
            channel="user_1",
            platform="instagram",
            is_archived=False,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        ),
        ChannelFeed(
            id=uuid4(),
            organisation_id=uuid4(),
            channel="user_2",
            platform="instagram",
            is_archived=True,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        ),
        ChannelFeed(
            id=uuid4(),
            organisation_id=uuid4(),
            channel="user_3",
            platform="instagram",
            is_archived=False,
            created_at=None,
            updated_at=None,
        ),
    ]


@patch("instascraper.coreapi.api_client")
def test_fetch_channel_feeds(mock_client, mock_channel_feeds):
    mock_client.fetch_channel_feeds.return_value = mock_channel_feeds

    result = fetch_channel_feeds()

    assert len(result) == 3
    assert all(isinstance(feed, ChannelFeed) for feed in result)
    assert result[0].channel == "user_1"
    assert result[0].platform == "instagram"
    assert result[1].is_archived is True
    assert result[2].created_at is None


@patch("instascraper.coreapi.api_client")
def test_fetch_channel_feeds_model_validation(mock_client, mock_channel_feeds):
    mock_client.fetch_channel_feeds.return_value = mock_channel_feeds

    result = fetch_channel_feeds()
    assert len(result)

    feed = result[0]
    assert isinstance(feed, ChannelFeed)
    assert feed.channel == "user_1"
    assert feed.platform == "instagram"
