# PriceTrack

Lightweight self-hosted price tracker for online stores + newest [pepper.pl](https://www.pepper.pl) promotions.

Paste a product link → the first price is fetched immediately → the scheduler re-checks it on the interval you pick → product cards show the current price, a trend badge and a sparkline, and the detail view shows the full price-history chart with a moving average. A second tab lists fresh deals from the pepper.pl RSS feed.

## Features

- **Add by URL** — product title, image, price and currency are detected automatically.
- **Grid or list view** for tracked products (remembered per browser), and **delete from the detail view**.
- **Tiered extraction** — schema.org **JSON-LD** first (works on most PL shops), then **OpenGraph**, then small per-domain CSS **adapters**, then a **Playwright headless-browser fallback** for JS-rendered / bot-protected pages, plus **manual price entry** as a last resort.
- **Per-product intervals** — 1h / 6h / 12h / 24h / 7d, with jitter, per-domain politeness delays and exponential backoff on failures.
- **Trends** — Δ1d / Δ7d / Δ30d, moving average, all-time-low detection, sparklines.
- **Deals tab** — server-side pepper.pl RSS ingestion, cached, searchable, with merchant/price/category and a **grid ↔ list** toggle (remembered in the browser).
- **Image proxy** — product and deal pictures are fetched and cached by the backend (hotlink protection, no third-party requests from your browser, SSRF-guarded).
- **Honest failures** — if a price cannot be read the product is marked **not supported** (or **failed** when the store blocks the request), the reason is stored, and the UI shows step-by-step ways to fix it.
- **Discord notifications** — webhook message whenever a tracked price drops (optional % threshold, all-time-low callout), configured **in the UI** under ⚙ Settings.
- **Single container** — FastAPI serves both the API and the built SPA; SQLite locally, PostgreSQL in production.
- **Optional single-user password** — cookie session; no accounts.

## Quick start (local)

```bash
make install
make build
make run
```

Development with hot reload:

```bash
make dev-api          # uvicorn --reload on :8000
make dev-web          # vite on :5173 (proxies /api to :8000)
```

Tests: `make test` (pytest, no network required).

## Configuration

Copy `.env.example` to `.env`. The most useful settings:

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/app.db` | use `postgresql+asyncpg://…` in production |
| `ADMIN_PASSWORD` | *(empty)* | set to enable the login overlay; empty = no auth |
| `DEFAULT_INTERVAL` | `24h` | default interval for new products |
| `SCRAPE_POLL_SECONDS` | `30` | scheduler tick |
| `SCRAPE_MIN_GAP_PER_DOMAIN` | `15` | seconds between requests to the same host |
| `RSS_URL` | `https://www.pepper.pl/rss/wszystkie` | pepper.pl feed |
| `RSS_POLL_SECONDS` | `900` | feed refresh cadence |
| `PLAYWRIGHT_ENABLED` | `true` | headless-browser fallback (enabled by default, see below) |
| `PLAYWRIGHT_TIMEOUT_MS` | `25000` | navigation timeout for the browser fallback |
| `IMAGE_PROXY_ENABLED` | `true` | proxy and cache remote images |
| `IMAGE_CACHE_DIR` | `./data/image_cache` | on-disk image cache |
| `IMAGE_CACHE_TTL_DAYS` | `7` | how long cached images stay fresh |
| `DISCORD_WEBHOOK_URL` | *(empty)* | Discord webhook; empty disables notifications |
| `DISCORD_MIN_DROP_PCT` | `0` | only notify when the drop is at least this % |
| `DISCORD_HIGHLIGHT_ALL_TIME_LOW` | `true` | add an all-time-low callout to the embed |

The Discord and browser-fallback values can also be changed in the UI; those saved values win over
the environment.

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/products` | `{url, interval}` → scrape now; `201` new, `200` already tracked |
| `GET` | `/api/products` | cards with sparkline + deltas |
| `GET` | `/api/products/{id}?range=7d\|30d\|90d\|all` | detail: points, moving average, stats |
| `PATCH` | `/api/products/{id}` | change `interval`, pause/resume |
| `POST` | `/api/products/{id}/scrape` | force re-scrape |
| `POST` | `/api/products/{id}/price` | manual price point |
| `DELETE` | `/api/products/{id}` | remove product + history |
| `GET` | `/api/stores` | stores known to work / known to block |
| `GET` | `/api/settings` | editable settings (Discord, browser fallback status) |
| `PUT` | `/api/settings` | save Discord webhook / threshold / browser toggle |
| `GET` | `/api/notifications` | Discord config + browser-fallback availability |
| `POST` | `/api/notifications/test` | send a test message to the Discord webhook |
| `GET` | `/api/deals` | cached pepper.pl items |
| `GET` | `/api/image?url=…` | proxied/cached remote image |
| `POST` | `/api/deals/refresh` | force RSS refetch |
| `GET` | `/api/health` | DB, scheduler and RSS worker status |

Interactive docs: `/docs`.

## Supported stores

Verified against a real product page (the pipeline is exercised end-to-end):

| Store | Domain | Extraction | Notes |
|---|---|---|---|
| x-kom | `x-kom.pl` | JSON-LD | schema.org product data, clean images |
| IKEA | `ikea.com` | JSON-LD | Polish storefront (`/pl/pl/...`) |
| Komputronik | `komputronik.pl` | JSON-LD + OpenGraph | |
| Neonet | `neonet.pl` | JSON-LD + OpenGraph | |
| Media Expert | `mediaexpert.pl` | browser fallback | plain HTTP is blocked (403); Chromium reads it |
| Rossmann | `rossmann.pl` | JSON-LD + OpenGraph | drugstore / beauty pages |
| Sportano | `sportano.pl` | JSON-LD + OpenGraph | sports equipment |
| Sferis | `sferis.pl` | JSON-LD + OpenGraph | electronics |

**Other shops usually work too.** Most e-commerce pages ship schema.org JSON-LD or OpenGraph price
tags, which the first two tiers read without any per-store configuration — that is why store-specific
adapters are rarely needed. The table lists shops verified against a real product page (extraction was
exercised, not just guessed); try your own shop and check the status pill.

Known to block automated clients (browser fallback *may* help, manual entry always works):
`allegro.pl`, `amazon.pl`, `euro.com.pl`.

## When a price cannot be read

PriceTrack distinguishes two outcomes instead of showing a misleading success:

| Status | Meaning | What the app does |
|---|---|---|
| `active` | price read successfully | keeps scraping on the chosen interval |
| `unsupported` | page loaded, but no price found | retries later, shows guidance in the UI |
| `failed` | store blocked the request / unreachable | retries with backoff, shows guidance |
| `paused` | switched off by you | no scraping |

The reason is stored on the product (`last_error`) and shown in the product detail. The fix path:

1. Open the product link in your browser — confirm the price is really on the page.
2. If the price only appears after JavaScript runs, turn on the **headless browser fallback** in
   ⚙ Settings (on by default) and press **Refresh now**.
3. If it still fails, add a small adapter: copy `app/scraping/adapters/_example.json`, set the domain
   and CSS selectors for price/title/image, restart the server, refresh. See
   [Adding a store adapter](#adding-a-store-adapter).
4. Meanwhile, keep the history going with **Enter price manually** in the product detail.

## Let an LLM write the adapter for you

Adding a shop does not have to be manual. When a product is **not supported**, the guidance panel has
a **“Let an LLM write the adapter for me”** button that runs a two-step wizard, fully in the GUI:

1. **Copy the prompt.** PriceTrack picks the price-looking elements out of the page (tag path, text
   and markup), cleans the HTML (scripts/styles removed, truncated) and wraps it in a prompt that
   specifies the exact adapter schema. Paste it into ChatGPT, Claude, Gemini, a local model — your
   choice.
2. **Paste the JSON back.** The answer is parsed (code fences are tolerated), the domain and CSS
   selectors are validated, and the adapter is **tested against the live page** before saving. If it
   finds a price, it is installed, the product is re-scraped immediately and turns `active`.


Installed adapters are stored as JSON in `./data/adapters/<domain>.json` (writable, survives restarts)
and are merged with the built-ins; user adapters win, exact-domain matches beat suffix matches.
The installed JSON stays visible in the product detail (“Custom adapter ▸”), where you can inspect
the selectors or remove the adapter.


Endpoints: `POST /api/products/{id}/adapter-prompt`, `POST /api/adapters`,
`GET /api/adapters`, `GET /api/adapters/{domain}`, `DELETE /api/adapters/{domain}`.

Nothing is sent anywhere by PriceTrack itself — you decide which assistant sees the page HTML.

## Headless-browser fallback (Playwright)

Some shops render prices with JavaScript or block plain HTTP clients. When the normal
fetch + JSON-LD/OpenGraph/adapter tiers find no price (or the request is blocked), PriceTrack
renders the page in headless Chromium and re-runs the same extraction. The extractor name in
`scrape_log` then contains `+browser`.

**Playwright is enabled by default.** `make install` downloads Chromium into
`./.playwright-browsers` (auto-detected by the server), and the default Docker image bundles it.

Prefer a lean setup? Skip the browser:

```bash
make install-slim
docker build --target runtime-slim .
```

or install it manually:

```bash
pip install '.[browser]'
playwright install chromium
```

Availability is shown in ⚙ Settings and at `GET /api/settings`. When Chromium is missing the
fallback is skipped gracefully — nothing else changes.

Local runs: set `PLAYWRIGHT_BROWSERS_PATH` if browsers are not in the default cache directory.
Docker: build the browser-enabled image target — it bundles Chromium and its system libraries
(+~1 GB), the default image stays small:

```bash
docker build --target runtime-browser -t pricetrack:browser .
```

`GET /api/notifications` reports whether the fallback is enabled and actually available.
If Playwright or Chromium is missing, scraping simply falls back to the previous behaviour —
nothing crashes.

## Discord notifications

Create a webhook in your Discord channel (Channel settings → Integrations → Webhooks), then set:

```bash
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
DISCORD_MIN_DROP_PCT=3
```

Every successful scrape compares the new price with the previous one and posts an embed on a
drop: old → new price, percentage, store, interval, product image, and a 🏆 all-time-low callout
when applicable. Notifications are best-effort and never fail a scrape.

Test the configuration:

```bash
curl -X POST https://your-app/api/notifications/test
```

## In-app settings

The ⚙ Settings button (top right) lets you change these at runtime — no restart, no env editing:

- **Discord webhook URL** — paste and save; the value is stored in the database (env var is only the
  initial default). "Send test message" saves the current value and posts a test embed.
- **Minimum drop (%)** — ignore small price movements.
- **Mark all-time lows** — toggle the 🏆 callout in notifications.
- **Use the browser fallback** — on/off, with live status: *Chromium is ready* or the reason it is
  not available.

Values from the UI override the matching environment variables; the API is `GET /api/settings` and
`PUT /api/settings` (protected by the same password as the rest of `/api`).

## Adding a store adapter

Only needed when a shop exposes neither JSON-LD nor OpenGraph price. Drop a JSON file in
`app/scraping/adapters/`:

```json
{
  "domain": "shop.example",
  "currency": "PLN",
  "selectors": { "price": ".product-price", "title": "h1", "image": "img.main" }
}
```

Check which tier succeeded in `scrape_log.extractor` (and the app logs).

## Deployment (Azure)

Infrastructure is defined in [`infra/main.bicep`](infra/main.bicep): Container Registry (Basic),
Container Apps environment, a single-replica Container App (the scheduler must not run twice),
PostgreSQL Flexible Server (B1ms), Log Analytics.

```bash
az group create -n rg-pricetrack -l polandcentral
az deployment group create -g rg-pricetrack -f infra/main.bicep \
  -p adminPassword='<ui-password>' secretKey='<random>'
```

Then push the first image and let CI take over — `.github/workflows/deploy.yml` builds, pushes and
updates the app on every push to `main` (OIDC federation; repo secrets `AZURE_CLIENT_ID`,
`AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`).

The deploy workflow builds the default image, which includes Chromium, so the Playwright fallback
works in Azure out of the box. If you want a smaller footprint, build `--target runtime-slim` and
set `PLAYWRIGHT_ENABLED=false` — a missing browser is reported by `/api/settings` and the fallback
is skipped gracefully.

Approximate cost: one 0.5 vCPU container + B1ms Postgres + Basic ACR ≈ €25/month, less on free tiers.

### Local Docker

```bash
docker compose up --build
```