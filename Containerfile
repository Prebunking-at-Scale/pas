FROM python:3.13-alpine
COPY --from=ghcr.io/astral-sh/uv:alpine /usr/local/bin/uv /bin/uv

WORKDIR /app

# alpine equivalent of build-essentials
RUN apk add --no-cache build-base python3-dev musl-dev linux-headers

COPY pyproject.toml uv.lock projects/lib/* /app
RUN uv lock --no-upgrade && \
  uv sync --locked
