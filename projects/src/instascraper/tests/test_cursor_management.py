from datetime import datetime
from uuid import uuid4

import pytest
import responses
from instascraper.coreapi import (
    API_URL,
    fetch_cursor,
    update_cursor,
    _make_safe_cursor_target,
)
from requests.exceptions import HTTPError


@pytest.fixture
def mock_cursor():
    return {
        "data": {
            "id": str(uuid4()),
            "target": "test_user",
            "platform": "instagram",
            "cursor": {"last_reel_id": "3364843860104643554"},
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
    }


def test_make_safe_cursor_target():
    # Test basic encoding
    assert _make_safe_cursor_target("simple_user") == "simple_user"

    # Test slash replacement
    assert _make_safe_cursor_target("user/name") == "user-name"

    # Test whitespace stripping
    assert _make_safe_cursor_target("  user_name  ") == "user_name"

    # Test URL encoding of special characters
    result = _make_safe_cursor_target("user@name#test")
    assert "/" not in result


@responses.activate
def test_fetch_cursor_success(mock_cursor):
    target = "test_user"
    _ = responses.add(
        responses.GET,
        f"{API_URL}/media_feeds/cursors/{target}/instagram",
        json=mock_cursor,
        status=200,
    )

    result = fetch_cursor(target)

    assert result == "3364843860104643554"


@responses.activate
def test_fetch_cursor_not_found():
    target = "nonexistent_user"
    _ = responses.add(
        responses.GET,
        f"{API_URL}/media_feeds/cursors/{target}/instagram",
        json={"error": "Not found"},
        status=404,
    )

    result = fetch_cursor(target)
    assert result is None


@responses.activate
def test_fetch_cursor_empty_cursor(mock_cursor):
    target = "test_user"
    mock_cursor["data"]["cursor"] = {}
    _ = responses.add(
        responses.GET,
        f"{API_URL}/media_feeds/cursors/{target}/instagram",
        json=mock_cursor,
        status=200,
    )

    result = fetch_cursor(target)
    assert result is None


@responses.activate
def test_fetch_cursor_with_special_characters(mock_cursor):
    target = "user/with/slashes"
    safe_target = "user-with-slashes"
    _ = responses.add(
        responses.GET,
        f"{API_URL}/media_feeds/cursors/{safe_target}/instagram",
        json=mock_cursor,
        status=200,
    )

    result = fetch_cursor(target)
    assert result == "3364843860104643554"


@responses.activate
def test_fetch_cursor_server_error():
    target = "test_user"
    _ = responses.add(
        responses.GET,
        f"{API_URL}/media_feeds/cursors/{target}/instagram",
        json={"error": "Internal server error"},
        status=500,
    )

    with pytest.raises(HTTPError):
        _ = fetch_cursor(target)


@responses.activate
def test_update_cursor_success():
    target = "test_user"
    cursor = "3364843860104643554"
    _ = responses.add(
        responses.POST,
        f"{API_URL}/media_feeds/cursors/{target}/instagram",
        json={"success": True},
        status=200,
    )

    result = update_cursor(target, cursor)
    assert result is None


@responses.activate
def test_update_cursor_with_special_characters():
    target = "user/with/slashes"
    safe_target = "user-with-slashes"
    cursor = "3364843860104643554"
    _ = responses.add(
        responses.POST,
        f"{API_URL}/media_feeds/cursors/{safe_target}/instagram",
        json={"success": True},
        status=200,
    )

    result = update_cursor(target, cursor)
    assert result is None
