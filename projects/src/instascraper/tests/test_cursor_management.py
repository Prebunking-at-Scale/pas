from datetime import datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from instascraper.coreapi import (
    fetch_cursor,
    update_cursor,
)
from scraper_common.coreapi import CoreAPIClient

_make_safe_cursor_target = CoreAPIClient._make_safe_cursor_target


def test_make_safe_cursor_target():
    assert _make_safe_cursor_target("simple_user") == "simple_user"
    assert _make_safe_cursor_target("user/name") == "user-name"
    assert _make_safe_cursor_target("  user_name  ") == "user_name"
    result = _make_safe_cursor_target("user@name#test")
    assert "/" not in result


@patch("instascraper.coreapi.api_client")
def test_fetch_cursor_success(mock_client):
    mock_client.fetch_cursor.return_value = {"last_reel_id": "3364843860104643554"}

    result = fetch_cursor("test_user")

    assert result == "3364843860104643554"
    mock_client.fetch_cursor.assert_called_once_with("test_user", "instagram")


@patch("instascraper.coreapi.api_client")
def test_fetch_cursor_not_found(mock_client):
    mock_client.fetch_cursor.return_value = None

    result = fetch_cursor("nonexistent_user")

    assert result is None


@patch("instascraper.coreapi.api_client")
def test_fetch_cursor_empty_cursor(mock_client):
    mock_client.fetch_cursor.return_value = {}

    result = fetch_cursor("test_user")

    assert result is None


@patch("instascraper.coreapi.api_client")
def test_update_cursor(mock_client):
    update_cursor("test_user", "3364843860104643554")

    mock_client.update_cursor.assert_called_once_with(
        "test_user", "instagram", {"last_reel_id": "3364843860104643554"}
    )
