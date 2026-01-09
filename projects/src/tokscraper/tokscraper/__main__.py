from dotenv import load_dotenv

_ = load_dotenv()

import logging
import os
from datetime import datetime, timedelta

import structlog
from google.cloud.storage import Bucket
from google.cloud.storage import Client as StorageClient
from pas_log import pas_setup_structlog
from structlog.contextvars import bind_contextvars
from tokscraper.channel_downloads import (
    backup_channel_entries,
    fetch_channel_feeds,
    preprocess_channel_feeds,
)
from tokscraper.register import fetch_cursor
from tokscraper.types import ChannelFeed

log_level = pas_setup_structlog()
logging.getLogger(__name__).setLevel(log_level)
logger: structlog.BoundLogger = structlog.get_logger(__name__)

STORAGE_BUCKET_NAME = os.environ["STORAGE_BUCKET_NAME"]
"""The bucket where tokscraper will store all it's output."""


def channels_downloader(
    channel_feeds: list[ChannelFeed], storage_bucket: Bucket
) -> None:
    log = logger.bind()
    channels = preprocess_channel_feeds(channel_feeds)
    for channel, orgs in channels.items():
        _ = bind_contextvars(channel_name=channel)
        log.info(f"archiving a new channel: {channel}")

        try:
            cursor_dt = fetch_cursor(channel)
            if not cursor_dt:
                cursor_dt = datetime.now() - timedelta(days=14)

            backup_channel_entries(storage_bucket, channel, cursor_dt, orgs)
        except ValueError as ex:
            log.error(
                "tiktok error or media feed probably does not exist, skipping",
                media_feed=channel,
                exc_info=ex,
            )
            continue


if __name__ == "__main__":
    log = logger.new()
    log.info("Tokscraper starting up...")

    storage_client = StorageClient()
    storage_bucket = storage_client.bucket(STORAGE_BUCKET_NAME)
    log.debug("buckets configured")

    channels = fetch_channel_feeds()
    channels_downloader(channels, storage_bucket)
