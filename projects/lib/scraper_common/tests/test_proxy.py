from unittest.mock import patch

import pytest

from scraper_common.proxy import ProxyConfig


def _make_config(count=3) -> ProxyConfig:
    with patch.dict(
        "os.environ",
        {"PROXY_COUNT": str(count), "PROXY_USERNAME": "user", "PROXY_PASSWORD": "pass"},
    ):
        return ProxyConfig()


class TestDeactivateProxy:
    def test_skips_inactive_proxy(self):
        config = _make_config(count=2)
        config.deactivate_proxy(1, duration=60)

        results = {config.get_proxy_details()[1] for _ in range(20)}
        assert results == {2}

    def test_reactivates_after_duration(self):
        config = _make_config(count=1)
        config.deactivate_proxy(1, duration=10)

        with patch("scraper_common.proxy.time") as mock_time:
            mock_time.monotonic.return_value = config._inactive_until[1] + 1
            _, proxy_id = config.get_proxy_details()

        assert proxy_id == 1

    def test_blocks_when_all_inactive(self):
        config = _make_config(count=1)
        config.deactivate_proxy(1, duration=10)
        deactivation_time = config._inactive_until[1]

        call_count = 0

        def advancing_monotonic():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return deactivation_time - 5
            return deactivation_time + 1

        with patch("scraper_common.proxy.time") as mock_time:
            mock_time.monotonic.side_effect = advancing_monotonic
            mock_time.sleep.return_value = None
            _, proxy_id = config.get_proxy_details()

        assert proxy_id == 1
        mock_time.sleep.assert_called_once()

    def test_sleeps_for_correct_duration(self):
        config = _make_config(count=1)
        config.deactivate_proxy(1, duration=10)
        deactivation_time = config._inactive_until[1]

        call_count = 0

        def advancing_monotonic():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return deactivation_time - 5
            return deactivation_time + 1

        with patch("scraper_common.proxy.time") as mock_time:
            mock_time.monotonic.side_effect = advancing_monotonic
            sleep_durations = []
            mock_time.sleep.side_effect = lambda d: sleep_durations.append(d)
            config.get_proxy_details()

        assert len(sleep_durations) == 1
        assert sleep_durations[0] == pytest.approx(5.0, abs=0.1)

    def test_picks_earliest_reactivation_when_all_inactive(self):
        config = _make_config(count=2)
        config.deactivate_proxy(1, duration=100)
        config.deactivate_proxy(2, duration=10)
        earliest_time = config._inactive_until[2]

        call_count = 0

        def advancing_monotonic():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return earliest_time - 5
            return earliest_time + 1

        with patch("scraper_common.proxy.time") as mock_time:
            mock_time.monotonic.side_effect = advancing_monotonic
            mock_time.sleep = lambda _: None
            _, proxy_id = config.get_proxy_details()

        assert proxy_id == 2

    def test_multiple_deactivations(self):
        config = _make_config(count=3)
        config.deactivate_proxy(1, duration=60)
        config.deactivate_proxy(3, duration=60)

        results = {config.get_proxy_details()[1] for _ in range(20)}
        assert results == {2}

    def test_get_proxy_details_raises_when_not_configured(self):
        with patch.dict("os.environ", {}, clear=True):
            config = ProxyConfig()
        with pytest.raises(ValueError):
            config.get_proxy_details()
