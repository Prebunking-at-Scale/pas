import io
from unittest.mock import MagicMock

import pytest
from instascraper import instagram
from instascraper.instagram import (
    Profile,
    Reel,
    fetch_profile,
)

instagram.SLEEP_MAX = 0
instagram.SLEEP_MIN = 0


@pytest.fixture
def mock_instagram_user():
    return {
        "data": {
            "user": {
                "id": "123456789",
                "username": "test_user",
                "full_name": "Test User",
                "edge_followed_by": {"count": 10000},
                "edge_follow": {"count": 500},
                "edge_owner_to_timeline_media": {
                    "edges": [
                        {
                            "node": {
                                "__typename": "GraphVideo",
                                "id": "3364843860104643554",
                                "shortcode": "C_abc123",
                                "video_view_count": 5000,
                                "edge_liked_by": {"count": 200},
                                "edge_media_to_comment": {"count": 50},
                                "taken_at_timestamp": 1704067200,
                                "video_url": "https://example.com/video.mp4",
                                "edge_media_to_caption": {
                                    "edges": [{"node": {"text": "Test video description"}}]
                                },
                            }
                        },
                        {
                            "node": {
                                "__typename": "GraphImage",
                                "id": "3364843860104643555",
                                "shortcode": "C_abc124",
                            }
                        },
                        {
                            "node": {
                                "__typename": "GraphVideo",
                                "id": "3364843860104643556",
                                "shortcode": "C_abc125",
                                "video_view_count": 3000,
                                "edge_liked_by": {"count": 150},
                                "edge_media_to_comment": {"count": 30},
                                "taken_at_timestamp": 1704153600,
                                "video_url": "https://example.com/video2.mp4",
                                "edge_media_to_caption": {"edges": []},
                            }
                        },
                    ]
                },
            }
        }
    }


@pytest.fixture
def mock_profile():
    return Profile(
        id="123456789",
        username="test_user",
        display_name="Test User",
        followers=10000,
        following=500,
        raw={
            "edge_owner_to_timeline_media": {
                "edges": [
                    {
                        "node": {
                            "__typename": "GraphVideo",
                            "id": "3364843860104643554",
                            "shortcode": "C_abc123",
                            "video_view_count": 5000,
                            "edge_liked_by": {"count": 200},
                            "edge_media_to_comment": {"count": 50},
                            "taken_at_timestamp": 1704067200,
                            "video_url": "https://example.com/video.mp4",
                            "edge_media_to_caption": {
                                "edges": [{"node": {"text": "Test video description"}}]
                            },
                        }
                    }
                ]
            }
        },
    )


def _mock_session_with_response(json_data=None, content=None, status_code=200):
    session = MagicMock()
    response = MagicMock()
    response.status_code = status_code
    response.raise_for_status = MagicMock()
    if json_data is not None:
        response.json.return_value = json_data
    if content is not None:
        response.content = content
    session.get.return_value = response
    return session


def test_fetch_profile_success(mock_instagram_user):
    session = _mock_session_with_response(json_data=mock_instagram_user)

    profile = fetch_profile("test_user", session)

    assert isinstance(profile, Profile)
    assert profile.id == "123456789"
    assert profile.username == "test_user"
    assert profile.display_name == "Test User"
    assert profile.followers == 10000
    assert profile.following == 500


def test_profile_reels_property(mock_profile):
    reels = mock_profile.reels

    assert len(reels) == 1
    assert isinstance(reels[0], Reel)
    assert reels[0].id == "3364843860104643554"
    assert reels[0].shortcode == "C_abc123"
    assert reels[0].view_count == 5000
    assert reels[0].likes_count == 200
    assert reels[0].comment_count == 50
    assert reels[0].description == "Test video description"
    assert reels[0].video_url == "https://example.com/video.mp4"


def test_profile_reels_filters_non_videos(mock_instagram_user):
    profile = Profile(
        id="123456789",
        username="test_user",
        display_name="Test User",
        followers=10000,
        following=500,
        raw=mock_instagram_user["data"]["user"],
    )

    reels = profile.reels

    assert len(reels) == 2
    assert all(isinstance(reel, Reel) for reel in reels)
    assert all(reel.id != "3364843860104643555" for reel in reels)


def test_profile_reels_empty_description():
    profile = Profile(
        id="123456789",
        username="test_user",
        display_name="Test User",
        followers=10000,
        following=500,
        raw={
            "edge_owner_to_timeline_media": {
                "edges": [
                    {
                        "node": {
                            "__typename": "GraphVideo",
                            "id": "3364843860104643556",
                            "shortcode": "C_abc125",
                            "video_view_count": 3000,
                            "edge_liked_by": {"count": 150},
                            "edge_media_to_comment": {"count": 30},
                            "taken_at_timestamp": 1704153600,
                            "video_url": "https://example.com/video2.mp4",
                            "edge_media_to_caption": {"edges": []},
                        }
                    }
                ]
            }
        },
    )

    reels = profile.reels
    assert len(reels) == 1
    assert reels[0].description == ""


def test_reel_video_bytes():
    mock_video_content = b"fake video content"
    session = _mock_session_with_response(content=mock_video_content)

    profile = Profile(
        id="123456789",
        username="test_user",
        display_name="Test User",
        followers=10000,
        following=500,
        raw={},
    )

    reel = Reel(
        id="3364843860104643554",
        profile=profile,
        shortcode="C_abc123",
        view_count=5000,
        likes_count=200,
        comment_count=50,
        timestamp="2024-01-01T00:00:00",
        description="Test video",
        video_url="https://example.com/video.mp4",
        raw={},
    )

    result = reel.video_bytes(session)

    assert isinstance(result, io.BytesIO)
    assert result.getvalue() == mock_video_content
