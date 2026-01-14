Instascraper is a scraper for Instagram that scrapes reels from user profiles.

The scraper is designed to scrape new content (i.e. it is not an archiver of old content) by fetching pages on a regular basis.

### Environment Variables
The following environment variables are required:
```
export API_URL=http://localhost:3000
export API_KEYS='["abc123"]'
export PROXY_COUNT=50
export PROXY_USERNAME=username
export PROXY_PASSWORD=password
```

It's possible to leave the `PROXY_` values unset, in which case no proxy will be used, however this is not recommended
due to Instagram's frequent account blocks.