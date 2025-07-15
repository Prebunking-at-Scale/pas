FROM python:3.13-alpine
COPY --from=ghcr.io/astral-sh/uv:alpine /usr/local/bin/uv /bin/uv


# alpine equivalent of build-essentials
RUN apk add --no-cache build-base python3-dev musl-dev linux-headers


COPY <<EOT /app/pyproject.toml
[tool.uv.workspace]
members = ["*"]
EOT
COPY uv.lock /app/uv.lock
COPY projects/lib/pas_log /app/pas_log

# RUN cd /app/pas_log && uv lock --no-upgrade &&  uv sync --all-packages --locked

WORKDIR /app
RUN uv lock --no-upgrade &&  uv sync --all-packages --locked
