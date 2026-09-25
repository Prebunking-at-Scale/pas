from unittest.mock import patch
from uuid import uuid4

from tubescraper.coreapi import register_download

ENTRY = {
    "id": "abc123",
    "timestamp": 1758000000,
    "uploader_id": "@channel",
    "title": "a video",
    "webpage_url": "https://www.youtube.com/watch?v=abc123",
}


def test_registers_merged_download_without_video_ext():
    entry = {**ENTRY, "requested_downloads": [{"filepath": "/tmp/abc123.mp4"}]}
    with patch("tubescraper.coreapi.api_client") as api_client:
        api_client.register_video_entry.return_value = True
        assert register_download(entry, [uuid4()], "tubescraper/x/abc123.mp4")
    api_client.register_video_entry.assert_called_once()


def test_skips_entry_that_was_not_downloaded():
    with patch("tubescraper.coreapi.api_client") as api_client:
        assert not register_download(ENTRY, [uuid4()], "tubescraper/x/abc123.mp4")
    api_client.register_video_entry.assert_not_called()
