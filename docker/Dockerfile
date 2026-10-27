# syntax=docker/dockerfile:1.4
FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /build

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /app/.venv && \
    uv pip install --python /app/.venv/bin/python --no-cache .

FROM python:3.12-slim-bookworm AS final

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    GH_DATA_DIR="/data"

RUN groupadd -g 10001 gh && \
    useradd -u 10001 -g gh -m -s /bin/bash gh && \
    mkdir -p /data /app/config && \
    chown -R gh:gh /data /app

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY config/ /app/config/
COPY migrations/ /app/migrations/
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

USER gh
VOLUME ["/data"]
EXPOSE 4000 8100

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gateway"]
