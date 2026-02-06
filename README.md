# Prebunking at scale

## Introduction

This is a monorepo for the prebunking-at-scale project, consisting of the infrastructure,
deployment tooling and application code. It is a work-in-progress and do expect process
and code changes as we refine the approach over the coming weeks.

## Getting started

### Installation

To install the repository just run:

`uv sync --all-packages`

from the repository root.

### Building the Scrapers

All three scrapers (instascraper, tokscraper, tubescraper) share a common base Docker image defined in the root `Containerfile`. Each scraper has its own Containerfile in `projects/src/<scraper>/`.

Images are built and pushed automatically by the **Build and Push Docker Images** workflow (`.github/workflows/build-images.yml`).

#### When builds run

- On every push to `main` or `dev`
- On manual trigger via `workflow_dispatch`

The workflow uses path filtering to only rebuild what changed:

| Change | What rebuilds |
|--------|---------------|
| `Containerfile`, `pyproject.toml`, `uv.lock`, `projects/lib/**` | Base image + all scrapers |
| `projects/src/tubescraper/**` | tubescraper only |
| `projects/src/tokscraper/**` | tokscraper only |
| `projects/src/instascraper/**` | instascraper only |

Manual triggers (`workflow_dispatch`) rebuild everything.

#### Tagging

Each scraper image is automatically tagged with:
- A semver version tag (e.g. `v1.2.3`) — bumped automatically per scraper
- `latest` for builds from `main`, `dev` for builds from `dev`

Tags follow the format `<scraper>/vX.Y.Z` (e.g. `tubescraper/v0.5.0`). A GitHub release is created for each build.

#### Images

All images are pushed to Google Artifact Registry:

```
europe-west4-docker.pkg.dev/pas-shared/pas/<scraper>:<tag>
```

#### Building locally

You can still build locally with docker compose for development:

```bash
DOCKER_DEFAULT_PLATFORM=linux/amd64 docker build -t base_image .
DOCKER_DEFAULT_PLATFORM=linux/amd64 docker compose build
```

**Note:** The `tokscraper` and `tubescraper` images include additional system dependencies (`ffmpeg` and `deno`) required by `yt-dlp` for video downloading.

### Deployment

Deployments use [Kustomize](https://kustomize.io/) with base manifests in `deployments/base/` and environment overlays in `deployments/dev/` and `deployments/prod/`.

#### Automatic deployment to dev

Pushes to the `dev` branch automatically deploy to the dev cluster after images are built. This is handled by the `deploy-dev` job in the build workflow. It runs `kubectl apply -k deployments/dev` and restarts the rescrape deployments.

#### Manual deployment (production and dev)

Use the **Deploy Scraper** workflow (`.github/workflows/deploy.yml`) via GitHub Actions:

1. Go to **Actions > Deploy Scraper > Run workflow**
2. Select the scraper to deploy (`tubescraper`, `tokscraper`, or `instascraper`)
3. Optionally provide a git tag (e.g. `tubescraper/v0.5.0`)
   - If no tag is provided, it deploys the latest production release (the highest non-prerelease tag)
   - Tags with a prerelease suffix (e.g. `v0.5.0-beta.1`) deploy to **dev**
   - Tags without a prerelease suffix (e.g. `v0.5.0`) deploy to **prod**

The workflow sets the image tag via kustomize and applies the appropriate overlay (`deployments/dev/` or `deployments/prod/`) to the corresponding GKE cluster.

#### Environments

| Environment | GCP Project | Cluster | Triggered by |
|-------------|-------------|---------|--------------|
| dev | pas-development-1 | dev-cluster | Push to `dev` branch, or manual deploy with prerelease tag |
| prod | pas-production-1 | prod-cluster | Manual deploy with release tag |

#### Manual deployment with kustomize

If you need to deploy without GitHub Actions (e.g. for debugging or urgent fixes), you can apply the kustomize overlays directly.

1. Get credentials for the target cluster:

```bash
# Dev
gcloud container clusters get-credentials dev-cluster --project pas-development-1 --location europe-west4-b

# Prod
gcloud container clusters get-credentials prod-cluster --project pas-production-1 --location europe-west4-b
```

2. To deploy all scrapers at the default image tag (`latest` for prod, `dev` for dev):

```bash
kubectl apply -k deployments/prod
# or
kubectl apply -k deployments/dev
```

3. To deploy a specific version of a single scraper, use `kustomize edit set image` to override the tag before applying:

```bash
cd deployments/prod
kustomize edit set image europe-west4-docker.pkg.dev/pas-shared/pas/tubescraper:v1.2.3
kubectl apply -k .
```

**Note:** `kustomize edit set image` modifies `kustomization.yaml` in place. Avoid committing these local tag overrides — they are managed by CI during normal deployments.

---

## Configuration

All scrapers share common configuration via environment variables from the shared libraries.

### Storage Configuration

The `STORAGE_BUCKET_NAME` environment variable controls where videos are stored:

| Value | Storage Type | Description |
|-------|--------------|-------------|
| `"local"` | Local Disk | Stores videos in a local directory (useful for development) |
| `"my-bucket-name"` | Google Cloud Storage | Stores videos in the specified GCS bucket |

**Local storage paths:**
- Tubescraper: `./youtube/`
- Tokscraper: `./tiktok/`
- Instascraper: `./instascraper/`

**Example:**
```bash
# Use local storage for development
export STORAGE_BUCKET_NAME="local"

# Use GCS for production
export STORAGE_BUCKET_NAME="pas-production-storage"
```

### Core API Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `API_URL` | `http://localhost:8000/` | Base URL for the Core API (tubescraper/tokscraper) |
| `API_KEYS` | `["abc123"]` | JSON array of API keys (first key is used) |

**Note:** Instascraper defaults to port 3000 for `API_URL`.

### Proxy Configuration (scraper_common)

For production use with rate-limited platforms, configure proxy rotation:

| Variable | Default | Description |
|----------|---------|-------------|
| `PROXY_COUNT` | `0` | Number of available proxies from webshare.io |
| `PROXY_USERNAME` | `""` | Proxy authentication username |
| `PROXY_PASSWORD` | `""` | Proxy authentication password |

**Note:** All three proxy variables must be set together for proxying to work. If any are missing, proxying is disabled.

### Logging Configuration (pas_log)

| Variable | Default | Description |
|----------|---------|-------------|
| `ROOT_LOG_LEVEL` | `"warn"` | Log level for root logger (external libraries) |
| `APP_LOG_LEVEL` | `"info"` | Log level for application (structlog) |

Valid levels: `debug`, `info`, `warn`, `error` (case-insensitive)

### Platform-Specific Configuration

**Tubescraper only:**

| Variable | Default | Description |
|----------|---------|-------------|
| `POT_PROVIDER_URL` | `""` | URL for YouTube POT (Proof of Origin Token) provider |

---

## Scrapers

### Instascraper

**Platform:** Instagram

**Purpose:** Archives Instagram reels from configured user profiles.

**How it works:**
1. Fetches list of Instagram channels from the Core API
2. For each channel, fetches the user's profile using Instagram's public web API
3. Extracts up to 12 most recent reels from the profile
4. Downloads video bytes and uploads to Google Cloud Storage
5. Registers video metadata with the Core API
6. Tracks cursor (last reel ID) per channel to avoid re-downloading

**Command Line Options:**

```bash
python -m instascraper
```

No subcommands - runs the channel scraper directly on startup.

**Environment Variables:**
- `STORAGE_BUCKET_NAME` (required) - GCS bucket name or `"local"` for local disk storage
- `API_URL` (default: `http://localhost:3000/`) - Core API base URL
- `API_KEYS` - JSON array of API keys

---

### Tokscraper

**Platform:** TikTok

**Purpose:** Archives TikTok shorts from configured creator accounts with optional stats rescraping.

**How it works:**
1. Fetches list of TikTok channels from the Core API
2. Uses `yt-dlp` to extract video entries from each TikTok channel
3. Downloads up to 200 shorts per channel (max 14-day lookback)
4. Uploads videos to Google Cloud Storage and registers metadata
5. Tracks timestamp cursor per channel to avoid re-downloading

**Command Line Options:**

```bash
python -m tokscraper [COMMAND]
```

| Command | Description |
|---------|-------------|
| `channels` | Scrape TikTok shorts from configured channels (default) |
| `rescrape` | Continuously rescrape existing shorts to update view counts and stats |

**Examples:**
```bash
# Run channel scraper (default)
python -m tokscraper
python -m tokscraper channels

# Run rescraper (infinite loop)
python -m tokscraper rescrape
```

**Environment Variables:**
- `STORAGE_BUCKET_NAME` (required) - GCS bucket name or `"local"` for local disk storage
- `API_URL` (default: `http://localhost:8000/`) - Core API base URL
- `API_KEYS` - JSON array of API keys
- `PROXY_COUNT`, `PROXY_USERNAME`, `PROXY_PASSWORD` - Proxy configuration (optional)

---

### Tubescraper

**Platform:** YouTube

**Purpose:** Archives YouTube shorts from configured channels or keyword searches, with stats update capability.

**How it works:**
1. Fetches YouTube channel or keyword feeds from the Core API
2. Uses `yt-dlp` to fetch up to 100 shorts per channel/keyword (max 14-day lookback)
3. Downloads videos and uploads to Google Cloud Storage
4. Only updates stats for existing videos if view count increased by 10%+
5. Tracks timestamp cursor per channel/keyword to avoid re-downloading

**Command Line Options:**

```bash
python -m tubescraper [COMMAND]
```

| Command | Description |
|---------|-------------|
| `channels` | Scrape YouTube shorts from configured channels (default) |
| `keywords` | Scrape YouTube shorts from keyword searches |
| `rescrape` | Continuously rescrape existing shorts to update view counts and stats |

**Examples:**
```bash
# Run channel scraper (default)
python -m tubescraper
python -m tubescraper channels

# Run keyword scraper
python -m tubescraper keywords

# Run rescraper (infinite loop)
python -m tubescraper rescrape
```

**Environment Variables:**
- `STORAGE_BUCKET_NAME` (required) - GCS bucket name or `"local"` for local disk storage
- `API_URL` (default: `http://localhost:8000/`) - Core API base URL
- `API_KEYS` - JSON array of API keys
- `POT_PROVIDER_URL` - YouTube POT provider URL (optional, for avoiding rate limits)
- `PROXY_COUNT`, `PROXY_USERNAME`, `PROXY_PASSWORD` - Proxy configuration (optional)

---

## Scraper Comparison

| Feature | Instascraper | Tokscraper | Tubescraper |
|---------|--------------|------------|-------------|
| Platform | Instagram | TikTok | YouTube |
| Scraping Method | Instagram API | yt-dlp | yt-dlp |
| Keyword Search | No | No | Yes |
| Rescrape Support | No | Yes | Yes |
| Max Lookback | Unlimited | 14 days | 14 days |
| Extra Dependencies | None | ffmpeg, deno | ffmpeg, deno |

---

