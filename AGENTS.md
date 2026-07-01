# AGENTS.md

Flask app for importing race timing CSV files, storing lap/standing data in SQLite, and rendering server-side analysis pages with interactive charts. Deployed on Ubuntu + Nginx + systemd + Gunicorn.

## Commands

```bash
pip install -r requirements.txt         # Flask + Flask-SQLAlchemy only
python run.py                            # dev: http://localhost:5000, debug, 0.0.0.0
rm instance/timing.db && python run.py   # fresh DB + seed (admin/admin123)
python -m unittest discover -s tests     # all tests (~32)
python -m unittest tests.test_standings_sorting  # single test file
python -m unittest tests.test_standings_sorting.TestName.test_method  # single test
```

## Architecture

- **app.py** — `create_app()` factory; runs `db.create_all()` then inline `ALTER TABLE` migrations via `_ensure_*()` functions. CSRF protection on all POST (skips `/api/`). Context processor injects `current_user` + `csrf_token`.
- **models.py** — `User`, `TimeKeeper`, `Event`, `Session`, `Standing`, `LapRecord`, `CarConfig`, `CarModelColor`.
- **routes.py** — All routes in a single `Blueprint("main")`. Auth, event CRUD, upload CSV, session detail (5 views), analytics API, car config editor, admin refresh flags, CSV reupload.
- **parsers/** — `BaseParser` ABC. Two parsers: `TSLTimingParser` (2-file CSV) and `SwissTimingParser` (up to 5 files). `detect_laps.py` — standalone functions for out_lap/in_lap/TLW detection, reused by parser and admin refresh.
- **templates/** — 18 Jinja2 templates, no frontend build. CDN: Tailwind CSS, Chart.js 4.4, Lucide icons.
- **static/** — `css/theme.css` (light/dark), `js/theme.js`, `js/charts.js` (13 chart types), `js/table-sort.js`.

## Key fields on LapRecord

- `session_time` — Float, seconds from session start (not datetime). Used as chart X-axis.
- `out_lap` — True for each car's first Lap 1, plus pitstop-derived out laps from PitStopsCsv.
- `in_lap` — Heuristic (>1.2x median) or from PitStopsCsv.
- `track_limit` — Set by TLW CSV matching (race_time → session_time range).
- `is_best` — Computed during import; excludes out_lap, in_lap, track_limit laps.

## Out lap / In lap detection (`parsers/detect_laps.py`)

- `detect_out_laps()` — Marks each car's first Lap 1 as out_lap. For duplicate Lap 1 entries, first one is marked.
- `detect_in_laps()` — Heuristic: lap_time > 1.2x median of clean laps (excludes lap 1).
- `apply_tlw()` — Matches TLW warnings to laps by session_time range, sets track_limit.
- `parse_tlw_file()` — Parses TLW CSV (semicolon-delimited).

## Sector best exclusion rules

- S1 best: excludes out_lap laps
- S2 best: no exclusion
- S3 best: excludes in_lap laps
- Fastest lap: excludes out_lap, in_lap, track_limit laps

## Admin features (session detail page)

- **Refresh button** — Marks each car's Lap 1 as out_lap. Preserves existing pitstop-derived flags.
- **Re-upload CSV** — `/sessions/<id>/reupload`. Supports sector, classification, pitstops, TLW. Sector/classification replace all records; pitstops/TLW update flags.
- **Delete** — Removes session and all related data.

## Upload & import

- Swiss Timing: up to 5 CSV files (sector, classification, pitstops, TLW, messages). Semicolon-delimited.
- TSL Timing: 2 CSV files (sector, classification). Comma-delimited.
- `MAX_CONTENT_LENGTH = 16 MB` (config.py).
- Session type auto-detected from CSV **filename** keywords (not path).
- Best lap: min positive `lap_time` per car, excluding out_lap/in_lap/track_limit.

## Conventions

- stdlib `csv` only — no pandas, no frontend build pipeline.
- `unittest.TestCase` (not pytest). Each test creates its own temp DB.
- Default admin: `admin` / `admin123` (seeded on first boot).
- No DB migration framework — `db.create_all()` + inline `ALTER TABLE`.
- All UI text must be in English (no Chinese in templates or flash messages).
- CSRF token: template uses `{{ csrf_token }}` (variable), form field name is `_csrf_token`.

## Color system

Server-side `model_to_color()` replicates JS `getCarColor()` (Java string hash → COLORS array). **COLORS array must stay in sync** between `static/js/charts.js` and `routes.py`.

## Deployment

Push to `master` auto-deploys via GitHub Actions. See `DEPLOYMENT.md`.
- Production: Gunicorn port 8000, Nginx reverse proxy, systemd
- Shared dirs: `instance/` and `uploads/` symlinked to `/opt/race-timing/shared/`
