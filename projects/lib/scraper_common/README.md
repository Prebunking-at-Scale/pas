# scraper_common

Shared functionality for PAS scrapers (tubescraper, tokscraper, instascraper).

## Contents

- **types.py**: Shared Pydantic models (MediaFeed, ChannelFeed, KeywordFeed, Cursor)
- **coreapi.py**: CoreAPIClient for interacting with the Core API
- **proxy.py**: Proxy configuration utilities
- **storage.py**: Storage abstraction (GCS and local disk)
