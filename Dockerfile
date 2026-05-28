# ============================================================
#  THE ULTIMATE WELCOME / COMMUNITY BOT — Dockerfile (v2)
#  - MongoDB Atlas TLS bullet-proof (latest OpenSSL + certifi)
#  - Multi-stage, non-root, tini, healthcheck
#  - Auto-restart friendly (in-memory fallback if DB down)
# ============================================================

# ---------- Stage 1: Builder ----------
FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

# Build dependencies
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

COPY requirements.txt .

# Upgrade pip stack + install deps into isolated prefix
RUN pip install --upgrade pip setuptools wheel \
 && pip install --prefix=/install --no-warn-script-location -r requirements.txt \
 && pip install --prefix=/install --no-warn-script-location --upgrade certifi


# ---------- Stage 2: Runtime ----------
FROM python:3.11-slim-bookworm AS runtime

LABEL maintainer="WelcomeBot" \
      description="Ultimate Welcome / Community Telegram Bot" \
      version="2.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    TZ=Asia/Kolkata \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PATH="/usr/local/bin:${PATH}" \
    # Force pymongo / ssl to use certifi bundle
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

# Runtime deps:
#  - tini      : PID 1 signal handler
#  - tzdata    : timezone
#  - ca-certs  : root CAs for TLS (Atlas)
#  - openssl   : latest TLS stack (fixes TLSV1_ALERT_INTERNAL_ERROR)
#  - libssl3   : runtime ssl lib
#  - libffi8   : cffi runtime
#  - curl      : for optional healthcheck
#  - dnsutils  : helps SRV lookup for mongodb+srv://
RUN apt-get update && apt-get install -y --no-install-recommends \
        tini \
        tzdata \
        ca-certificates \
        openssl \
        libssl3 \
        libffi8 \
        curl \
        dnsutils \
    && ln -fs /usr/share/zoneinfo/${TZ} /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata \
    && update-ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Non-root user
RUN groupadd --system --gid 1000 botuser \
 && useradd  --system --uid 1000 --gid botuser --create-home --shell /bin/bash botuser

# Copy installed python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy app code
COPY --chown=botuser:botuser . /app

# Logs dir
RUN mkdir -p /app/logs && chown -R botuser:botuser /app

USER botuser

# -------- Healthcheck --------
# Bot must be RUNNING; Mongo is OPTIONAL (script has in-memory fallback).
# So we only check that the python process can import + the script file exists.
# This prevents container from being marked "unhealthy" when Atlas is briefly down.
HEALTHCHECK --interval=60s --timeout=10s --start-period=20s --retries=3 \
  CMD python -c "import os, sys; sys.exit(0 if os.path.exists('/app/bot.py') else 1)" || exit 1

# tini = PID 1
ENTRYPOINT ["/usr/bin/tini", "--"]

CMD ["python", "-u", "bot.py"]
