import io
from os import path
from pathlib import Path
from typing import Protocol
import structlog
from google.cloud import storage

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class StorageClient(Protocol):
    def upload_blob(
        self, blob_name: str, buf: io.BytesIO, content_type: str = "video/mp4"
    ) -> str: ...


class DiskStorageClient:
    """Store blobs locally. This is intended mostly for testing purposes."""

    def __init__(self, folder: str):
        self.folder = folder

    def upload_blob(
        self, blob_name: str, buf: io.BytesIO, content_type: str = ""
    ) -> str:
        blob_path = path.join(self.folder, blob_name)
        Path(blob_path).parent.mkdir(parents=True, exist_ok=True)
        with open(blob_path, "wb") as f:
            f.write(buf.getbuffer())
        return blob_path


class GoogleCloudStorageClient:
    def __init__(self, bucket_name: str, path_prefix: str):
        self.bucket_name = bucket_name
        self.path_prefix = path_prefix
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket_name)

    def upload_blob(
        self, blob_name: str, buf: io.BytesIO, content_type: str = "video/mp4"
    ) -> str:
        blob_path = path.join(self.path_prefix, blob_name)
        log = logger.bind(blob_path=blob_path)
        log.debug(f"uploading blob to path {blob_path}")
        blob = self.bucket.blob(blob_path)
        blob.upload_from_file(buf, content_type=content_type)
        return blob_path
