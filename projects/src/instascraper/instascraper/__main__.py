import logging
import os
from uuid import UUID

import structlog
from pas_log import pas_setup_structlog
from scraper_common import GoogleCloudStorageClient, StorageClient

from instascraper import coreapi
from instascraper.scrape import scrape_channel

STORAGE_PATH_PREFIX = "instascraper"
STORAGE_BUCKET_NAME = os.environ["STORAGE_BUCKET_NAME"]

log_level = pas_setup_structlog()
logging.getLogger(__name__).setLevel(log_level)
logger: structlog.BoundLogger = structlog.get_logger(__name__)


type ChannelWatchers = dict[str, list[UUID]]


def channels_downloader(
    channels: ChannelWatchers, storage_client: StorageClient
) -> None:
    for channel, orgs in channels.items():
        log = logger.new(channel_name=channel)
        log.info(f"archiving a new channel: {channel}")
        try:
            cursor = coreapi.fetch_cursor(channel)
            next_cursor = scrape_channel(channel, cursor, storage_client, orgs)
            if next_cursor:
                coreapi.update_cursor(channel, next_cursor)
        except Exception as ex:
            log.error(
                "unexpected error processing channel", media_feed=channel, exc_info=ex
            )


def channel_feeds() -> ChannelWatchers:
    feeds = coreapi.fetch_channel_feeds()
    result: ChannelWatchers = {}
    for feed in feeds:
        if feed.platform != "instagram":
            continue
        channel = feed.channel
        result[channel] = result.get(channel, []) + [feed.organisation_id]
    return result


if __name__ == "__main__":
    log = logger.new()
    log.info("Instascraper starting up...")

    storage_client = GoogleCloudStorageClient(STORAGE_BUCKET_NAME, STORAGE_PATH_PREFIX)
    channels = channel_feeds()
    channels_downloader(channels, storage_client)
