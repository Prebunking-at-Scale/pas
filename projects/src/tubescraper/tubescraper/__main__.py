from dotenv import load_dotenv

_ = load_dotenv()

import logging
import os
import tempfile

import structlog
from google.cloud.storage import Client as StorageClient
from pas_log import pas_setup_structlog
from structlog.contextvars import bind_contextvars
from tubescraper.download import (
    backup_archivefile,
    backup_channel,
    download_archivefile,
    download_channel,
    register_downloads,
)
from tubescraper.hardcoded_channels import channels, preprocess_channels

log_level = pas_setup_structlog()
logging.getLogger(__name__).setLevel(log_level)
logger: structlog.BoundLogger = structlog.get_logger(__name__)

STORAGE_BUCKET_NAME = os.environ["STORAGE_BUCKET_NAME"]
"""The bucket where tubescraper will store all it's output."""

if __name__ == "__main__":
    log = logger.new()
    log.info("Tubescraper starting up...")

    storage_client = StorageClient()
    storage_bucket = storage_client.bucket(STORAGE_BUCKET_NAME)
    log.debug("buckets configured")

    channel_map = preprocess_channels(channels)
    for channel_name, orgs in channel_map.items():
        _ = bind_contextvars(channel_name=channel_name)
        log.info(f"archiving a new channel: {channel_name}")

        with tempfile.TemporaryDirectory() as download_directory:
            log.debug("downloading to temporary directory")
            archivefile: str = f"{channel_name}_state"
            download_archivefile(storage_bucket, archivefile)

            info = download_channel(channel_name, download_directory, archivefile)
            if not info:
                log.error("no info, skipping channel backup")
                continue

            register_downloads(info, channel_name, orgs)

            backup_channel(storage_bucket, channel_name, download_directory)
            backup_archivefile(storage_bucket, archivefile)
