import random
from datetime import datetime, timedelta

from dotenv import load_dotenv
from tubescraper.register import fetch_cursor
from tubescraper.types import ChannelFeed, KeywordFeed

_ = load_dotenv()


import logging
import os
import tempfile

import structlog
from google.cloud.storage import Bucket
from google.cloud.storage import Client as StorageClient
from pas_log import pas_setup_structlog
from structlog.contextvars import bind_contextvars
from tubescraper.channel_downloads import (
    channel_download_hook,
    download_channel,
    fetch_channel_feeds,
    id_for_channel,
)
from tubescraper.keyword_downloads import (
    backup_keyword_entries,
    fetch_keyword_feeds,
)

log_level = pas_setup_structlog()
logging.getLogger(__name__).setLevel(log_level)
logger: structlog.BoundLogger = structlog.get_logger(__name__)

STORAGE_BUCKET_NAME = os.environ["STORAGE_BUCKET_NAME"]
"""The bucket where tubescraper will store all it's output."""


def channels_downloader(channels: list[ChannelFeed], storage_bucket: Bucket) -> None:
    log = logger.bind()
    for channel in channels:
        if channel.platform != "youtube":
            continue

        channel_source = channel.channel
        _ = bind_contextvars(channel_source=channel_source)
        log.info(f"archiving a new channel: {channel_source}")

        with tempfile.TemporaryDirectory() as download_directory:
            log.debug("downloading to temporary directory")
            try:
                hook = channel_download_hook(storage_bucket, channel.organisation_id)
                channel_id = id_for_channel(channel_source)
                cursor_dt = fetch_cursor(channel_id, channel.platform)
                if not cursor_dt:
                    cursor_dt = datetime.now() - timedelta(days=31)
                info = download_channel(channel_id, download_directory, cursor_dt, hook)
                if not info:
                    log.error("no info, skipping channel backup")
                    continue
            except ValueError as exc:
                log.error("Error with channel {channel_source}", exc_info=exc)
                continue


def keywords_downloader(keyword_feeds: list[KeywordFeed], storage_bucket: Bucket) -> None:
    log = logger.bind()

    # Process keywords in a random order to avoid always scraping the same ones
    random.shuffle(keyword_feeds)
    for feed in keyword_feeds:
        for keyword in feed.keywords:
            _ = bind_contextvars(keyword=keyword)
            log.info(f"archiving a new keyword: {keyword}")

            cursor_dt = fetch_cursor(keyword, "youtube")
            backup_keyword_entries(storage_bucket, keyword, cursor_dt, feed.organisation_id)


if __name__ == "__main__":
    log = logger.new()
    log.info("Tubescraper starting up...")

    storage_client = StorageClient()
    storage_bucket = storage_client.bucket(STORAGE_BUCKET_NAME)
    log.debug("buckets configured")

    channels = fetch_channel_feeds()
    channels_downloader(channels, storage_bucket)

    keywords = fetch_keyword_feeds()
    keywords_downloader(keywords, storage_bucket)
