# AGENTS.md

This repository is a Flask-based race timing analysis app for importing timing CSV files, storing lap/standing data in SQLite, and rendering server-side views.

## What matters most
- The app is centered around events, sessions, laps, and standings in [models.py](models.py).
- Parsers live in [parsers/](parsers/) and must return a normalized payload with session metadata, laps, and standings.
- Routes and templates in [routes.py](routes.py) and [templates/](templates/) render the UI; keep changes aligned with the existing server-rendered approach.
- Existing project guidance is in [CLAUDE.md](CLAUDE.md); prefer that file for deeper domain context.

## Working conventions
- Use Python 3 and keep changes compatible with the current Flask/SQLAlchemy setup.
- Prefer the standard library for CSV parsing; avoid introducing pandas or a frontend build step.
- When adding a new parser, subclass the base parser in [parsers/base.py](parsers/base.py) and register it in [parsers/__init__.py](parsers/__init__.py).
- When changing import or display logic, keep lap-level fields consistent: lap_time, driver_name, out_lap, in_lap, sector values, and session_time.
- Add or update tests under [tests/](tests/) for parser or display behavior changes.

## Commands
- Install dependencies: `pip install -r requirements.txt`
- Run the app: `python run.py`
- Run tests: `python -m unittest discover -s tests`
- Reset local DB if needed: `rm instance/timing.db && python run.py`

## Notes for agents
- Do not assume a build pipeline exists; this project is intentionally simple and template-driven.
- UI changes should remain consistent with the existing Tailwind CDN and Jinja templates.
- Be careful with database migrations or schema changes: this app currently relies on creating tables from models at startup.
