# Price Tracker — Implementation Plan

> **Status: implemented (MVP M0–M5).** Backend, SPA, tests, Docker, CI and Bicep infra are in the
> repo and were verified locally end-to-end (live scraping of x-kom.pl and IKEA PL, live pepper.pl
> RSS, Postgres + auth via docker compose). The Azure resources themselves were not created — no
> subscription credentials in this environment; `infra/main.bicep` compiles cleanly with Bicep
> 0.33.93. See `README.md` for usage.
>
> Deviations from the plan below: schema is created with SQLAlchemy `create_all` instead of Alembic
> (single-user MVP, no migration history yet); the SPA uses hash-based tabs instead of a router.
>
> **Post-MVP additions:** the app is fully in English; a **Playwright headless-browser fallback**
> covers JS-rendered and bot-protected shops (plain 403s and pages without a price in the raw HTML
> are retried through Chromium, optional `runtime-browser` Docker target); **Discord webhook
> notifications** fire on price drops with an optional minimum-drop threshold and an all-time-low
> callout — configurable **in the UI** (⚙ Settings), with DB values overriding environment defaults.
> The app also ships a **server-side image proxy** (disk-cached, SSRF-guarded) for product and deal
> pictures, a **grid/list toggle** for the deals feed, and Playwright is now **on by default** in both
> `make install` and the default Docker image (lean variants remain available). Unsupported stores can
> be fixed from the UI with an **LLM adapter wizard** (generated prompt → validated JSON → live test →
> installed adapter, inspectable/removable later in the product detail). The products list has a
> grid/list toggle, products can be deleted from the detail view, and the stat boxes fit long prices.
> See README.

A lightweight self-hosted app on Azure: paste a product link → it's saved → prices are scraped on a chosen interval → browse products with pictures, price history graphs and trend indicators. A second tab shows the newest pepper.pl promotions (RSS).

---

## 1. Goals & non-goals

**Goals (MVP)**
- Single lightweight deployment (ideally 1 container + 1 managed DB), cheap (target ≈ €10–25/month).
- Add a product by pasting a URL; product auto-detected (title, image, price, currency).
- Per-product scrape interval (1h / 6h / 12h / 24h / 7d) + global default.
- Product list (cards with image, current price, trend badge) and detail view with full price-history chart.
- "Deals" tab with pepper.pl RSS promotions (title, image, merchant, price, category).
- Single-user — no accounts, no multi-tenancy.

**Non-goals (v1)**
- No user registration, no reviews, no cross-store price comparison engine, no price-drop notifications (listed as v2 ideas).

---

## 2. Architecture at a glance

```
Browser (SPA: React + Vite + Chart.js)
        │  HTTPS
        ▼
┌─────────────────────────────────────────────┐
│  Azure Container App (1 container, always-on)│
│  FastAPI                                      │
│   ├─ /api/*        REST API                   │
│   ├─ /            serves built SPA            │
│   ├─ scheduler     APScheduler (per-product  │
│   │                intervals, domain-limited) │
│   ├─ scraper       httpx + JSON-LD/OG parse   │
│   │                (+ per-domain adapters)    │
│   └─ rss worker    pepper.pl fetch, 15 min    │
└─────────────────────────────────────────────┘
        │ asyncpg / SQLAlchemy
        ▼
Azure Database for PostgreSQL (Flexible, Burstable B1ms/B2ms)
```

Single image = one place to deploy, easy local dev (SQLite fallback). One always-on container so the in-process scheduler works; the app is tiny (0.25–0.5 vCPU tier is enough).

**Cheaper alternative (v1.1 if cost matters):** split the scheduler + scraper into an Azure Functions timer trigger (consumption = ~free) and let the web container scale to zero. Adds moving parts — only do it if the bill says so.

## 3. Tech stack (with rationale)

| Layer | Choice | Why |
|---|---|---|
| Backend | **Python 3.12 + FastAPI** | best scraping ecosystem (httpx, selectolax/BeautifulSoup, JSON-LD), async, tiny footprint |
| Scheduler | **APScheduler** (in-process) | per-product cron/interval jobs, jitter, one container keeps it simple |
| DB | **SQLite locally / PostgreSQL on Azure** via SQLAlchemy + Alembic | zero-config dev; managed Postgres is cheap and boring-reliable |
| Frontend | **React + Vite + TypeScript**, built to static files served by FastAPI | one container, CDN-cacheable assets |
| Charts | **Chart.js** (line chart) + inline-SVG sparklines | small, well-documented, no heavyweight charting lib |
| Scraping | **httpx** + JSON-LD (schema.org) first; OG meta fallback; per-domain CSS-selector adapters; **Playwright headless** as an optional, later add-on | JSON-LD covers most shops (x-kom, Media Expert, Morele, Empik…) and survives redesigns better than selectors |
| RSS | **feedparser**, fetched server-side | pepper.pl feeds verified working (see §7) |
| Deploy | Docker → **ACR** → **Azure Container Apps**; **Bicep** for infra; **GitHub Actions** CI/CD | reproducible, one-command deploy |

## 4. Data model

```sql
products (
  id            uuid PK,
  url           text NOT NULL,          -- normalized for dedup
  url_canonical text UNIQUE,
  title         text,
  image_url     text,                    -- original URL; proxied later (v2)
  currency      char(3),
  domain        text,                    -- for rate-limit buckets
  last_price    numeric, last_price_at timestamptz,
  interval      text DEFAULT '24h',      -- 1h|6h|12h|24h|7d
  next_check_at timestamptz,
  status        text DEFAULT 'active',   -- active|failed|unsupported
  created_at    timestamptz
)

price_points (
  product_id uuid FK,
  price      numeric NOT NULL,
  in_stock   boolean DEFAULT true,
  scraped_at timestamptz NOT NULL,
  PRIMARY KEY (product_id, scraped_at)
)
-- index (product_id, scraped_at desc); ~10–50 rows/product/day → trivial scale

rss_items (
  id uuid PK, external_id text UNIQUE,   -- guid/permalink
  title text, link text, image_url text,
  merchant text, price_raw text, category text,
  published_at timestamptz, fetched_at timestamptz
)
-- keep last ~300 items, prune old

scrape_log (product_id, at, ok bool, http_status, error text)  -- debug + circuit breaker
```

## 5. Scraping strategy (tiered, in this order)

1. **Normalize URL** — strip tracking params (`utm_*`, `gclid`, fragments); dedupe.
2. **JSON-LD** (`<script type="application/ld+json">`, `@type: Product` with `offers`): name, image, price, priceCurrency, availability. This is present on the majority of EU e-commerce sites — the primary extraction path.
3. **OpenGraph / Twitter meta** (`og:title`, `og:image`, `product:price:amount`) — partial fallback.
4. **Per-domain adapter** — small JSON/YAML config of CSS selectors per shop (kept in `adapters/*.json`, e.g. x-kom, morele.net, mediaexpert.pl, empik.com). Auto-generate a stub: after first JSON-LD failure, a CLI helper (`app/helpers/make_adapter.py`) asks the user to point at the price element → saves selector.
5. **Playwright headless fallback** (optional, phase 5) — only for JS-rendered/anti-bot pages; increases the image ~500 MB, so gate it behind a separate optional image tag or a second container.
6. On total failure → product marked `unsupported`, UI offers **manual price entry** as last resort (still records history).

**Politeness / robustness:** realistic browser UA + Accept-Language `pl-PL`; per-domain token bucket (≥3 min between hits to same host — naturally satisfied by intervals); exponential backoff on 403/429/5xx (3 strikes → `status=failed`, stop hammering); 15s timeouts; `robots.txt` respected by default with a per-product override flag. Log everything to `scrape_log`.

**Trend calculations** (computed in API, not stored): change vs 1d/7d/30d (%), 7-day moving average series (second chart line), min/max/avg over selected window, "all-time low" / "drop since last check" badges.

## 6. API design

```
POST /api/products          {url, interval} → fetch once immediately, return product
GET  /api/products          → cards: title, image, last_price, Δ7d%, sparkline points, status
GET  /api/products/{id}     → detail + ?range=7d|30d|90d|all price series + trend stats
PATCH/api/products/{id}     → change interval, title, archive
DELETE /api/products/{id}
GET  /api/deals?category=   → cached RSS items (newest first)
GET  /api/deals/refresh     → force RSS refetch
GET  /api/health            → scheduler + DB + last-scrape stats
```

## 7. pepper.pl Deals tab

Verified feeds (Nov 2025): `https://www.pepper.pl/rss` 301-redirects to **`/rss/wszystkie`** (works, RSS 2.0). Useful variants to try at build time: `/rss/hot`. Item extensions available in the feed: `pepper:merchant` (with `price` attr), `media:content` (image), `category`.

Plan:
- Background worker refetches the feed **every 15 min** (server-side; browser never hits pepper.pl directly → no CORS, no hammering).
- Parse and store: title, link, image, merchant + price, category, publish date; **strip the description HTML** (keep first plain-text sentence max ~200 chars) and sanitize.
- UI: card grid like pepper — image, title, merchant badge, price, category chip, time-ago; click opens pepper.pl in a new tab. Category filter + search box.
- Show attribution "via pepper.pl" + link back (the feed is explicitly provided for consumption; we show snippet + link, not full reposts).

## 8. UI (two tabs, mobile-friendly, ~3 screens)

- **Products tab** — top bar: URL paste box + interval selector; card grid: image, title, current price, Δ badge (▼ −12.5% green / ▲ red / ● stable), mini sparkline (inline SVG), last-checked time. Empty state = call to action.
- **Product detail** (modal or route) — big image, title, link-out, interval picker, Chart.js line chart of history with 7-day MA overlay, range switch (7d/30d/90d/all), stats row: min / max / avg / current vs 90d-low.
- **Deals tab** — RSS cards, "refreshed 4 min ago", category filter.
- Dark/light, Polish labels (it's a PL-store tool), <100 KB JS budget for the SPA shell.

## 9. Deployment on Azure

**Resources (one resource group `rg-price-tracker`, region `westeurope`/`polandcentral`):**
1. **Container Apps environment** (Consumption) — 1 app, minReplicas=1 (scheduler must live), 0.5 vCPU / 1 Gi tier, image from ACR.
2. **Azure Database for PostgreSQL Flexible Server** — Burstable `B1ms`/`B2ms` (B2ms free under Azure free account for 12 months), 128 GB storage, non-public network (VNet integration or firewall to the Container Apps subnet).
3. **ACR** Basic tier.
4. **Log Analytics** + Container Apps diagnostics (free 5 GB ingestion).

**CI/CD (GitHub Actions):** `push → lint+pytest → docker build (multi-stage, slim) → ACR push → az containerapp update`. Infra provisioned once with a `infra/main.bicep` + one bootstrap script; secrets (DSN) injected as Container App secrets.

**Auth:** MVP = single global password (session cookie, `ADMIN_PASSWORD` env) — trivial, works behind any URL. Upgrade path: Entra ID authentication (built into Container Apps ingress) if you want SSO without a password field.

**Local dev:** `docker compose up` (app + Postgres), or plain `uvicorn` with SQLite; the whole app in one `make dev`.

**Rough cost:** always-on small container ≈ €8–15/mo + Postgres B1ms ≈ €10–15/mo + ACR/logs ≈ €3–5/mo → **≈ €25/mo worst case**, near-zero with free-account tiers. Option B (Functions for scraper, web scale-to-zero) cuts it roughly in half if needed.

## 10. Repository layout

```
price-tracker/
├─ app/
│  ├─ main.py            # FastAPI app, static mount
│  ├─ api/               # routes: products, deals, health
│  ├─ db/                # SQLAlchemy models, Alembic migrations
│  ├─ scraping/          # fetcher, extractors (jsonld, og, adapters/*.json), politeness
│  ├─ scheduler/         # APScheduler wiring, job = scrape due product
│  ├─ rss/               # feedparser worker, sanitizer
│  ├─ trends.py          # stats, moving avg, sparkline buckets
│  └─ config.py          # pydantic-settings (DSN, intervals, password)
├─ web/                  # React+Vite SPA → built into app/static
├─ infra/main.bicep
├─ .github/workflows/deploy.yml
├─ Dockerfile  docker-compose.yml  Makefile  pyproject.toml
└─ tests/
```

## 11. Milestones

| # | Deliverable | What "done" means | Effort |
|---|---|---|---|
| M0 | Skeleton | FastAPI + SPA scaffold, compose, SQLite, `/health`, CI runs | ~0.5 day |
| M1 | Paste & scrape | Add URL → immediate scrape → card with image/price; JSON-LD + OG extractors; detail view with Chart.js history | 1.5–2 days |
| M2 | Scheduler & trends | Per-product intervals, jitter, backoff/`status`, Δ badges + 7d MA + sparkline | 1–1.5 days |
| M3 | Deals tab | RSS worker + cache + deals UI with filters | 0.5–1 day |
| M4 | Azure deploy | Bicep + GH Actions + password auth, staging URL, data survives restart | ~1 day |
| M5 | Hardening | per-domain adapters, error surfacing in UI, empty/failure states, e2e test for 3 real stores | 1–2 days |
| **MVP total** | | | **≈ 5–7 working days** |

**v2 ideas (parked):** notifications via other channels (ntfy/Telegram/e-mail) · manual-entry mode · CSV export · multi-user.

## 12. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Anti-bot (Cloudflare etc.) on some stores | JSON-LD/normal fetch first; backoff + `failed` status; Playwright as optional v2; manual entry as escape hatch |
| Store redesign breaks selectors | JSON-LD primary (standards-based, stable); adapters are small JSON, easy to patch via PR |
| Hotlinked product images disappear / block referrers | MVP: hotlink with `<img referrerpolicy>`; v2: proxy+cache images |
| Container restart loses schedule state | `next_check_at` persisted in DB — scheduler recomputes on boot |
| pepper.pl feed format changes | feedparser is forgiving; store raw first N items; deals tab is additive, app core unaffected |
| Legal/ToS of scraping | personal, low-frequency, cached reads; honor robots.txt; RSS used as designed with attribution & links |

---

### Decision points for you (defaults in parentheses)
1. Stack: **Python/FastAPI (recommended)** vs Node/Fastify+cheerio — pick one, plan assumes Python.
2. Azure spend: always-on Container App **(recommended, simplest)** vs Functions+scale-to-zero.
3. Auth: single password **(recommended for MVP)** vs Entra ID SSO from day one.
4. Which specific stores matter most to you? (pre-seeds the v1 adapter list — x-kom, Morele, Media Expert assumed.)
