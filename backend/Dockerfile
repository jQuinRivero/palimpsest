# Reading two manuscripts side by side should not require a Python toolchain,
# a Node toolchain, and two terminals. This image is the whole API.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Bytecode is compiled at build time so the first comparison a reader runs is
# not also the slowest. Copy mode avoids hardlink warnings across the layer.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CONFIG=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies resolve from the lockfile in their own layer, so editing the
# application does not reinstall them. --frozen fails rather than silently
# re-resolving, which is what makes the image match the committed lock.
#
# The project itself is deliberately not installed as a distribution: that
# would drag in a build backend that the lockfile does not pin, so the image
# would resolve something at build time that no lockfile records. Running from
# the source tree keeps the image reproducible from uv.lock alone.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app

# Comparisons are a cache with a deadline, but a cache that empties on every
# restart makes shareable links useless. /data is a volume in compose.yaml.
ENV PALIMPSEST_DATABASE_PATH=/data/palimpsest.db
RUN install -d -o 65532 -g 65532 /data

USER 65532:65532
EXPOSE 8000

# Uploaded manuscripts may be unpublished, so nothing here reaches outside the
# container. Health is the same endpoint CI waits on.
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
