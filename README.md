# SOT Analyzer v1.1

[![CI](https://github.com/Bjproducts/SportAnalyzer/actions/workflows/ci.yml/badge.svg)](https://github.com/Bjproducts/SportAnalyzer/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.1.0-b8f34a)](https://github.com/Bjproducts/SportAnalyzer)

Historical football research platform focused on **shots on target (SOT)**.

Search a player, filter to starts, split home and away, and read the
match-by-match SOT record — with every percentage reported alongside the
sample size behind it.

## v1.1 feature set

### Player research

- Accent-insensitive player search, player profiles and current-team links.
- Complete competitive appearance logs across competitions, with Starts-only
  mode and Last 5, Last 10 or Last 20 evidence windows.
- Match-level shots, SOT, goals, assists, minutes, venue, position, early exits
  and share of team SOT.
- 1+, 2+ and 3+ SOT hit rates, averages, per-90 metrics, shot accuracy and
  recent-form summaries.
- Home/away, competition, season and opponent splits with their sample sizes.
- Current and longest streaks, including honest treatment of missing data.
- Two-to-four-player comparison workspace.

### Team and fixture analysis

- Searchable team pages and current squads.
- Top-five SOT candidates for every populated squad, with Last 5/10/20 and
  home/away controls.
- Paginated fixture history and upcoming fixtures organized by UTC date.
- Five matchup candidates per team with an explainable 0-100 research score.
- Daily scoring combines recent form, Wilson sample adjustment, SOT volume,
  home/away record, starting-minute stability and opponent SOT allowed.
- Positive evidence, possible failure factors, confidence labels, defensive
  strength and explicit unconfirmed-lineup warnings.

### Data platform

- SportsAPI Pro adapters for MLS, Premier League, La Liga, Bundesliga, Ligue 1,
  Serie A, Süper Lig and Leagues Cup.
- API-Football, StatsBomb Open Data and deterministic demo providers behind one
  provider contract.
- Quota-safe, resumable and idempotent fixture/statistics synchronization.
- PostgreSQL production storage, SQLite local/demo support and Alembic
  migrations.
- Auditable raw provider payloads, ingestion jobs, structured errors, health
  probes, secret redaction and protected administration endpoints.
- FastAPI OpenAPI documentation in development and a responsive Next.js 15 UI.

The candidate score is an evidence-ranking tool, not a probability, betting
recommendation or guarantee. Future lineups, injuries and tactical roles can
change after the historical evidence was collected.

---

## Core data principles

These are enforced in code, not just documented:

| Principle | How it is enforced |
|---|---|
| Missing SOT is never zero | `shots_on_target` is `int \| None`. Records with `None` are excluded from rate denominators and counted separately. |
| A percentage never travels alone | Rate calculations return `(successes, valid, missing, percentage)`. The UI cannot render a bare `%`. |
| Division never lies | Safe division returns `None` — not `0.0` — when the denominator is zero. The UI renders `—`. |
| Small samples do not win rankings | Rankings use a Wilson lower bound plus a configurable minimum-start gate (default 5), so 2/2 ranks below 18/20. |
| Starts and substitute appearances are distinct | Substitute appearances are viewable but excluded from start-based percentages. |
| A short start is still a start | Starts under 45 minutes are flagged `early_exit`, never dropped. |
| Provider data is auditable | The raw provider payload is stored on every player-fixture row. |
| Imports are idempotent | Unique constraint on `(fixture_id, player_id, team_id)` + upsert. |

---

## Requirements

- Docker Desktop (or Docker Engine + Compose v2)
- For local, non-Docker work: Python 3.12+ and Node.js 20+

---

## Quick start (Docker)

```bash
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD and ADMIN_API_TOKEN.
# Generate a token with:
#   python -c "import secrets; print(secrets.token_urlsafe(32))"

docker compose up -d --build
docker compose exec backend alembic upgrade head    # from Phase 2 onward
```

| Service | URL |
|---|---|
| Web | http://localhost:3000 |
| API health | http://localhost:8000/api/health |
| API docs | http://localhost:8000/docs |

`docker compose down` stops the stack and keeps the database volume.
`docker compose down -v` also deletes the data.

---

## Local development (without Docker)

The API and the web app can run on the host while Postgres stays in Docker.

**Postgres only:**

```bash
docker compose up -d db
```

**Backend:**

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e "backend[dev]"     # Windows
# .venv/bin/python -m pip install -e "backend[dev]"       # macOS / Linux

# Point the API at the container's published port:
# in .env set POSTGRES_HOST=localhost

cd backend
../.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

### Zero-dependency demo (PowerShell)

When Docker is unavailable, the complete product can run against an ignored
local SQLite database while still using the production ingestion service:

```powershell
cd backend
$env:ALEMBIC_DATABASE_URL = "sqlite+aiosqlite:///./sot_demo.db"
../.venv/Scripts/alembic upgrade head
$env:DATABASE_URL = "sqlite+aiosqlite:///./sot_demo.db"
../.venv/Scripts/python -m app.ingestion.seed_demo
../.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# In a second terminal:
cd frontend
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Open http://127.0.0.1:3000. The deterministic demo contains 12 fixtures and
six players, including one deliberately missing SOT value to exercise the data
quality safeguards.

---

## Production deployment: Netlify + FastAPI host

Netlify deploys the Next.js frontend. The Python API, ingestion jobs and
PostgreSQL database must run on a container-capable backend host such as
Render, Railway, Fly.io or a VPS. Netlify's maintained OpenNext adapter handles
the App Router automatically; this repository intentionally does not pin the
adapter version.

### 1. Deploy the backend and PostgreSQL

Create a PostgreSQL database and deploy `backend/Dockerfile` using its
`production` target. Configure these server-side variables on the backend host:

```dotenv
ENVIRONMENT=production
LOG_LEVEL=INFO
LOG_JSON=true
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE
CORS_ORIGINS=https://YOUR-SITE.netlify.app
ADMIN_API_TOKEN=GENERATE_A_LONG_RANDOM_VALUE
FOOTBALL_PROVIDER=sportsapipro
SPORTS_API_PRO_KEY=YOUR_PRIVATE_PROVIDER_KEY
SPORTS_API_PRO_HISTORY_PAGES=1
FOOTBALL_API_RATE_LIMIT_PER_MINUTE=10
```

Do not put `SPORTS_API_PRO_KEY`, `ADMIN_API_TOKEN` or `DATABASE_URL` in
Netlify. Run the database migration once on the backend host:

```bash
cd backend
alembic upgrade head
```

Verify `https://YOUR-API-HOST/api/health/ready` before deploying the frontend.
Production data is not committed to Git; run an intentional quota-safe sync on
the backend after migration.

### 2. Connect GitHub to Netlify

1. In Netlify, select **Add new project → Import an existing project**.
2. Choose `Bjproducts/SportAnalyzer`.
3. The root `netlify.toml` supplies Base directory `frontend`, build command
   `npm run build:netlify`, publish directory `.next`, and Node.js 22.
4. Add `NEXT_PUBLIC_API_BASE_URL=https://YOUR-API-HOST/api` under Netlify
   environment variables. It is browser-visible and must contain no secret.
5. Optionally set `NEXT_PUBLIC_SITE_URL` to the final custom domain. Netlify's
   built-in deployment URL is used automatically when it is omitted.
6. Deploy. The build deliberately fails if the API URL is missing, uses HTTP,
   points to localhost, contains credentials, or does not end in `/api`.

For deploy previews, keep the production origin in `CORS_ORIGINS` and set an
appropriately scoped backend regex, replacing the site name:

```dotenv
CORS_ORIGIN_REGEX=^https://deploy-preview-[0-9]+--YOUR-SITE\.netlify\.app$
```

After Netlify assigns the final domain, update `CORS_ORIGINS` on the backend
and restart it. These settings follow Netlify's current [Next.js deployment](https://docs.netlify.com/build/frameworks/framework-setup-guides/nextjs/overview/)
and [monorepo configuration](https://docs.netlify.com/build/configure-builds/monorepos/) guidance.

### Deployment checklist

- Backend readiness endpoint returns HTTP 200.
- Alembic migrations are at `head`.
- Netlify has only public frontend variables; provider/database secrets stay on
  the backend host.
- Backend CORS contains the exact Netlify production origin.
- Player search, team ranking and Upcoming pages load real API data.
- GitHub Actions and the Netlify production build both pass.

---

## Verification commands

Run these from the repository root unless noted.

```bash
# Backend tests
cd backend && ../.venv/Scripts/python -m pytest tests -v

# Backend lint / format / types
cd backend && ../.venv/Scripts/python -m ruff check .
cd backend && ../.venv/Scripts/python -m ruff format --check .
cd backend && ../.venv/Scripts/python -m mypy app

# Frontend types / lint / build
cd frontend && npx tsc --noEmit
cd frontend && npm run lint
cd frontend && npm run build
```

A `Makefile` wraps these (`make test`, `make check`, `make up`). It needs a
POSIX shell — on Windows use Git Bash or WSL, or run the raw commands above.

---

## Project layout

```
.
├── backend/
│   ├── app/
│   │   ├── api/            # Routers, dependencies, error translation
│   │   ├── analytics/      # PURE calculations. No DB or provider imports.
│   │   ├── ingestion/      # Provider clients, normalisation, import jobs
│   │   ├── models/         # SQLAlchemy ORM models
│   │   ├── repositories/   # All SQLAlchemy queries live here
│   │   ├── schemas/        # Pydantic request/response models
│   │   ├── services/       # Orchestration: repositories + analytics
│   │   ├── core/           # Config, logging, exceptions
│   │   ├── database.py
│   │   └── main.py
│   ├── alembic/
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── app/                # Next.js App Router pages
│   ├── components/
│   ├── hooks/
│   ├── lib/
│   ├── types/
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── Makefile
```

### The one architectural rule

`app/analytics/` is pure. It imports no SQLAlchemy, no HTTP client and no
provider module. It accepts typed value objects and returns typed results,
which is what makes the full matrix of edge cases (no matches, all missing
SOT, streak ending in failure, duplicate records) testable without a database.

Provider-specific logic stays inside `app/ingestion/`, behind the
`FootballDataProvider` protocol.

---

## Configuration

Every setting is read from the environment via `app/core/config.py`. Nothing
reads `os.environ` directly. See `.env.example` for the full annotated list.

Security notes:

- The provider API key is **server-side only**. It is never given a
  `NEXT_PUBLIC_` prefix and never reaches the browser.
- `POST /api/admin/*` routes require an `X-Admin-Token` header, compared in
  constant time. If `ADMIN_API_TOKEN` is unset the routes **fail closed**.
- Logs are scrubbed: any field whose key contains `password`, `token`,
  `secret`, `api_key`, `authorization`, `credential`, `dsn` or `database_url`
  is replaced with `***redacted***`, including inside nested dicts.
- API docs are disabled when `ENVIRONMENT=production`.
- `.env` is gitignored; only `.env.example` is committed.

---

## Database and migrations

Seven tables: `competitions`, `seasons`, `teams`, `players`, `fixtures`,
`player_fixture_stats` and `ingestion_jobs`.

**Applying migrations**

```bash
docker compose exec backend alembic upgrade head

# Or locally, from backend/ with the venv active:
alembic upgrade head
```

**Creating a migration after changing a model**

```bash
cd backend
alembic revision --autogenerate -m "add whatever you added"
# Read the generated file before committing it. Always.
alembic upgrade head
```

Run Alembic from the activated virtualenv (or inside the backend container):
the post-write hooks shell out to `python -m ruff`, which only resolves there.

`tests/test_migrations.py` fails the build if the migration chain and the ORM
models disagree, so a model change without a matching migration cannot reach
`main`.

**Things worth knowing**

- `shots_on_target` is nullable and `NULL` means *unreported*. The
  `data_quality_status` column records why.
- CHECK constraints enforce what the analytics layer assumes: a row cannot be
  both a start and a substitute appearance, SOT cannot exceed shots, team and
  opponent must differ, ratings sit in 0–10, minutes in 0–200.
- Enums are stored as `VARCHAR` + CHECK rather than native PostgreSQL enums, so
  adding a value is an ordinary migration. Autogenerate is configured to ignore
  these type-generated constraints — without that filter it emits migrations
  that *drop* them (see `app/core/migrations.py`).
- `early_exit` is stored, but computed through the same
  `app.analytics.rules.is_early_exit` the analytics engine uses, so the column
  and any recomputation cannot disagree.
- Player and team names carry a folded `search_name` (lowercase, accent-free),
  so searching `odegaard` finds `Martin Ødegaard`.
- All timestamps are `TIMESTAMP WITH TIME ZONE` in UTC.

---

## Analytics engine

Phase 3 is implemented as a pure, typed Python package under
`backend/app/analytics/`:

- `MatchStatLine` is an immutable, provider-independent input record. It
  rejects impossible identifiers, dates, appearance combinations and stat
  values before they can corrupt an aggregate.
- Summaries report appearance counts, 1+/2+/3+ SOT rates, shot volume,
  per-90 figures, accuracy, team SOT share and minutes profiles.
- Venue splits keep home and away sample sizes separate. Competition, season
  and opponent split helpers use the same rate result type.
- Recent form windows count the latest starts, not the latest valid records.
  Missing SOT inside a last-five window stays in that window and is reported;
  the engine never reaches farther back to manufacture five valid results.
- Streaks use starts only. Missing SOT is neutral: it neither extends nor
  breaks a streak, and `missing_in_window` / `is_reliable` tells the UI when a
  current streak crosses an evidence gap.
- Every public window, threshold and minimum-sample parameter is validated.
  Duplicate fixture/player/team records are defensively removed even though
  the database also prevents them.

The analytics tests cover empty and one-match samples, all successes, all
failures, early exits, substitutes, mixed venues, missing and untrusted SOT,
recent windows, rolling trends, current and longest streaks, never-failed
players, duplicates, grouped splits and package purity. The current analytics
package has 100% statement coverage.

---

## Player analytics API

Phase 4 exposes the analytics engine through validated, paginated endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /api/players` | Accent-folded player search or paginated player listing |
| `GET /api/players/{id}` | Player profile and current-team context |
| `GET /api/players/{id}/matches` | Newest-first match history and row-level SOT results |
| `GET /api/players/{id}/sot-summary` | Summary metrics plus last-5/10/20 form |
| `GET /api/players/{id}/splits` | Home/away, competition, season and opponent splits |
| `GET /api/players/{id}/streaks` | Current/longest streak and latest failed start |

Example:

```bash
curl "http://localhost:8000/api/players?q=odegaard"
curl "http://localhost:8000/api/players/1/matches?venue=away&last_n=10"
curl "http://localhost:8000/api/players/1/sot-summary?starts_only=true&season=2024"
```

Filters compose in SQL and are represented directly in the URL. Depending on
the endpoint, they include `starts_only`, `venue`, `competition_id`, `season`,
`last_n`, `date_from`, `date_to`, `minimum_minutes`, `opponent_id`, `team_id`,
`position`, `sot_threshold`, `threshold` and `minimum_starts`. Page sizes are
limited to 100. Invalid filters return the standard structured 422 envelope;
unknown players return a structured 404.

Only competitive, finished fixtures are included. Match rows expose nullable
1+ and 2+ SOT outcomes: missing or untrusted SOT produces `null`, never a false
failure. Every percentage response includes successes, failures, valid count,
missing count and a sample-aware description.

---

## Data ingestion

Provider data is fetched through authorised APIs only. The ingestion layer
respects the provider's documented rate limits and backs off exponentially on
transient failures. Failed imports are never silently dropped — the reason is
recorded in the ingestion job log.

Phase 6 ships four implementations of the `FootballDataProvider` contract:

- `fake` is deterministic, credential-free and powers the auditable demo.
- `apifootball` is an authorised API-Football adapter with server-side API-key
  handling, throttling, retries and provider-payload preservation.
- `sportsapipro` is the quota-aware SportsAPI Pro V2 adapter used for the seven
  tracked leagues, Leagues Cup and their explicit player shots-on-target statistics.
- `statsbomb` imports the competitions available in the free StatsBomb Open
  Data repository; its public competition coverage is intentionally limited.

Fixture and player-stat imports are idempotent and tracked as persistent jobs.
The protected operations are `POST /api/admin/ingestion/fixtures` and
`POST /api/admin/ingestion/player-statistics`; job history is available at
`GET /api/admin/ingestion/jobs`.

This project does not scrape websites and does not bypass authentication,
rate limits or access controls.

### Connect SportsAPI Pro (seven leagues plus Leagues Cup)

SportsAPI Pro covers MLS, the Premier League, La Liga, Bundesliga, Ligue 1,
Serie A, Süper Lig and Leagues Cup. Its free plan currently allows 100 calls per day, so the
sync defaults to one 30-match history page and at most two new player-stat
fixtures per league. Put the key in the root `.env`; it stays on the backend:

```dotenv
FOOTBALL_PROVIDER=sportsapipro
SPORTS_API_PRO_KEY=replace_with_your_private_key
SPORTS_API_PRO_BASE_URL=https://v2.football.sportsapipro.com
SPORTS_API_PRO_HISTORY_PAGES=1
FOOTBALL_API_RATE_LIMIT_PER_MINUTE=10
DATABASE_URL=sqlite+aiosqlite:///./sot_sportsapi.db
```

Create the provider-specific database from `backend/`, then import a season:

```powershell
$env:ALEMBIC_DATABASE_URL = "sqlite+aiosqlite:///./sot_sportsapi.db"
../.venv/Scripts/alembic upgrade head

../.venv/Scripts/python -m app.ingestion.sync_sports_api `
  --season 2025 `
  --leagues all `
  --max-stat-fixtures-per-league 2
```

Use `--max-stat-fixtures-per-league 0` for a fixtures-only schedule refresh.
Imports are incremental and idempotent, so already populated matches do not
consume another player-stat request. A provider-side missing match is recorded
as a partial import and does not prevent later matches or leagues from loading.

For quota-efficient history backfills, use `--history-pages` once to discover
older fixtures (30 per page), then resume existing fixtures without paying for
fixture discovery again:

```powershell
# Discover roughly six recent matchdays and fill the newest missing statistics.
../.venv/Scripts/python -m app.ingestion.sync_sports_api `
  --season 2026 --leagues mls --history-pages 3 `
  --max-stat-fixtures-per-league 65

# On the next quota reset, continue without fixture-list API calls.
../.venv/Scripts/python -m app.ingestion.sync_sports_api `
  --season 2026 --leagues mls --statistics-only `
  --max-stat-fixtures-per-league 90
```

The SportsAPI Pro league identifiers used by the adapter are:

| Slug | League | Provider ID |
|---|---|---:|
| `mls` | Major League Soccer | 242 |
| `epl` | Premier League | 17 |
| `la-liga` | La Liga | 8 |
| `bundesliga` | Bundesliga | 35 |
| `ligue-1` | Ligue 1 | 34 |
| `serie-a` | Serie A | 23 |
| `super-lig` | Süper Lig | 52 |
| `leagues-cup` | Leagues Cup | 13783 |

### Connect API-Football for live league data

Create an account at [API-Football](https://dashboard.api-football.com), copy
the key from **Account → My Access**, and place it only in the root `.env`:

```dotenv
FOOTBALL_PROVIDER=apifootball
FOOTBALL_API_KEY=replace_with_your_private_key
FOOTBALL_API_RATE_LIMIT_PER_MINUTE=10
```

The bundled live catalog uses API-Football's stable league identifiers:

| Slug | League | Provider ID | Season format |
|---|---|---:|---|
| `mls` | Major League Soccer | 253 | Calendar year |
| `epl` | Premier League | 39 | Starting year (`2026` = 2026/27) |
| `la-liga` | La Liga | 140 | Starting year |
| `bundesliga` | Bundesliga | 78 | Starting year |
| `ligue-1` | Ligue 1 | 61 | Starting year |
| `serie-a` | Serie A | 135 | Starting year |
| `super-lig` | Süper Lig | 203 | Starting year |

Use a clean database for the live provider. Do not import live rows into
`sot_demo.db`: the schema intentionally supports one provider per deployment,
and provider identifiers are not interchangeable. For local SQLite, create the
live database once from `backend/`:

```powershell
$env:ALEMBIC_DATABASE_URL = "sqlite+aiosqlite:///./sot_live.db"
../.venv/Scripts/alembic upgrade head
$env:DATABASE_URL = "sqlite+aiosqlite:///./sot_live.db"
```

Restart the API with that same `DATABASE_URL`, then run a quota-safe
incremental sync from `backend/`. The default imports all league fixture lists plus the newest
10 finished fixtures that do not yet have player statistics—at most 77 provider
requests for all seven leagues on a fresh run:

```powershell
# Keep this line in each new PowerShell terminal when using local SQLite.
$env:DATABASE_URL = "sqlite+aiosqlite:///./sot_live.db"

../.venv/Scripts/python -m app.ingestion.sync_leagues --season 2026
```

Target selected leagues with `--leagues`, for example:

```powershell
../.venv/Scripts/python -m app.ingestion.sync_leagues `
  --season 2025 `
  --leagues epl,la-liga,bundesliga,ligue-1,serie-a,super-lig

../.venv/Scripts/python -m app.ingestion.sync_leagues `
  --season 2026 `
  --leagues mls
```

Use `--max-stat-fixtures-per-league 0` to refresh fixture schedules without
spending calls on player statistics. Use `--all-missing-statistics` only when
the account has enough daily quota for the initial historical backfill. Every
later run is incremental and idempotent: completed fixtures already carrying
statistics are not requested again. The JSON result reports the provider's
remaining daily and per-minute quota when those headers are present.

The protected `GET /api/admin/ingestion/leagues` endpoint returns the same
catalog. Provider keys remain server-side and must never use a `NEXT_PUBLIC_`
environment variable.

---

## Rankings and comparison

Phase 7 adds squad discovery, fixture browsing, team rankings and side-by-side
player comparison:

| Endpoint | Purpose |
|---|---|
| `GET /api/teams` | Team listing, prioritising teams with registered squads |
| `GET /api/teams/{id}/players` | Current squad |
| `GET /api/teams/{id}/sot-rankings` | Sample-adjusted 1+ SOT leaderboard |
| `GET /api/players/compare` | Two-to-four-player evidence matrix |
| `GET /api/fixtures` | Validated, paginated fixture history |
| `GET /api/fixtures/upcoming-analysis` | Daily previews with five candidates per team |

The Next.js UI includes player search, URL-backed venue/window/start filters,
summary cards, SOT trend charts, match logs, venue/opponent/competition splits,
team rankings and a two-to-four-player comparison workspace.

Team rankings default to the top five 1+ SOT candidates over their last five
starts across all competitions. `last_n=5|10|20` changes the evidence window,
and `limit` controls how many ranked candidates are returned. Player pages show
all appearances by default; the Starts-only toggle remains available.

The **Upcoming** workspace ranks both squads for every scheduled fixture on a
selected UTC date. Its 0-100 research score combines recent 1+ SOT form (35%),
Wilson sample-adjusted reliability (20%), SOT volume (15%), matching home/away
record (10%), starting-minute stability (10%) and the opponent's recent SOT
allowed (10%). It is explicitly not a probability: every candidate includes
supporting evidence, possible failure factors, sample confidence and an
unconfirmed-lineup warning. `window=5|10|20` changes the evidence window and
`candidates_per_team=1..5` controls the shortlist size. Opening the page uses
stored data only and makes no provider call.

---

## Build status

| Phase | Scope | Status |
|---|---|---|
| 1 | Monorepo, Docker Compose, FastAPI, Next.js, health checks, config | ✅ Done |
| 2 | Models, Alembic, indexes, unique constraints, DB tests | ✅ Done |
| 3 | Analytics engine: summaries, splits, form, streaks | ✅ Done |
| 4 | API: search, matches, summary, splits, streaks, pagination | ✅ Done |
| 5 | Frontend: search, player page, filters, table, charts | ✅ Done |
| 6 | Provider interface, API-Football adapter, demo import, job tracking | ✅ Done |
| 7 | Team rankings, player comparison, sample safeguards | ✅ Done |
| 8 | Upcoming fixtures, matchup scoring, defensive context, risk explanations | ✅ Done |
