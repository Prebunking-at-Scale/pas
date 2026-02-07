import io
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from instascraper.instagram import Profile, Reel
from instascraper.scrape import scrape_channel


def _make_profile():
    return Profile(
        id="123",
        username="test_user",
        display_name="Test User",
        followers=1000,
        following=100,
        raw={},
    )


def _make_reel(id: str, profile: Profile | None = None) -> Reel:
    return Reel(
        id=id,
        profile=profile or _make_profile(),
        shortcode=f"sc_{id}",
        view_count=100,
        likes_count=10,
        comment_count=5,
        timestamp=datetime.now().isoformat(),
        description="test",
        video_url=f"https://example.com/{id}.mp4",
        raw={},
    )


@patch("instascraper.instagram._new_session")
@patch("instascraper.scrape.coreapi")
@patch("instascraper.scrape.instagram")
def test_downloads_new_video(mock_instagram, mock_coreapi, mock_new_session):
    session = MagicMock()
    response = MagicMock()
    response.content = b"video"
    session.get.return_value = response
    mock_new_session.return_value = session

    profile = _make_profile()
    reel = _make_reel("reel1", profile)
    mock_instagram.fetch_profile.return_value = profile
    type(profile).reels = property(lambda self: [reel])

    mock_coreapi.get_video.return_value = None

    storage = MagicMock()
    storage.upload_blob.return_value = "blob/path"

    result = scrape_channel("test_user", None, storage, [])

    assert result == "reel1"
    mock_coreapi.register_download.assert_called_once()
    mock_coreapi.update_video_stats.assert_not_called()


@patch("instascraper.scrape.coreapi")
@patch("instascraper.scrape.instagram")
def test_updates_stats_for_existing_video(mock_instagram, mock_coreapi):
    profile = _make_profile()
    reel = _make_reel("reel1", profile)
    mock_instagram.fetch_profile.return_value = profile
    type(profile).reels = property(lambda self: [reel])

    mock_coreapi.get_video.return_value = {"id": "db-video-id"}

    storage = MagicMock()
    result = scrape_channel("test_user", "old_cursor", storage, [])

    assert result is None
    mock_coreapi.update_video_stats.assert_called_once_with(reel, "db-video-id")
    mock_coreapi.register_download.assert_not_called()


@patch("instascraper.instagram._new_session")
@patch("instascraper.scrape.coreapi")
@patch("instascraper.scrape.instagram")
def test_downloads_new_and_updates_existing(mock_instagram, mock_coreapi, mock_new_session):
    session = MagicMock()
    response = MagicMock()
    response.content = b"video"
    session.get.return_value = response
    mock_new_session.return_value = session

    profile = _make_profile()
    new_reel = _make_reel("new_reel", profile)
    old_reel = _make_reel("old_reel", profile)
    mock_instagram.fetch_profile.return_value = profile
    type(profile).reels = property(lambda self: [new_reel, old_reel])

    mock_coreapi.get_video.side_effect = [None, {"id": "db-id"}]

    storage = MagicMock()
    storage.upload_blob.return_value = "blob/path"

    result = scrape_channel("test_user", "old_cursor", storage, [])

    assert result == "new_reel"
    mock_coreapi.register_download.assert_called_once()
    mock_coreapi.update_video_stats.assert_called_once_with(old_reel, "db-id")


@patch("instascraper.scrape.coreapi")
@patch("instascraper.scrape.instagram")
def test_no_reels_returns_none(mock_instagram, mock_coreapi):
    profile = _make_profile()
    mock_instagram.fetch_profile.return_value = profile
    type(profile).reels = property(lambda self: [])

    storage = MagicMock()
    result = scrape_channel("test_user", None, storage, [])

    assert result is None
    mock_coreapi.register_download.assert_not_called()
    mock_coreapi.update_video_stats.assert_not_called()
