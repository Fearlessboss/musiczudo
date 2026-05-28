# ============================================================
#  THE ULTIMATE WELCOME / COMMUNITY BOT — Dockerfile
#  - Slim Python base
#  - Non-root user for security
#  - Build deps separated from runtime (multi-stage)
#  - Healthcheck + tini for proper signal handling
#  - Timezone, locale, certs, build tools — sab included
# ============================================================

# ---------- Stage 1: Builder ----------
FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

# Build dependencies (compilers, headers, ssl, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        make \
        libffi-dev \
        libssl-dev \
        libxml2-dev \
        libxslt1-dev \
        zlib1g-dev \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Install python deps into an isolated prefix
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel \
    && pip install --prefix=/install --no-warn-script-location -r requirements.txt


# ---------- Stage 2: Runtime ----------
FROM python:3.11-slim-bookworm AS runtime

LABEL maintainer="WelcomeBot" \
      description="Ultimate Welcome / Community Telegram Bot" \
      version="1.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    TZ=Asia/Kolkata \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PATH="/usr/local/bin:${PATH}"

# Runtime-only deps: tini (signal handling), tzdata, certs, curl (for healthcheck), libssl
RUN apt-get update && apt-get install -y --no-install-recommends \
        tini \
        tzdata \
        ca-certificates \
        curl \
        libssl3 \
        libffi8 \
    && ln -fs /usr/share/zoneinfo/${TZ} /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN groupadd --system --gid 1000 botuser \
    && useradd  --system --uid 1000 --gid botuser --create-home --shell /bin/bash botuser

# Copy installed python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy app code (preserve permissions for botuser)
COPY --chown=botuser:botuser . /app

# Make sure logs dir exists & is writable
RUN mkdir -p /app/logs && chown -R botuser:botuser /app

USER botuser

# Healthcheck: simple python import + Mongo ping (lightweight)
HEALTHCHECK --interval=60s --timeout=15s --start-period=30s --retries=3 \
  CMD python -c "import os, sys; \
from pymongo import MongoClient; \
MongoClient(os.environ.get('MONGO_URL','mongodb://localhost:27017'), serverSelectionTimeoutMS=5000).admin.command('ping')" || exit 1

# tini = PID 1 -> clean Ctrl+C / SIGTERM handling
ENTRYPOINT ["/usr/bin/tini", "--"]

CMD ["python", "-u", "bot.py"]
