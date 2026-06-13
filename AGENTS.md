# AGENTS.md

Flask app for importing race timing CSV files, storing lap/standing data in SQLite, and rendering server-side analysis pages. Deployed on a remote Ubuntu server with Nginx + systemd + Gunicorn.

## Commands

```bash
pip install -r requirements.txt       # install deps (Flask + Flask-SQLAlchemy only)
python run.py                          # http://localhost:5000, debug mode, binds 0.0.0.0
python -m unittest discover -s tests   # run all tests
python -m unittest tests.test_standings_sorting   # single test module
del instance\timing.db && python run.py           # fresh start (Windows)
rm instance/timing.db && python run.py            # fresh start (Linux)
```

## Architecture

- **models.py** — Event, Session, LapRecord, Standing, User, TimeKeeper. Tables auto-created from models at startup; no migration framework.
- **parsers/** — CSV parsers inheriting from `parsers/base.py`. Register new parsers in `parsers/__init__.py` `PARSER_REGISTRY`.
- **routes.py** — All routes; upload endpoint shows parser-specific file inputs dynamically.
- **templates/** — Server-rendered Jinja2 + Tailwind CSS CDN + Chart.js CDN. No frontend build step.
- **static/** — `theme.css` (light/dark CSS vars), `theme.js` (localStorage toggle), `charts.js` (Chart.js rendering for all 7 chart types), `table-sort.js` (client-side column sorting).
- **app.py** — `create_app()` factory; runs inline `ALTER TABLE` migrations via `_ensure_*()` functions on first boot (`_ensure_session_sort_order_column`, `_ensure_lap_record_time_columns`, `_ensure_car_model_columns`).

## Key conventions

- Python 3, stdlib `csv` module only — do not add pandas or a frontend build pipeline.
- Preserve normalized fields: `lap_time`, `driver_name`, `out_lap`, `in_lap`, sector values, `session_time`.
- Parser changes that affect import must update downstream display logic and tests.
- Prefer small, targeted changes over architectural rewrites.
- Admin-only routes: event CRUD, upload, session reorder/delete, user registration.
- Default admin: `admin` / `admin123` (seeded on first run, never hardcode in templates).
- Upload accepts up to 5 CSV files per session; which inputs appear is parser-specific.
- Session detail has 5 inline views (Classification, Lap Summary, Lap-by-Lap, Drivers, Chart) toggled by buttons — no page navigation.

## Adding a parser

1. Subclass `BaseParser` (implements `name`, `description`, `parse(**kwargs)`, `detect(filepath)`)
2. `parse()` returns `{session_name, session_type, laps[], standings[]}`
3. Register an instance in `PARSER_REGISTRY` in `parsers/__init__.py`

## Deployment

- Push to main triggers `.github/workflows/deploy.yml` (build + deploy to remote)
- Production: Ubuntu + Nginx reverse proxy → Gunicorn on 127.0.0.1:8000
- Configs in `deploy/` (systemd service, Nginx conf)
- Docker: `Dockerfile` builds Python 3.12-slim image
- `scripts/` — `build_release.sh` (tar.gz archive), `deploy.sh` (SSH push + remote install), `repair_swiss_timing_driver_names.py` (data repair utility)
