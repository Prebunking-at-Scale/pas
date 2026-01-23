import logging
import os

import structlog
from pas_log import pas_setup_structlog
from scraper_common import ChannelFeed, GoogleCloudStorageClient, StorageClient
from scraper_common.storage import DiskStorageClient
from structlog.contextvars import bind_contextvars

from tokscraper import coreapi
from tokscraper.coreapi import fetch_cursor
from tokscraper.scrape import (
    download_channel_shorts,
    preprocess_channel_feeds,
)

STORAGE_BUCKET_NAME = os.environ["STORAGE_BUCKET_NAME"]
STORAGE_PATH_PREFIX = "tokscraper"

log_level = pas_setup_structlog()
logging.getLogger(__name__).setLevel(log_level)
logger: structlog.BoundLogger = structlog.get_logger(__name__)


def channels_downloader(
    channel_feeds: list[ChannelFeed], storage_client: StorageClient
) -> None:
    log = logger.bind()
    channels = preprocess_channel_feeds(channel_feeds)
    for channel, orgs in channels.items():
        _ = bind_contextvars(channel_name=channel)
        log.info(f"archiving a new channel: {channel}")

        try:
            cursor = fetch_cursor(channel)
            log.debug(f"using cursor {cursor}")
            next_cursor = download_channel_shorts(channel, cursor, storage_client, orgs)
            if next_cursor:
                coreapi.update_cursor(channel, next_cursor)

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

    if STORAGE_BUCKET_NAME == "local":
        storage_client = DiskStorageClient("tiktok")
    else:
        storage_client = GoogleCloudStorageClient(
            STORAGE_BUCKET_NAME, STORAGE_PATH_PREFIX
        )
    channels = coreapi.api_client.fetch_channel_feeds()
    channels_downloader(channels, storage_client)
