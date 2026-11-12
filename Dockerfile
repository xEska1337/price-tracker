# syntax=docker/dockerfile:1

# ---------- stage 1: build the SPA ----------
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---------- stage 2: lean runtime (no Chromium) ----------
# Used by CI and available as: docker build --target runtime-slim .
FROM python:3.12-slim AS runtime-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# install dependencies first for layer caching
COPY pyproject.toml ./
COPY app/__init__.py app/
RUN pip install --no-cache-dir ".[postgres]" && rm -rf /tmp/*

COPY app/ ./app/
COPY --from=web /web/dist ./web/dist

# non-root user; /app/data holds the SQLite fallback volume
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

ENV DATABASE_URL=sqlite+aiosqlite:////app/data/app.db \
    PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]

# ---------- stage 3: default image = runtime + headless Chromium ----------
# Playwright is enabled by default, so the browser ships in the default image.
# Adds ~1 GB (Chromium + system libs); use --target runtime-slim for the lean variant.
FROM runtime-slim AS runtime-browser
USER root
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=0
RUN apt-get update \
    && apt-get install -y --no-install-recommends libatomic1 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir "playwright>=1.47" \
    && python -m playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright \
    && rm -rf /var/lib/apt/lists/* /root/.cache
USER appuser
