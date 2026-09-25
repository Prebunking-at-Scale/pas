from datetime import datetime
from unittest.mock import MagicMock, patch

from structlog.testing import capture_logs
from tokscraper.scrape import download_channel_shorts

CURSOR = datetime(2026, 9, 18)


@patch("tokscraper.scrape.proxy_config")
@patch("tokscraper.scrape.register_download")
@patch("tokscraper.scrape.video_details")
@patch("tokscraper.scrape.api_client")
@patch("tokscraper.scrape.yt_dlp.YoutubeDL")
def test_logs_registration_result(
    ydl, api_client, video_details, register, proxy_config
):
    proxy_config.get_proxy_details.return_value = ("http://proxy", 1)
    entries = [
        {"id": i, "timestamp": CURSOR.timestamp(), "duration": 20}
        for i in ("ok", "rejected")
    ]
    ydl.return_value.__enter__.return_value.extract_info.return_value = {
        "entries": entries
    }
    api_client.get_video.return_value = None
    video_details.side_effect = lambda url, buf: {
        "id": url.rsplit("/", 1)[1],
        "ext": "mp4",
    }
    register.side_effect = [True, False]

    with capture_logs() as logs:
        download_channel_shorts("@channel", CURSOR, MagicMock(), [])

    metrics = [e["event_metric"] for e in logs if "event_metric" in e]
    assert metrics == ["download_success", "register_failure"]


@patch("tokscraper.scrape.proxy_config")
@patch("tokscraper.scrape.register_download", return_value=True)
@patch("tokscraper.scrape.video_details")
@patch("tokscraper.scrape.api_client")
@patch("tokscraper.scrape.yt_dlp.YoutubeDL")
def test_skips_photo_posts(ydl, api_client, video_details, _register, proxy_config):
    proxy_config.get_proxy_details.return_value = ("http://proxy", 1)
    entries = [
        {"id": "video", "timestamp": CURSOR.timestamp(), "duration": 20},
        {"id": "photo", "timestamp": CURSOR.timestamp(), "duration": None},
    ]
    ydl.return_value.__enter__.return_value.extract_info.return_value = {
        "entries": entries
    }
    api_client.get_video.return_value = None
    video_details.side_effect = lambda url, buf: {
        "id": url.rsplit("/", 1)[1],
        "ext": "mp4",
    }

    download_channel_shorts("@channel", CURSOR, MagicMock(), [])

    assert [c.args[0].rsplit("/", 1)[1] for c in video_details.call_args_list] == [
        "video"
    ]
