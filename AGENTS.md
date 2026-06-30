# AGENTS.md

Flask app for importing race timing CSV files, storing lap/standing data in SQLite, and rendering server-side analysis pages with interactive charts. Deployed on Ubuntu + Nginx + systemd + Gunicorn.

## Commands

```bash
pip install -r requirements.txt         # Flask + Flask-SQLAlchemy only
python run.py                            # dev: http://localhost:5000, debug, 0.0.0.0
rm instance/timing.db && python run.py   # fresh DB + seed (admin/admin123)
python -m unittest discover -s tests     # all tests
python -m unittest tests.test_standings_sorting  # single test file
python -m unittest tests.test_standings_sorting.TestName.test_method  # single test
```

## Architecture

- **app.py** — `create_app()` factory; runs `db.create_all()` then inline `ALTER TABLE` migrations via `_ensure_*()` functions. CSRF protection on all POST (skips `/api/`). Context processor injects `current_user` + `csrf_token`.
- **models.py** — `User`, `TimeKeeper`, `Event`, `Session`, `Standing`, `LapRecord`, `CarConfig` (event-level car display config), `CarModelColor` (global model→color mapping).
- **routes.py** — All routes in a single `Blueprint("main")`. Key sections: auth, event CRUD, upload CSV, session detail (5 inline views), analytics API, car config editor (event-level + global model colors). Server-side `model_to_color()` replicates JS `getModelColor()`.
- **parsers/** — `BaseParser` ABC with `parse(**kwargs)` returning `{session_name, session_type, laps[], standings[]}`. Two parsers: `TSLTimingParser` (2-file CSV pair) and `SwissTimingParser` (up to 5 files). Registered in `PARSER_REGISTRY` dict.
- **templates/** — 16 Jinja2 templates, no frontend build step. CDN deps: Tailwind CSS, Chart.js 4.4.7 + chartjs-plugin-zoom 2.0.1, Lucide icons, JetBrains Mono + Syne fonts.
- **static/** — `css/theme.css` (light/dark CSS vars), `js/theme.js` (localStorage theme toggle), `js/charts.js` (Chart.js rendering for 13 chart types), `js/table-sort.js` (client-side column sorting).

## Database models — key fields beyond basic

- **Standing**: `gap_text`/`diff_text` (String, stores raw CSV strings like "1 Lap"), `car_model`/`series_color`/`model_color` (color system).
- **CarConfig**: event-level overrides for `car_model`, `series_color`, `model_color`, `team_name`, `class_name`. One row per `(event_id, car_number)`.
- **CarModelColor**: global `car_model` → `model_color` mapping, used by "By Model" chart mode across all events.
- **LapRecord**: `session_time` is Float (seconds from session start), not datetime. Used as chart X-axis. Also stores `time_in_lap`/`time_out_lap` for pit stop calculation.

## Color system (By Model / By Car #)

Priority for chart colors (`getCarColor()` in charts.js):
- **By Car # mode**: `series_color` (per-car override) → car number hash into COLORS array
- **By Model mode**: `model_color` (from standings/CarConfig, overridden by global `CarModelColor` table) → model name hash fallback

Server-side `model_to_color()` in routes.py replicates JS `getModelColor()` (Java string hash → COLORS array index). **The COLORS array must stay in sync** between `static/js/charts.js` and `routes.py`.

Three levels of row/cell highlighting:
- **bg-purple** (`--highlight-overall-bg`, 70% opacity): best across all cars (overall best lap/sector)
- **bg-green** (`--highlight-car-bg`, 70% opacity): per-car best
- **bg-orange** (`--highlight-stint-bg`, 70% opacity): per-stint best (between pit stops/driver changes)

## Session detail page — 5 inline views

1. **Classification** — standings table with class filter, car model color toggle (Color button, click/dbl-click rows), raw gap_text/diff_text shown when available
2. **Lap Summary** — best lap per car, same Color toggle with `data-car-color`
3. **Lap-by-Lap** — every lap, pit-in/out coloring, three-level best highlighting (purple/green/orange), per-car filter, per-stint bests
4. **Drivers** — per-driver analysis with theoretical lap (best S1+S2+S3), overall best sector highlight
5. **Chart** — 13 chart sub-types in toggleable checkboxes:
   - lapTime, delta, sector, speed, boxPlot, pitStops, position (Race only), driverS1, driverS2, driverS3, driverLap, consistency, strategy
   - All charts share a single `<canvas>` — switching destroys/recreates the Chart.js instance
   - Y-axis drag-to-zoom, Shift+drag to pan, double-click to reset (chartjs-plugin-zoom)

Table row color toggle: Color button master ON/OFF. Single click (ON) or double-click (OFF, 350ms timer) toggles individual row color via `--row-car-color` CSS variable.

## Upload & import

- Accepts up to 5 CSV files per session (sector, classification, pitstops, TLW, messages). Parser-specific file inputs shown dynamically.
- `MAX_CONTENT_LENGTH = 16 * 1024 * 1024` (16 MB) set in `config.py`.
- On import: auto-computes `model_color = model_to_color(car_model)`. If `car_model` is empty, falls back to sibling events (same championship + year) from CarConfig or Standing.
- Best lap detection: computed per car during import — min positive `lap_time` → `is_best=True`.
- Session type auto-detected from CSV **filename** keywords (not path):
  - `paid test|paidtest|paid_test` → Paid-Test
  - `practice|free practice|fp` → Practice
  - `bronze session|bronzesession|bronze_session` → Bronze-Session
  - `pre-qualifying|prequalifying|pre-qual|prequal` → Pre-Qualifying
  - `qualifying|qual|qualification|q` → Qualifying
  - `warm-up|warmup|warm_up` → Warm-up
  - `race|r` → Race
  - Falls back to "Practice". Upload page allows manual override.
- Standings sorted by position ASC with NC cars (pos=0) below classified, sorted by laps DESC.

## Conventions

- stdlib `csv` module only — no pandas, no frontend build pipeline.
- One import per line, order: stdlib → Flask → local modules.
- `unittest.TestCase` (not pytest). Each test creates its own temp DB via `create_app(config_override)`.
- Default admin: `admin` / `admin123` (seeded on first boot, never hardcode in templates).
- No DB migration framework — `db.create_all()` + inline `ALTER TABLE` on startup. Schema changes require manual migration or DB wipe.
- `session_time` is Float (seconds from session start), not datetime. Used as chart X-axis.
- Chart zoom: Y-axis only (`mode: 'y'`). Drag to zoom, Shift+drag to pan, double-click to reset.
- Analytics API has 5-minute in-memory cache (`_analytics_cache`, max 50 entries). Invalidated per-session or all at once via `_invalidate_all_analytics_caches()`.
- Safety car detection: laps exceeding 1.35× the car's median clean lap time are flagged as `sc_lap: true` in the analytics API. Lap Times chart filters these out.

## Deployment

Push to `master` auto-deploys via GitHub Actions. See `DEPLOYMENT.md` for full setup.
- Production: Gunicorn on port 8000, Nginx reverse proxy, systemd service
- Shared dirs: `instance/` and `uploads/` are symlinked to `/opt/race-timing/shared/`
- `SECRET_KEY` auto-generated on first deploy, stored in `/opt/race-timing/shared/.env`

## Utility scripts

- `scripts/repair_swiss_timing_driver_names.py` — re-parses Swiss Timing uploads to fix driver names and pit in/out flags
- `scripts/build_release.sh` — builds release tarball for deployment
- `scripts/deploy.sh` — manual deploy via SSH (requires `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_PATH` env vars)
