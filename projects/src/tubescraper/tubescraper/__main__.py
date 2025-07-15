import logging
import os
import tempfile
from pathlib import Path

import structlog
from google.cloud.storage import Client as StorageClient
from pas_log import pas_setup_structlog
from structlog.contextvars import bind_contextvars
from tubescraper.download import (
    backup_archivefile,
    backup_channel,
    download_archivefile,
    download_channel,
)
from tubescraper.hardcoded_channels import channels

log_level = pas_setup_structlog()
logging.getLogger().setLevel(log_level)
logger: structlog.BoundLogger = structlog.get_logger()

STORAGE_BUCKET_NAME = os.environ["STORAGE_BUCKET_NAME"]
"""The bucket where tubescraper will store all it's output."""

if __name__ == "__main__":
    log = logger.new()
    log.info("Tubescraper starting up...")

    storage_client = StorageClient()
    storage_bucket = storage_client.bucket(STORAGE_BUCKET_NAME)
    log.debug("buckets configured")

    channels: list[str] = channels
    for channel_name in channels:
        _ = bind_contextvars(channel_name=channel_name)
        log.info(f"archiving a new channel: {log.get_context().get("channel_name")}")

        with tempfile.TemporaryDirectory() as download_directory:
            log.debug("downloading to temporary directory")
            archive_path: Path = Path("archives", channel_name)
            download_archivefile(storage_bucket, archive_path)
            download_channel(channel_name, download_directory, archive_path)
            backup_channel(storage_bucket, channel_name, download_directory)
            backup_archivefile(storage_bucket, archive_path)
