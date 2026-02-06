from os import path
from uuid import UUID

import structlog
from scraper_common import DiskStorageClient, StorageClient

from instascraper import coreapi, instagram

logger: structlog.BoundLogger = structlog.get_logger(__name__)


def scrape_channel(
    channel: str, cursor: str | None, storage_client: StorageClient, org_ids: list[UUID]
) -> str | None:
    log = logger.new(cursor=cursor, channel=channel)

    next_cursor = None
    profile = instagram.fetch_profile(channel)
    reels = profile.reels
    log.debug(f"got {len(reels)} reels for user")
    for reel in reels:
        try:
            if reel.id == cursor:
                break

            bytes = reel.video_bytes()
            blob_name = path.join(channel, f"{reel.id}.mp4")
            blob_path = storage_client.upload_blob(blob_name, bytes)
            coreapi.register_download(reel, org_ids, blob_path)

            if not next_cursor:
                # The first video will be the most recent
                next_cursor = reel.id

        except Exception as ex:
            log.error(
                "exception with downloading, skipping entry",
                event_metric="download_failure",
                exc_info=ex,
            )

    return next_cursor


if __name__ == "__main__":
    storage_client = DiskStorageClient("./reels/")
    next_cursor = scrape_channel("alimasadia_", "3364843860104643554", storage_client, [])
    print(next_cursor)
