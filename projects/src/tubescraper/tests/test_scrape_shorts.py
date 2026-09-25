from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

from tubescraper.scrape import scrape_shorts

CURSOR = datetime(2026, 9, 18)
NEW = CURSOR.timestamp()
OLD = (CURSOR - timedelta(days=30)).timestamp()


def details_for(timestamps):
    def video_details(entry_id, buf=None):
        return {
            "id": entry_id,
            "channel_id": "UC1",
            "ext": "mp4",
            "timestamp": timestamps[entry_id],
        }

    return video_details


@patch("tubescraper.scrape.time.sleep")
@patch("tubescraper.scrape.register_download", return_value=True)
@patch("tubescraper.scrape.update_video_stats")
@patch("tubescraper.scrape.api_client")
def test_stops_downloading_after_an_old_video(
    api_client, update_stats, register, _sleep
):
    api_client.get_video.side_effect = lambda video_id, platform: (
        {"id": "db-known", "views": 1, "uploaded_at": CURSOR.isoformat()}
        if video_id == "known"
        else None
    )
    entries = [
        {"id": "new"},
        {"id": "old"},
        {"id": "later"},
        {"id": "known", "view_count": 100},
    ]
    timestamps = {"new": NEW, "old": OLD, "later": NEW}

    with patch(
        "tubescraper.scrape.video_details", side_effect=details_for(timestamps)
    ) as details:
        scrape_shorts(entries, CURSOR, MagicMock(), "@channel", [uuid4()])

    assert [c.args[0] for c in details.call_args_list] == ["new", "old"]
    assert register.call_count == 1
    update_stats.assert_called_once()


@patch("tubescraper.scrape.time.sleep")
@patch("tubescraper.scrape.register_download", return_value=True)
@patch("tubescraper.scrape.update_video_stats")
@patch("tubescraper.scrape.api_client")
def test_only_sleeps_between_youtube_requests(
    api_client, _update_stats, _register, sleep
):
    known = {"k1", "k2", "k3"}
    api_client.get_video.side_effect = lambda video_id, platform: (
        {"id": f"db-{video_id}", "views": 1, "uploaded_at": CURSOR.isoformat()}
        if video_id in known
        else None
    )
    entries = [{"id": i} for i in ("k1", "n1", "k2", "k3", "n2")]
    timestamps = {"n1": NEW, "n2": NEW}

    with patch("tubescraper.scrape.video_details", side_effect=details_for(timestamps)):
        scrape_shorts(entries, CURSOR, MagicMock(), "@channel", [uuid4()])

    # two downloads, so one pause between them, and none for the known videos
    assert sleep.call_count == 1
