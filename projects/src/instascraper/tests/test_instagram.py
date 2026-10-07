import io
import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from instascraper import instagram
from instascraper.instagram import (
    InstagramError,
    Profile,
    RateLimitError,
    Reel,
    fetch_profile,
    fetch_reel,
)

instagram.SLEEP_MAX = 0
instagram.SLEEP_MIN = 0


def _page(*blobs: dict) -> str:
    """Wrap JSON blobs the way Instagram embeds them in a logged-out page."""
    scripts = "".join(
        f'<script type="application/json" data-sjs>{json.dumps(b)}</script>'
        for b in blobs
    )
    return f"<html><head><title>Instagram</title></head><body>{scripts}</body></html>"


def _relay(data: dict) -> dict:
    return {
        "require": [
            [
                "RelayPrefetchedStreamCache",
                "next",
                [],
                ["q", {"__bbox": {"result": {"data": data}}}],
            ]
        ]
    }


def _clip(pk: str, code: str, plays: int | None, likes: int, comments: int) -> dict:
    return {
        "node": {
            "__typename": "XIGPolarisVideoMedia",
            "pk": pk,
            "code": code,
            "play_count": plays,
            "like_count": likes,
            "comment_count": comments,
        }
    }


@pytest.fixture
def reels_tab_html() -> str:
    user = {
        "pk": "22478535964",
        "id": "17841422558939816",
        "username": "test_user",
        "full_name": "Test User",
        "follower_count": 10000,
        "following_count": 500,
    }
    clips = {
        "pk": "22478535964",
        "id": "17841422558939816",
        "polaris_clips_connection": {
            "edges": [
                _clip("3364843860104643554", "C_abc123", 5000, 200, 50),
                _clip("3364843860104643556", "C_abc125", None, 150, 30),
            ]
        },
    }
    return _page(
        _relay({"xig_user_by_username": user}),
        _relay({"xig_user_by_username": clips}),
    )


@pytest.fixture
def reel_page_html() -> str:
    media = {
        "pk": "3364843860104643554",
        "code": "C_abc123",
        "taken_at": 1704067200,
        "like_count": 200,
        "comment_count": 50,
        "caption": {"text": "Test video description"},
        "video_versions": [
            {"type": "101", "url": "https://example.com/video.mp4"},
            {"type": "102", "url": "https://example.com/video-small.mp4"},
        ],
    }
    return _page(_relay({"xig_polaris_media": {"if_not_gated_logged_out": media}}))


def _session(
    text: str = "",
    content: bytes = b"",
    status_code: int = 200,
    url: str = "https://www.instagram.com/test_user/reels/",
) -> MagicMock:
    session = MagicMock()
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    response.content = content
    response.url = url
    session.get.return_value = response
    return session


def _profile() -> Profile:
    return Profile(
        id="123",
        username="test_user",
        display_name="Test User",
        followers=0,
        following=0,
        raw={},
    )


def _reel(**overrides) -> Reel:
    fields = {
        "id": "3364843860104643554",
        "profile": _profile(),
        "shortcode": "C_abc123",
        "view_count": 5000,
        "likes_count": 200,
        "comment_count": 50,
        "raw": {},
    }
    return Reel(**(fields | overrides))


def test_fetch_profile_reads_user_details(reels_tab_html):
    profile = fetch_profile("test_user", _session(text=reels_tab_html))

    assert profile.id == "22478535964"
    assert profile.username == "test_user"
    assert profile.display_name == "Test User"
    assert profile.followers == 10000
    assert profile.following == 500


def test_fetch_profile_reads_reels_with_counts(reels_tab_html):
    profile = fetch_profile("test_user", _session(text=reels_tab_html))

    assert [
        (r.id, r.shortcode, r.view_count, r.likes_count, r.comment_count)
        for r in profile.reels
    ] == [
        ("3364843860104643554", "C_abc123", 5000, 200, 50),
        ("3364843860104643556", "C_abc125", 0, 150, 30),
    ]
    assert all(r.profile is profile for r in profile.reels)
    assert all(r.video_url is None for r in profile.reels)


def test_fetch_profile_requests_reels_tab(reels_tab_html):
    session = _session(text=reels_tab_html)

    fetch_profile("test_user", session)

    assert session.get.call_args.args[0] == "https://www.instagram.com/test_user/reels/"


def test_fetch_profile_without_reels():
    html = _page(
        _relay(
            {
                "xig_user_by_username": {
                    "pk": "1",
                    "username": "test_user",
                    "follower_count": 5,
                }
            }
        )
    )

    profile = fetch_profile("test_user", _session(text=html))

    assert profile.reels == []


def test_fetch_profile_ignores_username_case(reels_tab_html):
    profile = fetch_profile("Test_User", _session(text=reels_tab_html))

    assert profile.username == "test_user"
    assert len(profile.reels) == 2


def test_fetch_profile_ignores_other_accounts_reels(reels_tab_html):
    other = {
        "pk": "999",
        "polaris_clips_connection": {"edges": [_clip("1", "OTHER", 1, 1, 1)]},
    }
    html = _page(_relay({"xig_user_by_username": other})) + reels_tab_html

    profile = fetch_profile("test_user", _session(text=html))

    assert [r.shortcode for r in profile.reels] == ["C_abc123", "C_abc125"]


def test_fetch_profile_raises_when_profile_missing():
    with pytest.raises(InstagramError):
        fetch_profile("test_user", _session(text=_page({"unrelated": True})))


@pytest.mark.parametrize("status_code", [401, 429])
def test_fetch_profile_raises_rate_limit_error(reels_tab_html, status_code):
    with pytest.raises(RateLimitError):
        fetch_profile(
            "test_user", _session(text=reels_tab_html, status_code=status_code)
        )


def test_fetch_profile_raises_rate_limit_error_on_login_redirect():
    session = _session(
        text=_page(),
        url="https://www.instagram.com/accounts/login/?next=%2Ftest_user%2Freels%2F",
    )

    with pytest.raises(RateLimitError):
        fetch_profile("test_user", session)


def test_fetch_reel_adds_video_details(reel_page_html):
    session = _session(
        text=reel_page_html, url="https://www.instagram.com/reel/C_abc123/"
    )

    reel = fetch_reel(_reel(), session)

    assert session.get.call_args.args[0] == "https://www.instagram.com/reel/C_abc123/"
    assert reel.video_url == "https://example.com/video.mp4"
    assert reel.timestamp == datetime.fromtimestamp(1704067200).isoformat()
    assert reel.description == "Test video description"
    assert reel.view_count == 5000


def test_fetch_reel_without_caption(reel_page_html):
    html = reel_page_html.replace('{"text": "Test video description"}', "null")

    reel = fetch_reel(
        _reel(), _session(text=html, url="https://www.instagram.com/reel/C_abc123/")
    )

    assert reel.description == ""


def test_fetch_reel_raises_when_video_missing():
    with pytest.raises(InstagramError):
        fetch_reel(
            _reel(),
            _session(text=_page(), url="https://www.instagram.com/reel/C_abc123/"),
        )


def test_fetch_reel_raises_rate_limit_error_on_login_redirect():
    session = _session(text=_page(), url="https://www.instagram.com/accounts/login/")

    with pytest.raises(RateLimitError):
        fetch_reel(_reel(), session)


def test_reel_video_bytes():
    session = _session(content=b"fake video content")
    reel = _reel(video_url="https://example.com/video.mp4")

    result = reel.video_bytes(session)

    assert isinstance(result, io.BytesIO)
    assert result.getvalue() == b"fake video content"


def test_video_bytes_requires_video_url():
    with pytest.raises(InstagramError):
        _reel().video_bytes(_session())


@pytest.mark.parametrize("status_code", [401, 429])
def test_video_bytes_raises_rate_limit_error(status_code):
    session = _session(status_code=status_code)
    reel = _reel(video_url="https://example.com/video.mp4")

    with pytest.raises(RateLimitError):
        reel.video_bytes(session)
