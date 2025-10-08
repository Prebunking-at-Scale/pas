from dotenv import load_dotenv

_ = load_dotenv()

import logging
import os
import tempfile
from datetime import datetime, timedelta

import structlog
from google.cloud.storage import Bucket
from google.cloud.storage import Client as StorageClient
from pas_log import pas_setup_structlog
from structlog.contextvars import bind_contextvars
from tokscraper.channel_downloads import (
    channel_download_hook,
    download_channel,
    fetch_channel_feeds,
)
from tokscraper.register import fetch_cursor
from tokscraper.types import ChannelFeed

log_level = pas_setup_structlog()
logging.getLogger(__name__).setLevel(log_level)
logger: structlog.BoundLogger = structlog.get_logger(__name__)

STORAGE_BUCKET_NAME = os.environ["STORAGE_BUCKET_NAME"]
"""The bucket where tokscraper will store all it's output."""


def channels_downloader(channels: list[ChannelFeed], storage_bucket: Bucket) -> None:
    log = logger.bind()
    for channel in channels:
        if channel.platform != "tiktok":
            continue

        channel_source = channel.channel

        _ = bind_contextvars(channel_source=channel_source)
        log.info(f"archiving a new channel: {channel_source}")

        with tempfile.TemporaryDirectory() as download_directory:
            log.debug("downloading to temporary directory")
            try:
                hook = channel_download_hook(storage_bucket, channel.organisation_id)
                cursor_dt = fetch_cursor(channel_source, channel.platform)
                if not cursor_dt:
                    cursor_dt = datetime.now() - timedelta(days=31)
                info = download_channel(channel_source, download_directory, cursor_dt, hook)
                if not info:
                    log.error("no info, skipping channel backup")
                    continue
            except ValueError as exc:
                log.error("Error with channel {channel_source}", exc_info=exc)
                continue


if __name__ == "__main__":
    log = logger.new()
    log.info("tokscraper starting up...")

    storage_client = StorageClient()
    storage_bucket = storage_client.bucket(STORAGE_BUCKET_NAME)
    log.debug("buckets configured")

    channels = fetch_channel_feeds()
    channels_downloader(channels, storage_bucket)
