from dotenv import load_dotenv

_ = load_dotenv()


import gc
import logging
import os
import tempfile

import structlog
from google.cloud.storage import Bucket
from google.cloud.storage import Client as StorageClient
from pas_log import pas_setup_structlog
from structlog.contextvars import bind_contextvars
from tubescraper.channel_downloads import (
    backup_archivefile,
    download_archivefile,
    download_channel,
    fix_archivefile,
    id_for_channel,
)
from tubescraper.hardcoded_channels import OrgName, channels, preprocess_channels
from tubescraper.hardcoded_keywords import org_keywords, preprocess_keywords
from tubescraper.keyword_downloads import (
    backup_cursor,
    backup_keyword_entries,
    download_cursor,
    download_existing_ids_for_keyword,
)

log_level = pas_setup_structlog()
logging.getLogger(__name__).setLevel(log_level)
logger: structlog.BoundLogger = structlog.get_logger(__name__)

STORAGE_BUCKET_NAME = os.environ["STORAGE_BUCKET_NAME"]
"""The bucket where tubescraper will store all it's output."""


def channels_downloader(storage_bucket: Bucket) -> None:
    log = logger.bind()
    channel_map = preprocess_channels(channels)
    for channel_source, orgs in channel_map.items():
        _ = bind_contextvars(channel_source=channel_source)
        log.info(f"archiving a new channel: {channel_source}")

        with tempfile.TemporaryDirectory() as download_directory:
            log.debug("downloading to temporary directory")
            archivefile: str = f"{channel_source}_state"
            try:
                channel_id = id_for_channel(channel_source)

                download_archivefile(storage_bucket, archivefile)
                # XXX: please remove this when archives exist or we do it via api
                fix_archivefile(storage_bucket, archivefile, channel_id)

                info = download_channel(
                    channel_id,
                    download_directory,
                    archivefile,
                    storage_bucket,
                    orgs,
                )
                if not info:
                    log.error("no info, skipping channel backup")
                    continue

                backup_archivefile(storage_bucket, archivefile)
            except ValueError as exc:
                log.error("Error with channel {channel_source}", exc_info=exc)
                continue


def keywords_downloader(storage_bucket: Bucket) -> None:
    log = logger.bind()
    keywords: dict[str, list[OrgName]] = preprocess_keywords(org_keywords)
    for keyword, orgs in keywords.items():
        _ = bind_contextvars(keyword=keyword)
        log.info(f"archiving a new keyword: {keyword}")

        cursor = download_cursor(storage_bucket, keyword)
        existing = download_existing_ids_for_keyword(storage_bucket, keyword)
        new_cursor = backup_keyword_entries(storage_bucket, keyword, cursor, existing, orgs)
        backup_cursor(storage_bucket, keyword, new_cursor)

        # maybe fix memory leak?
        _ = gc.collect()


if __name__ == "__main__":
    log = logger.new()
    log.info("Tubescraper starting up...")

    storage_client = StorageClient()
    storage_bucket = storage_client.bucket(STORAGE_BUCKET_NAME)
    log.debug("buckets configured")

    # channels_downloader(storage_bucket)
    keywords_downloader(storage_bucket)
