# REASONIX.md

Race timing analysis web app — upload time-keeper CSV files, parse into SQLite, view server-rendered analysis pages with interactive charts. Deployed on Ubuntu + Nginx + systemd + Gunicorn (port 8000).

## Stack

- Python 3.12 + **Flask 3.1** + **Flask-SQLAlchemy 3.1.1** + **SQLite** (PostgreSQL via `DATABASE_URL` env var)
- **Jinja2** server-rendered templates + **Tailwind CSS** (CDN, no build step)
- **Chart.js 4.4.7** + **chartjs-plugin-zoom 2.0.1** for interactive charts
- **Werkzeug** password hashing, **Lucide** icons via CDN
- **Gunicorn 23.0** for production deployment
- No pandas — stdlib `csv` module only

## Layout

| Path | Purpose |
|---|---|
| `app.py` | Flask app factory: `create_app()`, inline `ALTER TABLE` migrations, CSRF protection, admin seeding |
| `run.py` | Entrypoint — `python run.py` starts dev server on `0.0.0.0:5000` |
| `config.py` | Config — `DATABASE_URL` env var overrides SQLite path |
| `models.py` | SQLAlchemy models: User, Event, Session, LapRecord, Standing, CarConfig, CarModelColor, TimeKeeper |
| `routes.py` | Single Flask Blueprint: all auth, CRUD, upload, session detail, analytics API routes |
| `parsers/` | Pluggable CSV parser system — `BaseParser` ABC, `PARSER_REGISTRY` dict. Two parsers: `TSLTimingParser` (2-file pair) and `SwissTimingParser` (up to 5 files) |
| `templates/` | 16 Jinja2 templates, all server-rendered |
| `static/css/` | `theme.css` — light/dark CSS custom properties |
| `static/js/` | `charts.js` (Chart.js rendering for 13+ chart types), `table-sort.js` (client-side column sorting), `theme.js` (localStorage theme toggle) |
| `tests/` | 7 `unittest.TestCase` files — no pytest |
| `deploy/` | Nginx reverse-proxy config + systemd unit |
| `uploads/` | Uploaded CSVs (gitignored) |
| `instance/` | SQLite DB file location (gitignored) |
| `.reasonix/skills/` | `frontend-design.md` — project-specific skill for Tailwind/layout guidance |

## Commands

```bash
pip install -r requirements.txt
python run.py                          # dev server, debug mode, 0.0.0.0:5000
rm instance/timing.db && python run.py # fresh DB + seed (admin/admin123)
python -m unittest discover tests/     # run all tests
gunicorn --bind 127.0.0.1:8000 --workers 2 "app:create_app()"  # production (see deploy/)
```

## Architecture

- **Data flow**: CSV upload → Parser → dict → Flask route → SQLAlchemy → SQLite → Jinja2 template → HTML page
- **Session detail page** has 5 inline-switchable views (no page navigation): Classification, Lap Summary, Lap-by-Lap, Drivers, Chart (13+ sub-types in toggleable checkboxes)
- **Analytics API** (`GET /api/sessions/<id>/analytics`) returns pre-computed data for all charts. 5-minute in-memory cache (`_analytics_cache`, max 50 entries)
- **Color system**: two modes toggled by "Color" button — By Car # (uses `series_color` / car number hash) and By Model (uses `model_color` from CarConfig/CarModelColor). Server-side `model_to_color()` replicates JS `getModelColor()` (Java string hash)
- **Three-level best highlighting** in Lap-by-Lap view: purple (overall best across all cars), green (per-car best), orange (per-stint best between pit stops/driver changes)
- **Safety car detection**: laps > 1.35× median clean lap time flagged as `sc_lap`
- **Session type auto-detection** from CSV filename keywords: Paid-Test → Practice → Bronze-Session → Pre-Qualifying → Qualifying → Warm-up → Race. Falls back to Practice.

## Conventions

- **Tests**: `unittest.TestCase` (not pytest). Each test creates its own temp DB via `app.create_app(config_override)`. No fixtures.
- **Parser system**: subclass `BaseParser` (name, description, `parse()`, `detect()`), register in `parsers/__init__.py` `PARSER_REGISTRY`.
- **Admin auth**: `User.is_admin` boolean, `@admin_required` decorator. Default: `admin` / `admin123`.
- **Imports**: stdlib → Flask → local modules, one import per line, no `__init__.py` re-exports.
- **No DB migrations**: `db.create_all()` on every startup + inline `ALTER TABLE` in `app.py` (`_ensure_*()` functions). Schema changes require manual migration or DB wipe.
- **`session_time` is a Float**: seconds from session start, not datetime. Used as chart X-axis.
- **Chart zoom**: Y-axis only (`mode: 'y'`). Drag to zoom, Shift+drag to pan, double-click to reset.
- **Theme**: light/dark via CSS custom properties on `[data-theme]` + `localStorage('race-timing-theme')`. Chart colors read from CSS vars at runtime to avoid redraw.
- **CSRF**: all POST routes require `_csrf_token` (skips `/api/`). `current_user` injected into all templates via `app.context_processor`.
- **Upload**: up to 5 CSV files per session. Parser-specific file inputs shown dynamically. On import: auto-computes `model_color`, detects best lap per car, copies `car_model`/colors to lap_records and standings.

## Notes

