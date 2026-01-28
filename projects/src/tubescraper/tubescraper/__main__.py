import logging
import os
import random
import time
from typing import Iterable
from uuid import UUID

import click
import structlog
from pas_log import pas_setup_structlog
from scraper_common import ChannelFeed, KeywordFeed
from scraper_common.storage import (
    DiskStorageClient,
    GoogleCloudStorageClient,
    StorageClient,
)
from structlog.contextvars import bind_contextvars

from tubescraper.coreapi import PLATFORM, api_client, fetch_cursor, update_cursor
from tubescraper.scrape import rescrape_short, scrape_shorts
from tubescraper.youtube import channel_shorts, id_for_channel, keyword_shorts

type TargetOrgMapping = dict[str, list[UUID]]

SHORTS_PER_TARGET = 50
STORAGE_BUCKET_NAME = os.environ["STORAGE_BUCKET_NAME"]
STORAGE_PATH_PREFIX = "tubescraper"

log_level = pas_setup_structlog()
logging.getLogger(__name__).setLevel(log_level)
logger: structlog.BoundLogger = structlog.get_logger(__name__)


def get_storage_client() -> StorageClient:
    if STORAGE_BUCKET_NAME == "local":
        return DiskStorageClient("youtube")
    return GoogleCloudStorageClient(STORAGE_BUCKET_NAME, STORAGE_PATH_PREFIX)


def preprocess_keyword_feeds(feeds: list[KeywordFeed]) -> TargetOrgMapping:
    """Deduplicates organisation ids from the feeds. We should probably do this in the
    api.
    """
    result: TargetOrgMapping = {}
    for feed in feeds:
        for keyword in feed.keywords:
            result[keyword] = result.get(keyword, []) + [feed.organisation_id]

    return result


def preprocess_channel_feeds(feeds: Iterable[ChannelFeed]) -> TargetOrgMapping:
    result: TargetOrgMapping = {}
    for feed in feeds:
        if feed.platform != "youtube":
            continue
        result[feed.channel] = result.get(feed.channel, []) + [feed.organisation_id]

    return result


def channels_downloader(
    channel_feeds: list[ChannelFeed], storage_client: StorageClient
) -> None:
    log = logger.bind()
    channels = preprocess_channel_feeds(channel_feeds)
    for channel, orgs in channels.items():
        _ = bind_contextvars(channel_name=channel)
        log.info(f"archiving a new channel: {channel}")

        try:
            channel_id = id_for_channel(channel)
            cursor = fetch_cursor(channel_id)
            entries = channel_shorts(channel_id, SHORTS_PER_TARGET)
            next_cursor = scrape_shorts(
                entries, cursor, storage_client, channel_id, orgs
            )
            if next_cursor:
                update_cursor(channel, next_cursor)
        except ValueError as ex:
            log.error(
                "youtube error or media feed probably does not exist, skipping",
                media_feed=channel,
                exc_info=ex,
            )
            continue


def keywords_downloader(
    keyword_feeds: list[KeywordFeed], storage_client: StorageClient
) -> None:
    log = logger.new()

    processed_keywords = preprocess_keyword_feeds(keyword_feeds)

    # Process keywords in a random order to avoid always scraping the same ones
    keywords = list(processed_keywords.keys())
    random.shuffle(keywords)

    for keyword in keywords:
        org_ids = processed_keywords[keyword]

        bind_contextvars(keyword=keyword)
        log.info(f"archiving a new keyword: {keyword}")

        try:
            cursor = fetch_cursor(keyword)
            entries = keyword_shorts(keyword, SHORTS_PER_TARGET)
            next_cursor = scrape_shorts(
                entries, cursor, storage_client, keyword, org_ids
            )
            if next_cursor:
                update_cursor(keyword, next_cursor)
        except ValueError as ex:
            log.error(
                "youtube error or search failed for keyword, skipping",
                keyword=keyword,
                exc_info=ex,
            )
            continue


def rescrape_shorts() -> None:
    log = logger.bind()

    while True:
        log.info("starting new re-scrape pass")
        for target in api_client.get_rescrape_targets(
            PLATFORM, min_age_hours=1, limit=100
        ):
            try:
                log.info(f"rescraping {target['id']}")
                rescrape_short(target)
            except ValueError as ex:
                log.error(
                    "youtube error or rescrape failed",
                    exc_info=ex,
                )
                continue
            time.sleep(3)


@click.group()
def cli() -> None:
    """Scrape YouTube shorts from channels or keywords."""
    pass


@cli.command()
def channels() -> None:
    """Scrape YouTube shorts from channels."""
    log = logger.new()
    log.info("Tubescraper starting up...", mode="channels")

    storage_client = get_storage_client()
    channel_feeds = api_client.fetch_channel_feeds()
    channels_downloader(channel_feeds, storage_client)


@cli.command()
def keywords() -> None:
    """Scrape YouTube shorts from keywords."""
    log = logger.new()
    log.info("Tubescraper starting up...", mode="keywords")

    storage_client = get_storage_client()
    keyword_feeds = api_client.fetch_keyword_feeds()
    keywords_downloader(keyword_feeds, storage_client)


@cli.command()
def rescrape() -> None:
    """Rescrape YouTube shorts"""
    log = logger.new()
    log.info("Tubescraper starting up...", mode="rescrape")
    rescrape_shorts()


if __name__ == "__main__":
    cli()
