# pocketii

> A production-grade personal finance platform — track expenses, manage budgets, monitor investments, and get AI-powered insights into your financial health.

[![Live App](https://img.shields.io/badge/Live%20App-pocketii.fly.dev-blue?style=flat-square)](https://pocketii.fly.dev/landing)
[![Demo](https://img.shields.io/badge/Demo-pocketii.onrender.com-green?style=flat-square)](https://pocketii.onrender.com)


---

## Live Links

| Environment | URL |
|---|---|
| **Production App** | [https://pocketii.fly.dev/landing](https://pocketii.fly.dev/landing) |
| **Interactive Demo** | [https://pocketii.onrender.com](https://pocketii.onrender.com) |

The demo runs in two modes:
- **Watch Mode** — automated guided tour with pre-seeded data and narration
- **Interactive Mode** — sandboxed session to freely explore all features (no real account needed, resets every 15 minutes)

---

## Table of Contents

- [What is pocketii?](#what-is-pocketii)
- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [API Keys & External Services](#api-keys--external-services)
- [Local Development (Docker Compose)](#local-development-docker-compose)
- [Running Services Individually](#running-services-individually)
- [Environment Variables Reference](#environment-variables-reference)
- [Database Migrations](#database-migrations)
- [Deployment](#deployment)
  - [Fly.io (Production)](#flyio-production)
  - [Render (Demo App)](#render-demo-app)
- [Project Structure](#project-structure)
- [Important Considerations](#important-considerations)

---

## What is pocketii?

pocketii is a full-featured personal finance management platform with the addition of an investment portfolio module, shared household finance, and AI-powered insights.

- reach out for project docs if interested

**Core capabilities:**
- Log and categorize expenses and income
- Set and track budgets with real-time alerts
- Monitor investment portfolios with live market data
- Detect spending anomalies and forecast future expenses
- Set savings goals including micro-savings via round-ups
- Link real bank accounts (Plaid, Teller, TrueLayer)
- Share finances with household members
- Export data, view reports, and manage recurring transactions


---

## Features

### Expense & Income Tracking
- Add, edit, and delete expenses with 8 predefined categories (Food, Transportation, Travel, Utilities, Entertainment, Health, Shopping, Other)
- Log income entries separately
- Running balance calculated on every transaction
- Idempotency key support to prevent duplicate entries on retries
- Import expenses via CSV
- Attach receipt images with OCR extraction (Tesseract)
- User-defined tags and auto-categorization rules by merchant/keyword
- Multi-currency support with live exchange rate sync (ECB)

### Budgeting
- Create per-category budgets with configurable time periods
- Visual progress bars and percentage tracking
- Alert thresholds at 50% and 100% of budget
- Budget history and household-scoped budgets
- Background worker evaluates and fires alerts automatically

### Savings Goals
- Define savings goals with target amounts and deadlines
- Track progress over time
- Round-up micro-savings: automatically rounds up transactions and deposits the difference toward a goal

### Recurring Transactions
- Define weekly, monthly, or custom recurring expenses and income
- Background job marks due transactions and sends reminders

### Insights (AI/Statistical)
- **Anomaly Detection** — Z-score and IQR statistical analysis flags unusual spending spikes
- **Spending Forecast** — 3-month moving average with confidence intervals to project future spend
- User feedback on anomalies (thumbs up/down) to tune detection over time

### Investments
- Track stock, ETF, and fund holdings (quantity, cost basis, current value)
- Portfolio snapshot: allocation by sector and asset class
- Historical daily returns and performance metrics
- **AI-Powered Recommendations** — sector allocation analysis, rebalancing suggestions, tax-loss harvesting opportunities explained via Groq LLM + Brave Search research context
- Sentiment scoring per holding
- Financial news aggregation (Benzinga primary, Finnhub and Alpha Vantage supplement)
- Risk profile questionnaire with tailored recommendations
- Alpaca broker integration for live position sync

### Bank Integrations
- **Plaid** (US, sandbox and production)
- **Teller** (US, alternative connector)
- **TrueLayer** (EU bank connector)
- Linked account management and automatic transaction sync

### Household / Shared Finance
- Create a household and invite members by email
- Role-based access: owner vs member
- All expenses, budgets, and goals can be scoped to a household
- Switch active household context per session

### Reports & Export
- Category breakdown and spending trend charts
- CSV export of all transactions
- Saved Views — save custom report configurations and reload them later

### User & Security
- Email/password registration with bcrypt hashing
- Google OAuth and Apple Sign-In
- JWT access tokens (30 min) + rotating refresh tokens (7 days)
- Forgot password / reset password via email
- Email verification (configurable)
- Active session tracking with IP and user agent; revoke any session
- GDPR data retention policies and full account data export (ZIP) on deletion
- Audit log of all authentication events
- HSTS, CSP with nonce injection, rate limiting on all endpoints

### Notifications
- In-app notification inbox
- Budget threshold alerts
- Anomaly nudges (max 5/user/run)
- Low projected balance warnings
- Recurring transaction due reminders
- Optional email digest (SMTP)

### Progressive Web App
- Service worker for offline capability
- Web app manifest for installability on mobile

---

## Architecture

pocketii uses a microservices architecture. In production (Fly.io) all services run in a single container for cost efficiency; in development they run as separate Docker containers.

```
[Browser / PWA]
      │
  [API Gateway :8080]  ← single public entry point
      │  JWT validated once here; rate-limited per user and per IP
  ┌───┼────────┬──────────────────┐
  │   │        │                  │
User  Expense  Budget        Investments
:8000 :3001   :3002          :3003
  │     │
PostgreSQL (4 separate DBs) + Redis (caching & rate limiting)
```

| Service | Port | Responsibility |
|---|---|---|
| `api-gateway` | 8080 | JWT validation, rate limiting, path-based routing |
| `user-microservice` | 8000 | Auth, profiles, households, notifications, frontend |
| `expense-microservice` | 3001 | Expenses, income, receipts, goals, insights, bank integrations |
| `budget-microservice` | 3002 | Budgets, alerts |
| `investments-microservice` | 3003 | Holdings, portfolio, market data, recommendations |

**Background Workers** run alongside each service:
- `user-worker` — email digests, GDPR retention purge, webhook delivery
- `expense-worker` — exchange rate sync, anomaly nudges, balance alerts, recurring processor, round-up savings
- `budget-worker` — budget alert evaluation
- `investment-worker` — Alpaca sync, ETF metadata, returns backfill, sentiment, tax harvesting

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, uvicorn |
| Database | PostgreSQL 16 |
| Cache / Rate Limiting | Redis 7 |
| Frontend | Jinja2 templates, TypeScript (strict) → ESBuild for `auth.js` / `sw.js`, Tailwind CSS, PWA |
| Auth | JWT (HS256), OAuth2 (Google, Apple) |
| OCR | Tesseract |
| AI / LLM | Groq (llama-3.3-70b-versatile) |
| Market Data | Alpaca, Finnhub, Twelve Data, Alpha Vantage |
| News | Benzinga, Finnhub, Alpha Vantage |
| Bank Linking | Plaid, Teller, TrueLayer |
| Containerization | Docker, Docker Compose |
| Production Deploy | Fly.io |
| Demo Deploy | Render |

### Frontend TypeScript

Sources live under `frontend/src/ts/` and compile with ESBuild via `npm run build:js` (see `frontend/scripts/build-js.mjs`). Run `npm run typecheck` and `npm run build:js` from `frontend/` before deploy when TS changes; templates load emitted files under `frontend/static/js/` and `frontend/static/sw.js`. Strict typing is enabled for `auth.ts`; other page modules use `// @ts-nocheck` until types are narrowed incrementally.

### Stitch → template map (mobile parity target)

Use the Stitch `code.html` references as the mobile (`md:hidden` / narrow viewport) hierarchy target; desktop keeps existing `md:` layouts. Primary mapping: `dashboard_v5` → `dashboard.html`, `expenses_list_v4` → expenses list templates, `investments_overview_2` / `investments_v3` → `investments.html`, `portfolio_recommendations_v3` → `recommendations.html`, `integrations_hub_v3` → `settings/integrations.html`, `settings_v3` → `settings.html`, `login_create_account_v2` → `login.html` / `register.html`, `budgets_v3` → `budgets/list.html`, `analytics_overview_v2_2` → `analytics.html`, `financial_insights_v2` → `insights.html`, `financial_reports_v3` → `reports.html`, `net_worth_breakdown_v2` / `net_worth_overview_2` → `net_worth.html`, `goal_detail_v2` / `goals_list_v2` → goal templates, `household_management` → `household.html`, `transactions_v3` → transactions views, `profile_v4` → `profile.html`, `landing_page` → `landing.html`, `link_bank_account` / `link_bank_confirmation` → link-bank flow templates.

### Mobile journey (summary)

Cold open → dashboard summary first; investments/recommendations charts load on tab focus or below the fold. Expenses default to list; analytics from a secondary tab/CTA. Investments overview before full chart/detail. More/settings uses collapsed sections with navigate-in screens for integrations and household. After bank link, confirmation then integrations hub; avoid stacked modals.

---

## Prerequisites

- **Docker** and **Docker Compose** (v2+)
- **Root environment file:** `cp .env.example .env` at the project root. Docker Compose loads `.env` automatically for `${VAR}` substitution. Minimum: **`SECRET_KEY`** (shared by all JWT services), **`INTERNAL_API_KEY`** (shared for internal routes; `.env.example` provides a dev default), **`GATEWAY_PUBLIC_URL=http://localhost:8080`**, **`APP_BASE_URL=http://localhost:8080`**, **`REQUIRE_EMAIL_VERIFICATION=false`** for local dev (register → login without completing email).
- **Frontend assets:** The user service image **copies** `frontend/` at build time. After changing TypeScript/CSS sources run **`./scripts/bootstrap-frontend.sh`**, then **`docker compose build user`** (or rebuild the whole stack).
- **Expo Go:** Mobile now auto-detects the Metro host in dev and resolves gateway as `http://<detected-host>:8080`. For reliability, still set **`EXPO_PUBLIC_GATEWAY_URL`** in `mobile/.env` (copy from `.env.example`) to `http://<your-LAN-IP>:8080` (not `localhost`) so a phone can always reach the gateway.
- **Example gateway (LAN dev):** `http://10.206.27.212:8080` — substitute your host’s IP; use that same base for **`GATEWAY_PUBLIC_URL`**, **`APP_BASE_URL`**, and **`EXPO_PUBLIC_GATEWAY_URL`** when testing mobile or OAuth from another device on the network.
- **OAuth on device:** For Google/Apple OAuth from Expo on a physical phone, set both **`APP_BASE_URL`** and **`GATEWAY_PUBLIC_URL`** in root `.env` to the same reachable host as **`EXPO_PUBLIC_GATEWAY_URL`** (for example `http://10.206.27.212:8080` or `http://192.168.1.10:8080`) so authorize/callback/exchange all stay on one public origin.
- Optional: API keys for third-party services (see below)

---

## API Keys & External Services

Most features work without any third-party keys. The table below describes what each key unlocks and where to get it.

> **Only `SECRET_KEY` is required** to run the app locally. Everything else is optional and degrades gracefully.

### Core (Required)

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | **Yes** | Random 64-char hex string. Used to sign JWTs. All services must share the same value. Generate with: `openssl rand -hex 32` |
| `INTERNAL_API_KEY` | Recommended | Shared secret for internal service-to-service calls (budget→user notifications). Set to any random string. |

### Market Data (Investments module)

The investments service uses a **failover chain** — it tries providers in order and falls back if a key is missing or rate-limited. You need at least one key for live quotes.

| Variable | Provider | Free Tier | Sign Up |
|---|---|---|---|
| `ALPACA_API_KEY` + `ALPACA_API_SECRET` | Alpaca | Free paper trading account | [alpaca.markets](https://alpaca.markets) |
| `FINNHUB_API_KEY` | Finnhub | 60 calls/min | [finnhub.io](https://finnhub.io) |
| `TWELVEDATA_API_KEY` | Twelve Data | 8 req/min, 800/day | [twelvedata.com](https://twelvedata.com) |
| `ALPHAVANTAGE_API_KEY` | Alpha Vantage | 25 req/day | [alphavantage.co](https://www.alphavantage.co/support/#api-key) |

Set provider priority order via:
```
MARKET_DATA_PROVIDER_ORDER=alpaca,finnhub,twelvedata,alphavantage
```

### AI Recommendations Explainer

| Variable | Provider | Free Tier | Sign Up |
|---|---|---|---|
| `GROQ_API_KEY` | Groq | Generous free tier | [console.groq.com](https://console.groq.com) |
| `BRAVE_API_KEY` | Brave Search API | Free monthly credits | [brave.com/search/api](https://brave.com/search/api/) |

Set explainer order via:
```
AI_EXPLAINER_PROVIDER_ORDER=groq,brave,generic
```
`generic` requires no API key and always works as a final fallback.

### Financial News

| Variable | Provider | Notes |
|---|---|---|
| `BENZINGA_API_KEY` | Benzinga | Paid; primary news source |
| `FINNHUB_API_KEY` | Finnhub (shared with market data) | Supplement |
| `ALPHAVANTAGE_API_KEY` | Alpha Vantage (shared) | Supplement |

### Bank Linking

| Variable | Provider | Notes |
|---|---|---|
| `PLAID_CLIENT_ID` + `PLAID_SECRET` | Plaid | Set `PLAID_ENV=sandbox` for testing |
| `TELLER_APP_ID` + `TELLER_CERT_PATH` + `TELLER_KEY_PATH` | Teller | mTLS cert required |
| `ENCRYPTION_KEY` | — | Required when using Plaid/Teller to encrypt stored access tokens |

### OAuth (Social Sign-In)

| Variable | Provider | Notes |
|---|---|---|
| `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` | Google Cloud Console | Add OAuth 2.0 client |
| `APPLE_CLIENT_ID` + `APPLE_TEAM_ID` + `APPLE_KEY_ID` + `APPLE_PRIVATE_KEY` + `APPLE_REDIRECT_URI` | Apple Developer | Requires paid Apple Developer account |

### Email (Notifications & Password Reset)

By default `EMAIL_MODE=console` — emails are printed to stdout (great for dev). To send real emails:

```
EMAIL_MODE=smtp
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=you@example.com
SMTP_PASSWORD=yourpassword
SMTP_FROM=noreply@example.com
```

---

## Local Development (Docker Compose)

### 1. Clone the repository

```bash
git clone https://github.com/your-username/pocketii.git
cd pocketii
```

### 2. Create your environment file

```bash
cp .env.example .env
```

Edit `.env`. Defaults in `.env.example` are enough for **local dev** (email verification off, gateway URL set, dev internal API key). For anything beyond your laptop, **replace** `SECRET_KEY` and `INTERNAL_API_KEY` (e.g. `openssl rand -hex 32`).

Add any optional API keys you have (market data, AI, etc.).

### 2b. Frontend build (before or after `docker compose build`)

```bash
./scripts/bootstrap-frontend.sh
```

Then build images so `frontend/static` includes the compiled JS/CSS:

```bash
docker compose build user
```

Or use `--build` on full `up` after running the bootstrap script.

### 3. Build and start

Docker can struggle with parallel builds on some machines. Use the serial build script to avoid I/O errors:

```bash
./scripts/docker-build-serial.sh up
```

Or standard Docker Compose (may hit I/O issues on resource-constrained machines):

```bash
docker compose up --build
```

### 4. Access the app

**Use the gateway in the browser** (`http://localhost:8080`) so `window.API_BASE` stays same-origin and all `/api/v1/*` routes work. The user service on `:8000` proxies to microservices when `GATEWAY_PUBLIC_URL` is unset; with the recommended `.env`, open **`8080`** for the full app.

| Service | URL |
|---|---|
| **App (via gateway)** | http://localhost:8080 |
| User service (direct) | http://localhost:8000 |
| Expense service (direct) | http://localhost:3001 |
| Budget service (direct) | http://localhost:3002 |
| Investments service (direct) | http://localhost:3003 |

Register a new account at http://localhost:8080 and start using the app. Email verification is disabled by default (`REQUIRE_EMAIL_VERIFICATION=false`).

### 5. Stopping

```bash
docker compose down
# To also remove volumes (wipes database):
docker compose down -v
```

---

## Running Services Individually

Each microservice can be run standalone with Python for faster iteration.

### Setup per service

```bash
cd user-microservice   # or expense-microservice, budget-microservice, investments-microservice
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your settings
```

### Start a service

```bash
uvicorn app.main:app --reload --port 8000   # user
uvicorn app.main:app --reload --port 3001   # expense
uvicorn app.main:app --reload --port 3002   # budget
uvicorn app.main:app --reload --port 3003   # investments
```

### Run migrations manually

```bash
python run_migration.py migrations/001_schema.sql
# Run all migrations in order (see docker-compose.yml for the full sequence per service)
```

### Start a background worker

```bash
python -m app.jobs.scheduler
```

---

## Environment Variables Reference

### Shared across all services

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | — | **Required.** JWT signing key. Must be identical across all services. |
| `ALGORITHM` | `HS256` | JWT algorithm |
| `JWT_ISSUER` | `user-microservice` | JWT `iss` claim |
| `JWT_AUDIENCE` | `expense-tracker` | JWT `aud` claim |
| `INTERNAL_API_KEY` | — | Shared key for internal service calls |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `SECURITY_HEADERS_ENABLED` | `true` | Enable HSTS, CSP, etc. |
| `HSTS_MAX_AGE_SECONDS` | `31536000` | HSTS max-age |

### Database (per service)

| Variable | Default | Description |
|---|---|---|
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_USER` | `postgres` | PostgreSQL user |
| `DB_PASSWORD` | `postgres` | PostgreSQL password |
| `DB_NAME` | *(per service)* | `users_db`, `expenses_db`, `budgets_db`, `investments_db` |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |

### User Service

| Variable | Default | Description |
|---|---|---|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | JWT access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime |
| `APP_BASE_URL` | `http://localhost:8000` | Used in email links |
| `EMAIL_MODE` | `console` | `console` or `smtp` |
| `REQUIRE_EMAIL_VERIFICATION` | `false` | Require email verify before login |
| `RATE_LIMIT_LOGIN_PER_MINUTE` | `10` | Login rate limit per IP |
| `RATE_LIMIT_REGISTER_PER_MINUTE` | `5` | Register rate limit per IP |
| `RATE_LIMIT_API_PER_MINUTE` | `200` | General API rate limit per IP |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | — | Google OAuth credentials |
| `DEMO_PUBLIC_URL` | — | Adds Watch/Try demo links on the landing page |

### Expense Service

| Variable | Default | Description |
|---|---|---|
| `RECEIPT_STORAGE_BACKEND` | `local` | `local` or cloud backend |
| `RECEIPT_STORAGE_PATH` | `/data/receipts` | Local receipt storage path |
| `PLAID_CLIENT_ID` / `PLAID_SECRET` | — | Plaid credentials |
| `PLAID_ENV` | `sandbox` | `sandbox` or `production` |
| `ENCRYPTION_KEY` | — | Required for Plaid/Teller token encryption (Fernet key) |
| `TELLER_APP_ID` / `TELLER_CERT_PATH` / `TELLER_KEY_PATH` | — | Teller mTLS credentials |
| `TELLER_ENV` | `sandbox` | `sandbox` or `production` |
| `EXCHANGE_RATE_SOURCE` | `ECB` | Exchange rate data source |

### Investments Service

| Variable | Default | Description |
|---|---|---|
| `MARKET_DATA_PROVIDER_ORDER` | `alpaca,finnhub,twelvedata,alphavantage` | Failover order for market data |
| `ALPACA_API_KEY` / `ALPACA_API_SECRET` | — | Alpaca market data + broker API |
| `ALPACA_DATA_BASE_URL` | `https://data.alpaca.markets` | Alpaca data endpoint |
| `FINNHUB_API_KEY` | — | Finnhub market data |
| `TWELVEDATA_API_KEY` | — | Twelve Data market data |
| `ALPHAVANTAGE_API_KEY` | — | Alpha Vantage market data |
| `QUOTE_CACHE_MAX_AGE_SECONDS` | `60` | Quote cache TTL to reduce rate-limit usage |
| `AI_EXPLAINER_PROVIDER_ORDER` | `groq,brave,generic` | AI explainer failover order |
| `GROQ_API_KEY` | — | Groq LLM for recommendation explanations |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model to use |
| `BRAVE_API_KEY` | — | Brave Search for recommendation research context |
| `NEWS_PROVIDER_ORDER` | `benzinga,finnhub,alphavantage` | News failover order |
| `BENZINGA_API_KEY` | — | Benzinga financial news (primary) |

### API Gateway

| Variable | Default | Description |
|---|---|---|
| `GATEWAY_RATE_LIMIT_PER_USER` | `200` | Gateway rate limit per user/min |
| `GATEWAY_RATE_LIMIT_PER_IP` | `300` | Gateway rate limit per IP/min |
| `PROXY_TIMEOUT_SECONDS` | `60` | Upstream proxy timeout |

---

## Database Migrations

Migrations are plain SQL files run in order via `run_migration.py`. They are idempotent — already-applied migrations are skipped automatically.

The Docker Compose stack runs all migrations automatically at startup before services start. The full migration sequences are in `docker-compose.yml`.

To run migrations manually against a running PostgreSQL:

```bash
# Example: user service migrations
cd user-microservice
export DB_HOST=localhost DB_PORT=5432 DB_USER=postgres DB_PASSWORD=postgres DB_NAME=users_db
python run_migration.py migrations/create_user_table.sql
python run_migration.py migrations/002_refresh_token.sql
# ... continue in numeric order
```

**Total migrations: 65 across all 4 databases** (keep `docker-compose.yml` and `deploy/release.sh` lists in sync)
- `users_db`: 19 migrations
- `expenses_db`: 28 migrations
- `budgets_db`: 4 migrations
- `investments_db`: 14 migrations

---

## Deployment

### Fly.io (Production)

The production app runs as a single Fly.io machine with all 4 services in one container (`Dockerfile.fly`). The API gateway on port 8080 is the only exposed port. The release command automatically runs all database migrations before the new version starts serving traffic.

The **web UI** is the **`frontend/`** tree (Jinja templates + `/static`); it is copied into the image next to `user-microservice`, not the `demo-app/` project. After UI changes, **redeploy/rebuild** so the new assets ship. See **[docs/MAIN_PLATFORM.md](docs/MAIN_PLATFORM.md)** for paths and keeping Fly `deploy/release.sh` investment migrations in sync with `docker-compose`.

#### 1. Install Fly CLI

```bash
brew install flyctl   # macOS
# or: curl -L https://fly.io/install.sh | sh
```

#### 2. Authenticate

```bash
fly auth login
```

#### 3. Create a Postgres database

```bash
fly postgres create --name pocketii-db --region ewr
fly postgres attach --app pocketii pocketii-db
```

> The app uses individual `DB_*` variables rather than `DATABASE_URL`. Set them via secrets below.

#### 4. Set required secrets

```bash
fly secrets set \
  SECRET_KEY=$(openssl rand -hex 32) \
  INTERNAL_API_KEY=$(openssl rand -hex 16) \
  DB_HOST=pocketii-db.internal \
  DB_PORT=5432 \
  DB_USER=postgres \
  DB_PASSWORD=your-db-password \
  --app pocketii
```

Set optional secrets for any integrations you want enabled:

```bash
fly secrets set \
  ALPACA_API_KEY=your-key \
  ALPACA_API_SECRET=your-secret \
  FINNHUB_API_KEY=your-key \
  GROQ_API_KEY=your-key \
  PLAID_CLIENT_ID=your-id \
  PLAID_SECRET=your-secret \
  ENCRYPTION_KEY=your-fernet-key \
  GOOGLE_CLIENT_ID=your-id \
  GOOGLE_CLIENT_SECRET=your-secret \
  EMAIL_MODE=smtp \
  SMTP_HOST=your-smtp-host \
  SMTP_USER=your-smtp-user \
  SMTP_PASSWORD=your-smtp-password \
  --app pocketii
```

**Recommendations & market data (same Fly machine — investment service on `:3003`):**  
Provider **URLs** and default **provider order** are in `fly.toml` `[env]`. You must set **API keys** as Fly secrets so they are injected into the container (there is no `investments-microservice/.env` file in the image).

Variable names match `investments-microservice/app/core/config.py` / `investments-microservice/.env.example`:

```bash
fly secrets set \
  FINNHUB_API_KEY=your-finnhub-token \
  BENZINGA_API_KEY=your-benzinga-token \
  TWELVEDATA_API_KEY=your-twelvedata-key \
  ALPHAVANTAGE_API_KEY=your-alphavantage-key \
  --app pocketii
```

Optional overrides (defaults already in `fly.toml`):

```bash
fly secrets set \
  NEWS_PROVIDER_ORDER=benzinga,finnhub,alphavantage \
  MARKET_DATA_PROVIDER_ORDER=alpaca,finnhub,twelvedata,alphavantage \
  --app pocketii
```

Bulk import template (do not commit real values): see [`deploy/fly-investment-providers.example.env`](deploy/fly-investment-providers.example.env), then run `fly secrets import --app pocketii < your-local.env`.

After changing secrets, redeploy or restart machines so new values load: `fly deploy --app pocketii` or `fly machines restart --app pocketii`.

#### 5. Deploy

```bash
fly deploy --app pocketii
```

The Fly.io configuration (`fly.toml`) is already set up:
- Region: `ewr` (Newark)
- 1 CPU, 1 GB RAM
- Auto-stop when idle, auto-start on traffic
- HTTPS forced

---

### Render (Demo App)

The demo app is a standalone FastAPI app with SQLite — no PostgreSQL, Redis, or API keys required.

#### Option A: Render Blueprint (recommended)

Connect your GitHub repo to Render and select the `render.yaml` blueprint. Render will automatically create and configure the `pocketii-demo` service.

After deploy, set `PUBLIC_BASE_URL` to your service URL in the Render dashboard.

#### Option B: Manual deploy

1. Create a new **Web Service** on Render
2. Set **Root Directory** to `demo-app`
3. Set **Dockerfile Path** to `./Dockerfile`
4. Set environment variables:

```
DEMO_JWT_SECRET=<generate a random string>
DEMO_RESET_INTERVAL_SECONDS=900
PUBLIC_BASE_URL=https://your-service.onrender.com
DEMO_AI_ENABLED=false
```

#### Optional: Enable AI Narration in the Demo

```
DEMO_AI_ENABLED=true
DEMO_AI_API_URL=https://api.openai.com/v1/chat/completions
DEMO_AI_API_KEY=your-openai-key
DEMO_AI_MODEL=gpt-4o-mini
DEMO_AI_DAILY_CAP=200
```

---

## Project Structure

```
pocketii/
├── user-microservice/          # Auth, profiles, households, notifications, frontend
│   ├── app/
│   │   ├── main.py
│   │   ├── routers/            # auth, users, households, sessions, settings, net-worth, etc.
│   │   ├── jobs/               # digest_sender, retention_purge, webhook_processor
│   │   └── core/               # config, JWT, security middleware
│   ├── frontend/               # Jinja2 templates + JS + CSS (35+ pages)
│   ├── migrations/             # 19 SQL migrations
│   └── Dockerfile
│
├── expense-microservice/       # Expenses, income, receipts, goals, insights, bank links
│   ├── app/
│   │   ├── routers/            # expenses, income, receipts, goals, insights, plaid, teller, etc.
│   │   ├── jobs/               # exchange_rate_sync, anomaly_nudge, recurring, round_up, etc.
│   │   └── services/           # ExpenseDataService, InsightsService, PlaidDataService, etc.
│   ├── migrations/             # 28 SQL migrations
│   └── Dockerfile
│
├── budget-microservice/        # Budgets, alert evaluation
│   ├── app/
│   │   ├── routers/
│   │   └── jobs/               # budget alert worker
│   ├── migrations/             # 4 SQL migrations
│   └── Dockerfile
│
├── investments-microservice/   # Holdings, portfolio, market data, recommendations
│   ├── app/
│   │   ├── routers/            # holdings, portfolio, recommendations, market, news, risk, alpaca
│   │   ├── jobs/               # alpaca_sync, etf_sync, returns_backfill, sentiment, tax_harvesting
│   │   └── services/           # market data providers, AI explainer, news pipeline
│   ├── migrations/             # 14 SQL migrations
│   └── Dockerfile
│
├── api-gateway/                # JWT validation, rate limiting, reverse proxy
│   ├── app/
│   └── Dockerfile
│
├── mobile/                     # Expo (Expo Go) — tabs shell, secure-store tokens, same gateway URL as web
│   ├── app/                    # expo-router layouts
│   └── src/                    # config + auth token helpers
│
├── demo-app/                   # Standalone SQLite demo (watch + interactive mode)
│   ├── app/
│   ├── Dockerfile
│   └── render.yaml
│
├── docker/
│   └── postgres/init/          # PostgreSQL init scripts (creates the 4 databases)
│
├── deploy/
│   ├── start.sh                # Fly.io startup: launches all 4 services + gateway
│   └── release.sh              # Fly.io release command: runs all migrations
│
├── scripts/
│   ├── docker-build-serial.sh  # Builds one image at a time to avoid Docker I/O errors
│   └── bootstrap-frontend.sh   # npm ci + typecheck + build JS/CSS into frontend/static
│
├── docker-compose.yml          # Local development stack
├── Dockerfile.fly              # Single-image Fly.io build
├── fly.toml                    # Fly.io app configuration
├── render.yaml                 # Render Blueprint (demo app only)
├── .env.example                # Copy to .env for Docker Compose variable substitution
```

---

## Important Considerations

### Security

- **Never commit `.env` files or real secrets.** The root **`.env.example`** documents dev defaults; generate a fresh `SECRET_KEY` (`openssl rand -hex 32`) before any real deployment and change `INTERNAL_API_KEY`.
- **Rotate `SECRET_KEY` carefully.** Changing it invalidates all existing JWTs and refresh tokens, immediately logging out all users.
- **`INTERNAL_API_KEY`** should be a random string shared between services. Without it, internal endpoints (e.g., the budget service writing user notifications) are unauthenticated on your internal network.
- **HTTPS is enforced in production.** Fly.io sets `force_https = true`. The default HSTS max-age is 1 year (`31536000`).
- Email verification is off by default (`REQUIRE_EMAIL_VERIFICATION=false`) for development convenience. Enable it in production.

### Alpaca & Market Data

- The investments module works without any market data key, but live quotes, recommendations, and portfolio performance metrics will not be available.
- **Alpaca's paper trading account (free)** provides the highest quality data. Sign up at [alpaca.markets](https://alpaca.markets) and generate API keys under "Paper Trading."
- Alpaca is also used for **live broker position sync** (`/api/v1/alpaca`), which reads your real or paper portfolio holdings directly from the broker.
- The failover chain `alpaca → finnhub → twelvedata → alphavantage` means the system degrades gracefully — if Alpaca is unavailable or rate-limited, it moves to the next provider automatically.
- At minimum, adding a **Finnhub key** (free, 60 req/min) provides a solid fallback with no daily cap concerns.

### Plaid Bank Linking

- Start with `PLAID_ENV=sandbox` — Plaid provides test credentials and simulated institutions without connecting real banks.
- You **must** set `ENCRYPTION_KEY` when using Plaid or Teller. This is a Fernet key used to encrypt stored access tokens at rest. Generate one with:
  ```python
  from cryptography.fernet import Fernet
  print(Fernet.generate_key().decode())
  ```
- Moving to `PLAID_ENV=production` requires Plaid approval and a paid plan.

### Docker Build Performance

On resource-constrained machines or machines with limited Docker disk I/O, parallel builds can fail. Always use the serial build script:

```bash
./scripts/docker-build-serial.sh up
```

### Database

- The stack creates 4 separate PostgreSQL databases: `users_db`, `expenses_db`, `budgets_db`, `investments_db`.
- The init script in `docker/postgres/init/` creates all 4 databases automatically when the PostgreSQL container first starts.
- Migrations are **forward-only and idempotent** — safe to re-run at any time.
- The **budget service reads directly from `expenses_db`** (read-only queries) for budget calculations. Both `DB_*` (budgets_db) and `EXPENSE_DB_*` variables must be set correctly for the budget service.

### Demo App

- The demo app uses **SQLite** — no PostgreSQL or Redis required to run it.
- Sessions reset after 15 minutes of inactivity by default (`DEMO_RESET_INTERVAL_SECONDS=900`).
- Hard reset after 30 minutes idle (`DEMO_IDLE_RESET_SECONDS=1800`).
- AI narration is off by default to prevent unexpected API costs. Enable explicitly with `DEMO_AI_ENABLED=true` and set `DEMO_AI_DAILY_CAP` to cap spend.

### Rate Limits

Default limits (requests per minute):

| Endpoint | Limit |
|---|---|
| Login | 10 / IP |
| Register | 5 / IP |
| General API | 200 / IP |
| Expensive endpoints (reports, export, summary) | 60 / user |
| Gateway global | 200 / user · 300 / IP |

All limits are configurable via environment variables.

### Multi-Currency

Exchange rates are fetched from the ECB (European Central Bank) and cached locally. All amounts are stored in the user's base currency. `EXCHANGE_RATE_SOURCE=ECB` is the default and requires no API key.

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes
4. Open a pull request

Please open an issue first for major changes.

