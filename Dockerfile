# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# GamesTracker — Multi-stage Dockerfile
# Stage 1 (deps): install Python packages into a prefix
# Stage 2 (runtime): copy prefix + source onto a slim base
# ---------------------------------------------------------------------------

# ---- Stage 1: build dependency layer -------------------------------------
FROM python:3.10-slim AS deps

# System packages required to build some wheels (e.g. lxml, pandas C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /install

COPY requirements.txt .

# Install all Python dependencies into /install/site-packages
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ---- Stage 2: runtime image ----------------------------------------------
FROM python:3.10-slim AS runtime

# OCI standard labels
LABEL org.opencontainers.image.title="GamesTracker" \
      org.opencontainers.image.description="Indie game tracking background service" \
      org.opencontainers.image.source="https://github.com/gamestracker/gamestracker" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.base.name="python:3.10-slim"

# Runtime system dependencies for PyQt6 / OpenGL (headless collector still
# needs libGL for optional import-time checks) and SQLite
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libxcb-icccm4 \
        libxcb-image0 \
        libxcb-keysyms1 \
        libxcb-render-util0 \
        libxcb-xinerama0 \
        libxkbcommon-x11-0 \
        libdbus-1-3 \
        sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from the build stage
COPY --from=deps /install /usr/local

# Create a non-root user for the service
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Copy source — requirements layer is already cached above, so only source
# changes bust this layer
COPY --chown=appuser:appuser . .

# Ensure data/ exists and is writable by appuser
RUN mkdir -p /app/data && chown appuser:appuser /app/data

USER appuser

# HEALTHCHECK: verify the core package can be imported (fast, no side effects)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import core.config; core.config.get_settings()" || exit 1

# Default entrypoint: background collector service
CMD ["python", "run_collector.py"]
