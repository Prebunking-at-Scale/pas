import io

import pytest
import responses
from instascraper import instagram
from instascraper.instagram import (
    Profile,
    Reel,
    fetch_profile,
)

# Disable random sleeps - we're mocking the requests so no need to add
# delays between them!
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


@responses.activate
def test_fetch_profile_success(mock_instagram_user):
    username = "test_user"
    _ = responses.add(
        responses.GET,
        f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}",
        json=mock_instagram_user,
        status=200,
    )

    profile = fetch_profile(username)

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

    # Should only have 2 videos, not the image
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


@responses.activate
def test_reel_video_bytes():
    mock_video_content = b"fake video content"
    video_url = "https://example.com/video.mp4"

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
        video_url=video_url,
        raw={},
    )

    _ = responses.add(responses.GET, video_url, body=mock_video_content, status=200)

    result = reel.video_bytes()

    assert isinstance(result, io.BytesIO)
    assert result.getvalue() == mock_video_content
