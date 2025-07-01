from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import tubescraper.download as download


@pytest.fixture
def mock_bucket():
    bucket = MagicMock()
    bucket.get_blob.return_value = None
    bucket.blob.return_value = MagicMock()
    return bucket


def test_download_channel_calls_extract_info():
    with patch("tubescraper.download.yt_dlp.YoutubeDL") as mock_ydl_cls:
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {"id": "123"}
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl

        download.download_channel("@testchannel", "/tmp", Path("/tmp/archive.txt"))

        mock_ydl.extract_info.assert_called_once()
        url = mock_ydl.extract_info.call_args[0][0]
        assert url.startswith("https://youtube.com/@testchannel/shorts")


def test_download_channel_raises_on_bad_info():
    with patch("tubescraper.download.yt_dlp.YoutubeDL") as mock_ydl_cls:
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = None
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl

        with pytest.raises(Exception, match="ydl: no info dict?"):
            download.download_channel("@testchannel", "/tmp", Path("/tmp/archive.txt"))


def test_download_archivefile_downloads_file(mock_bucket, tmp_path):
    blob_mock = MagicMock()
    mock_bucket.get_blob.return_value = blob_mock

    archive_path = Path("archive.txt")
    download.download_archivefile(mock_bucket, archive_path)

    mock_bucket.get_blob.assert_called_once_with(download.STORAGE_PATH_PREFIX / archive_path)
    blob_mock.download_to_filename.assert_called_once_with(filename=archive_path)


def test_download_archivefile_no_blob(mock_bucket):
    mock_bucket.get_blob.return_value = None
    archive_path = Path("archive.txt")

    download.download_archivefile(mock_bucket, archive_path)


def test_backup_channel_uploads_files(tmp_path, mock_bucket):
    channel_name = "@channel"
    file1 = tmp_path / "video1.mp4"
    file1.write_text("dummy content")
    file2 = tmp_path / "video2.srt"
    file2.write_text("subtitle content")

    download.backup_channel(mock_bucket, channel_name, str(tmp_path))

    assert mock_bucket.blob.call_count == 2
    for call in mock_bucket.blob.return_value.upload_from_file.call_args_list:
        assert call is not None


def test_backup_archivefile_uploads_file(mock_bucket):
    path = Path("archive.txt")
    download.backup_archivefile(mock_bucket, path)
    mock_bucket.blob.assert_called_once_with(path)
    mock_bucket.blob.return_value.upload_from_filename.assert_called_once_with(path)
