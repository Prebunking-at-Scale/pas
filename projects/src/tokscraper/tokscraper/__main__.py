import logging
import os
import time

import click
import structlog
from pas_log import pas_setup_structlog
from scraper_common import ChannelFeed, GoogleCloudStorageClient, StorageClient
from scraper_common.storage import DiskStorageClient
from structlog.contextvars import bind_contextvars

from tokscraper import coreapi
from tokscraper.coreapi import PLATFORM, fetch_cursor
from tokscraper.scrape import (
    download_channel_shorts,
    preprocess_channel_feeds,
    rescrape_short,
)

STORAGE_BUCKET_NAME = os.environ["STORAGE_BUCKET_NAME"]
STORAGE_PATH_PREFIX = "tokscraper"

log_level = pas_setup_structlog()
logging.getLogger(__name__).setLevel(log_level)
logger: structlog.BoundLogger = structlog.get_logger(__name__)


def get_storage_client() -> StorageClient:
    if STORAGE_BUCKET_NAME == "local":
        return DiskStorageClient("tiktok")
    return GoogleCloudStorageClient(STORAGE_BUCKET_NAME, STORAGE_PATH_PREFIX)


def rescrape_shorts() -> None:
    log = logger.bind()

    while True:
        log.info("starting new re-scrape pass")
        for target in coreapi.api_client.get_rescrape_targets(
            PLATFORM, min_age_hours=1, limit=100
        ):
            try:
                log.info(f"rescraping {target['id']}")
                rescrape_short(target)
            except ValueError as ex:
                log.error(
                    "tiktok error or rescrape failed",
                    exc_info=ex,
                )
                continue
        time.sleep(60)


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


@click.group()
def cli() -> None:
    """Scrape TikTok shorts from channels."""
    pass


@cli.command()
def channels() -> None:
    """Scrape TikTok shorts from channels."""
    log = logger.new()
    log.info("Tokscraper starting up...", mode="channels")

    storage_client = get_storage_client()
    channel_feeds = coreapi.api_client.fetch_channel_feeds()
    channels_downloader(channel_feeds, storage_client)


@cli.command()
def rescrape() -> None:
    """Rescrape TikTok shorts to update stats."""
    log = logger.new()
    log.info("Tokscraper starting up...", mode="rescrape")
    rescrape_shorts()


if __name__ == "__main__":
    cli()
