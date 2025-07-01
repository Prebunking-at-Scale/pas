import os
import tempfile
from pathlib import Path

from google.cloud.storage import Client as StorageClient
from tubescraper.download import (
    backup_archivefile,
    backup_channel,
    download_archivefile,
    download_channel,
)
from tubescraper.hardcoded_channels import channels

STORAGE_BUCKET_NAME = os.environ["STORAGE_BUCKET_NAME"]
"""The bucket where tubescraper will store all it's output."""

if __name__ == "__main__":
    storage_client = StorageClient()
    storage_bucket = storage_client.bucket(STORAGE_BUCKET_NAME)

    channels: list[str] = channels
    for channel_name in channels:
        with tempfile.TemporaryDirectory() as download_directory:
            archive_path: Path = Path("archives", channel_name)
            download_archivefile(storage_bucket, archive_path)
            download_channel(channel_name, download_directory, archive_path)
            backup_channel(storage_bucket, channel_name, download_directory)
            backup_archivefile(storage_bucket, archive_path)
