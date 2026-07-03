# AGENTS.md

Flask app for importing race timing CSV files, storing lap/standing data in SQLite, and rendering server-side analysis pages with interactive charts. Deployed on Ubuntu + Nginx + systemd + Gunicorn.

## Commands

```bash
pip install -r requirements.txt         # Flask + Flask-SQLAlchemy + Gunicorn only
python run.py                            # dev: http://localhost:5000, debug, 0.0.0.0
rm instance/timing.db && python run.py   # fresh DB + seed (admin/admin123)
gunicorn --bind 127.0.0.1:8000 --workers 2 "app:create_app()"  # production
python -m unittest discover -s tests     # 32 tests across 10 files
python -m unittest discover tests/       # same
python -m unittest tests.test_standings_sorting.TestName.test_method  # single test
```

Root-level `test_tl_integration.py` is NOT in `tests/` — run separately or it gets skipped.

## Architecture

- **app.py** — `create_app()` factory; runs `db.create_all()` then inline `ALTER TABLE` migrations via `_ensure_*()` functions. CSRF on all POST (skips `/api/`). Context processor injects `current_user` + `csrf_token`.
- **models.py** — `User`, `TimeKeeper`, `Event`, `Session`, `Standing`, `LapRecord`, `CarConfig`, `CarModelColor`.
- **routes.py** — Single `Blueprint("main")`. Auth, event CRUD, upload CSV, session detail (5 views), analytics API, car config editor, admin refresh, CSV reupload.
- **parsers/** — `BaseParser` ABC → `PARSER_REGISTRY` dict in `parsers/__init__.py`. Two parsers: `TSLTimingParser` (2-file CSV, comma-delimited) and `SwissTimingParser` (up to 5 files, semicolon-delimited). `detect_laps.py` — standalone functions reused by parser and admin refresh.
- **templates/** — 18 Jinja2 templates, no frontend build. CDN: Tailwind CSS, Chart.js 4.4 + chartjs-plugin-zoom, Lucide icons.
- **static/** — `css/theme.css` (light/dark), `js/theme.js`, `js/charts.js` (13 chart types with LTTB decimation, max 200 samples), `js/table-sort.js`.

## Key conventions

- **`session_time` is a Float** (seconds from session start), not datetime. Used as chart X-axis.
- **No pandas** — stdlib `csv` module only. No frontend build pipeline.
- **Tests**: `unittest.TestCase` (not pytest). Each test creates its own temp DB via `app.create_app()`.
- **Import order**: stdlib → Flask → local modules. One import per line.
- **No DB migration framework** — `db.create_all()` + inline `ALTER TABLE` in `app.py`. Schema changes need manual migration or DB wipe.
- **Default admin**: `admin` / `admin123` (seeded when users table is empty).
- **All UI text must be in English** (no Chinese in templates or flash messages).
- **CSRF token**: template uses `{{ csrf_token }}` (variable), form field name is `_csrf_token`.
- **Chart zoom**: Y-axis only (`mode: 'y'`). Drag to zoom, Shift+drag to pan, double-click to reset.

## Upload & import

- Session type auto-detected from CSV **filename** keywords (not path). Falls back to "Practice". Upload page allows manual override.
- TSL: comma-delimited, UTF-8-sig. Swiss: semicolon-delimited, Latin-1/UTF-8.
- `MAX_CONTENT_LENGTH = 16 MB` (config.py).
- On import: auto-computes `model_color`, detects best lap per car (min positive `lap_time`, excludes out_lap/in_lap/track_limit).

## Out lap / In lap / TLW detection

- `detect_out_laps()` — Marks each car's first Lap 1 as out_lap. For duplicate Lap 1, first one marked.
- `detect_in_laps()` — Heuristic: lap_time > 1.2x median of clean laps (excludes lap 1).
- PitStopsCsv overrides heuristic: sets `out_lap`/`in_lap` from CSV data.
- `apply_tlw()` — Matches TLW warnings to laps by `race_time` → `session_time` range.

## Color system

Server-side `model_to_color()` in routes.py replicates JS `getModelColor()` (Java string hash → COLORS array). **COLORS array must stay in sync** between `static/js/charts.js:4-7` and `routes.py:23-28`.

Two modes toggled by Color button: "By Car #" (`series_color`) and "By Model" (`model_color` from CarConfig/CarModelColor).

## Performance patterns

- **AJAX lazy loading**: Lap-by-lap and drivers tables load via AJAX endpoints (`/api/sessions/<id>/laps`, `/api/sessions/<id>/drivers`). JS builds rows client-side.
- **Event delegation**: AJAX-loaded tables use event delegation on container (`#driverCard`). Direct `querySelectorAll` on dynamic rows returns nothing.
- **`car_colors` in AJAX responses**: Include `car_colors` in API response and set `data-car-color` on `<tr>` — otherwise Color toggle button won't work.
- **Analytics cache**: 5-min in-memory cache (`_analytics_cache`, max 50 entries). Invalidated per-session or globally.
- **Chart.js decimation**: LTTB, max 200 samples per dataset, animations disabled >1000 points.
- **13 chart types** share one canvas; tab switching destroys/recreates Chart.js instance.

## Config & env

- `DATABASE_URL` env var overrides SQLite path or swaps to PostgreSQL (default: `sqlite:///instance/timing.db`).
- `SECRET_KEY` env var required in production. Dev mode generates random key per startup.
- Dev mode detected by absence of `DATABASE_URL` and `SECRET_KEY` env vars.
- Production `.env` is auto-generated at `DEPLOY_PATH/shared/.env` during deployment.

## Deployment

Push to `master` (or tag `v*` or manual dispatch) → GitHub Actions → Ubuntu server via SSH.
- Gunicorn port 8000, Nginx reverse-proxy, systemd
- `instance/` and `uploads/` symlinked to `/opt/race-timing/shared/` (persist across deploys)
- Base64-encoded SSH key stored in `DEPLOY_SSH_KEY` GitHub Secret
- See `DEPLOYMENT.md` for full setup.

## Existing instruction files

- `CLAUDE.md` — verbose route table + CSV column details (supersedes AGENTS.md detail)
- `REASONIX.md` — shorter summary
- `.github/copilot-instructions.md` — points back to this file


<!-- headroom:rtk-instructions -->
# RTK (Rust Token Killer) - Token-Optimized Commands

When running shell commands, **always prefix with `rtk`**. This reduces context
usage by 60-90% with zero behavior change. If rtk has no filter for a command,
it passes through unchanged — so it is always safe to use.

## Key Commands
```bash
# Git (59-80% savings)
rtk git status          rtk git diff            rtk git log

# Files & Search (60-75% savings)
rtk ls <path>           rtk read <file>         rtk grep <pattern>
rtk find <pattern>      rtk diff <file>

# Test (90-99% savings) — shows failures only
rtk pytest tests/       rtk cargo test          rtk test <cmd>

# Build & Lint (80-90% savings) — shows errors only
rtk tsc                 rtk lint                rtk cargo build
rtk prettier --check    rtk mypy                rtk ruff check

# Analysis (70-90% savings)
rtk err <cmd>           rtk log <file>          rtk json <file>
rtk summary <cmd>       rtk deps                rtk env

# GitHub (26-87% savings)
rtk gh pr view <n>      rtk gh run list         rtk gh issue list

# Infrastructure (85% savings)
rtk docker ps           rtk kubectl get         rtk docker logs <c>

# Package managers (70-90% savings)
rtk pip list            rtk pnpm install        rtk npm run <script>
```

## Rules
- In command chains, prefix each segment: `rtk git add . && rtk git commit -m "msg"`
- For debugging, use raw command without rtk prefix
- `rtk proxy <cmd>` runs command without filtering but tracks usage
<!-- /headroom:rtk-instructions -->
