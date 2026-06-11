# REASONIX.md

## Stack

- **Python 3.12** + **Flask 3.1** + **Flask-SQLAlchemy 3.1** + **SQLite**
- **Jinja2** server-rendered templates with **Tailwind CSS** (CDN, no build step)
- **Chart.js 4.4.7** + **chartjs-plugin-zoom 2.0.1** for interactive charts
- **Werkzeug** for password hashing, **lucide** icons via CDN

## Layout

| Path | Purpose |
|---|---|
| `app.py` | Flask app factory, `create_app()`, admin seeding |
| `run.py` | Entrypoint — `python run.py` starts dev server on `0.0.0.0:5000` |
| `config.py` | Config — `DATABASE_URL` env var overrides SQLite path |
| `models.py` | SQLAlchemy models: User, Event, Session, LapRecord, Standing, TimeKeeper |
| `routes.py` | Flask blueprint: all routes + 2 chart APIs (`/api/sessions/<id>/laps|analytics`) |
| `parsers/` | Pluggable CSV parser system — `BaseParser` ABC, `PARSER_REGISTRY` dict |
| `templates/` | 11 Jinja2 templates + inline JS for chart rendering |
| `static/` | `theme.css` (light/dark CSS vars) + `theme.js` (localStorage toggle) |
| `tests/` | 7 `unittest.TestCase` files — no pytest config |
| `deploy/` | Nginx reverse-proxy config + systemd unit (gunicorn on port 8000) |
| `uploads/` | Uploaded CSVs (gitignored) |
| `instance/` | SQLite DB file location (gitignored) |

## Commands

```bash
pip install -r requirements.txt
python run.py                          # dev server, debug mode, 0.0.0.0:5000
rm instance/timing.db && python run.py # fresh DB seed (admin/admin123)
python -m unittest discover tests/     # run all tests
```

## Conventions

- **Tests**: `unittest.TestCase` (not pytest). Each test file creates its own temp DB via `app.create_app(config_override)`. No fixtures.
- **Parser system**: subclass `BaseParser` (name, description, `parse()`, `detect()`), register in `parsers/__init__.py` `PARSER_REGISTRY`.
- **Session type detection**: matched from CSV filename keywords — ordering: Paid Test → Practice → Bronze Session → Pre-Qualifying → Qualifying → Warm-up → Race. Falls back to Practice.
- **Theme**: light/dark via CSS custom properties on `[data-theme]` + `localStorage('race-timing-theme')`. Chart colors read from CSS vars at runtime.
- **Charts**: single `<canvas id="analysisChart">` (now per-type panels), instances destroyed/recreated on tab switch or theme toggle.
- **Admin auth**: `User.is_admin` boolean, `@admin_required` decorator on routes. Default: `admin` / `admin123`.
- **Imports**: stdlib → Flask → local modules, one import per line, no `__init__.py` re-exports.

## Watch out for

- **No DB migrations** — `db.create_all()` runs on every startup. Schema changes require manual `ALTER TABLE` or DB wipe.
- **`session_time` is a Float** (seconds from session start), not a datetime. Used as chart X-axis for Lap Times / Delta views (displayed in minutes).
- **Chart zoom**: Y-axis only (`mode: 'y'`). Left-drag to select range, Shift+drag to pan, double-click to reset.
- **Pit stop driver labels**: out-driver is inferred by matching `car_number + out_lap` in `lap_times` — only works if the CSV pair includes driver names in both classification and sector analysis.
