import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import tubescraper.download as download
from google.cloud.storage import Blob, Bucket


@pytest.fixture
def mock_bucket() -> Bucket:
    bucket = MagicMock(spec=Bucket)
    bucket.get_blob.return_value = None
    blob = MagicMock(spec=Blob)
    bucket.blob.return_value = blob
    return bucket


def test_download_channel_calls_extract_info() -> None:
    with patch("tubescraper.download.yt_dlp.YoutubeDL") as mock_ydl_cls:
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {"id": "123"}
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl

        download.download_channel("@testchannel", "/tmp", "archive.txt")

        mock_ydl.extract_info.assert_called_once()
        url = mock_ydl.extract_info.call_args[0][0]
        assert url.startswith("https://youtube.com/@testchannel/shorts")


def test_download_archivefile_downloads_file(mock_bucket: Bucket) -> None:
    blob_mock = MagicMock(spec=Blob)
    mock_bucket.get_blob.return_value = blob_mock

    archive_path = "archive.txt"
    download.download_archivefile(mock_bucket, archive_path)

    mock_bucket.get_blob.assert_called_once_with(
        str(download.STORAGE_PATH_PREFIX / archive_path)
    )
    blob_mock.download_to_filename.assert_called_once_with(filename=archive_path)


def test_download_archivefile_no_blob(mock_bucket: Bucket) -> None:
    mock_bucket.get_blob.return_value = None
    archive_path = "archive.txt"

    download.download_archivefile(mock_bucket, archive_path)


def test_backup_channel_uploads_files(tmp_path: Path, mock_bucket: Bucket) -> None:
    channel_name = "@channel"
    file1 = tmp_path / "video1.mp4"
    file1.write_text("dummy content")
    file2 = tmp_path / "video2.srt"
    file2.write_text("subtitle content")

    download.backup_channel(mock_bucket, channel_name, str(tmp_path))

    assert mock_bucket.blob.call_count == 2

    upload_calls = mock_bucket.blob.return_value.upload_from_filename.call_args_list
    assert len(upload_calls) == 2


def test_backup_archivefile_uploads_file(mock_bucket: Bucket) -> None:
    archive_path = "archive.txt"
    with open(archive_path, "w") as f:
        f.write("dummy content")

    download.backup_archivefile(mock_bucket, archive_path)

    mock_bucket.blob.return_value.upload_from_filename.assert_called_once_with(archive_path)

    os.remove(archive_path)
