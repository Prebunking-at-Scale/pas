import io
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from instascraper.instagram import Profile, RateLimitError, Reel
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


@patch("instascraper.scrape.new_session")
@patch("instascraper.scrape.coreapi")
@patch("instascraper.scrape.instagram")
def test_downloads_new_video(mock_instagram, mock_coreapi, mocknew_session):
    session = MagicMock()
    response = MagicMock()
    response.content = b"video"
    session.get.return_value = response
    mocknew_session.return_value = session

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


@patch("instascraper.scrape.new_session")
@patch("instascraper.scrape.coreapi")
@patch("instascraper.scrape.instagram")
def test_updates_stats_for_existing_video(mock_instagram, mock_coreapi, mocknew_session):
    mocknew_session.return_value = MagicMock()

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


@patch("instascraper.scrape.new_session")
@patch("instascraper.scrape.coreapi")
@patch("instascraper.scrape.instagram")
def test_downloads_new_and_updates_existing(mock_instagram, mock_coreapi, mocknew_session):
    session = MagicMock()
    response = MagicMock()
    response.content = b"video"
    session.get.return_value = response
    mocknew_session.return_value = session

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


@patch("instascraper.scrape.new_session")
@patch("instascraper.scrape.coreapi")
@patch("instascraper.scrape.instagram")
def test_no_reels_returns_none(mock_instagram, mock_coreapi, mocknew_session):
    mocknew_session.return_value = MagicMock()

    profile = _make_profile()
    mock_instagram.fetch_profile.return_value = profile
    type(profile).reels = property(lambda self: [])

    storage = MagicMock()
    result = scrape_channel("test_user", None, storage, [])

    assert result is None
    mock_coreapi.register_download.assert_not_called()
    mock_coreapi.update_video_stats.assert_not_called()


@patch("instascraper.scrape.proxy_config")
@patch("instascraper.scrape.new_session")
@patch("instascraper.scrape.coreapi")
@patch("instascraper.scrape.instagram")
def test_retries_profile_fetch_on_rate_limit(
    mock_instagram, mock_coreapi, mock_new_session, mock_proxy_config
):
    first_session = MagicMock()
    first_session.proxy_id = 1
    second_session = MagicMock()
    second_session.proxy_id = 2
    mock_new_session.side_effect = [first_session, second_session]

    profile = _make_profile()
    mock_instagram.fetch_profile.side_effect = [RateLimitError("rate limited"), profile]
    type(profile).reels = property(lambda self: [])

    storage = MagicMock()
    result = scrape_channel("test_user", None, storage, [])

    assert result is None
    mock_proxy_config.deactivate_proxy.assert_called_once_with(1, 300)
    assert mock_new_session.call_count == 2
    assert mock_instagram.fetch_profile.call_count == 2


@patch("instascraper.scrape.proxy_config")
@patch("instascraper.scrape.new_session")
@patch("instascraper.scrape.coreapi")
@patch("instascraper.scrape.instagram")
@patch.object(Reel, "video_bytes")
def test_retries_video_download_on_rate_limit(
    mock_video_bytes, mock_instagram, mock_coreapi, mock_new_session, mock_proxy_config
):
    first_session = MagicMock()
    first_session.proxy_id = 1
    second_session = MagicMock()
    second_session.proxy_id = 2
    mock_new_session.side_effect = [first_session, second_session]

    profile = _make_profile()
    reel = _make_reel("reel1", profile)
    mock_instagram.fetch_profile.return_value = profile
    type(profile).reels = property(lambda self: [reel])

    mock_coreapi.get_video.return_value = None
    mock_video_bytes.side_effect = [RateLimitError("rate limited"), io.BytesIO(b"video")]

    storage = MagicMock()
    storage.upload_blob.return_value = "blob/path"

    result = scrape_channel("test_user", None, storage, [])

    assert result == "reel1"
    mock_proxy_config.deactivate_proxy.assert_called_once_with(1, 300)
    assert mock_new_session.call_count == 2
    mock_coreapi.register_download.assert_called_once()
