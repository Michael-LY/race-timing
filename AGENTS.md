# AGENTS.md

This repository is a small Flask application for importing race timing CSV files, storing lap and standing data in SQLite, and rendering server-side analysis pages.

## What matters most
- Core domain models live in [models.py](models.py): Event, Session, LapRecord, Standing, User, and TimeKeeper.
- Parsers live in [parsers/](parsers/) and should inherit from [parsers/base.py](parsers/base.py); register new parsers in [parsers/__init__.py](parsers/__init__.py).
- The UI is server-rendered through [routes.py](routes.py) and [templates/](templates/) with Jinja2 and Tailwind CDN.
- For broader product context, see [CLAUDE.md](CLAUDE.md).

## Working conventions
- Use Python 3 and keep changes compatible with Flask + Flask-SQLAlchemy.
- Prefer the standard library CSV parser; avoid adding pandas or introducing a frontend build pipeline.
- Preserve the normalized lap and standing fields used across the app, especially lap_time, driver_name, out_lap, in_lap, sector values, and session_time.
- When changing import, parsing, or display behavior, add or update tests in [tests/](tests/).
- Do not assume database migrations exist; tables are created from the models at startup. Inline `ALTER TABLE` migrations live in [app.py](app.py) (`_ensure_*` functions) and run on first boot.

## Commands
- Install dependencies: `pip install -r requirements.txt`
- Run the app: `python run.py`
- Run tests: `python -m unittest discover -s tests`
- Run a single test: `python -m unittest tests.test_standings_sorting`
- Reset the local database if needed: `rm instance/timing.db && python run.py` (Windows: `del instance\timing.db && python run.py`)

## Agent guidance
- Keep UI changes consistent with the existing server-rendered Tailwind/Jinja approach.
- If a parser change affects import behavior, verify the downstream display logic and tests that depend on the normalized payload.
- Prefer small, targeted changes over architectural rewrites.
- New parsers: subclass `BaseParser`, implement `parse()` returning `{session_name, session_type, laps[], standings[]}`, then register the instance in `PARSER_REGISTRY` in [parsers/__init__.py](parsers/__init__.py).
- Default admin account seeded on first run: `admin` / `admin123` (do not hardcode credentials in templates or routes).
- Upload accepts up to 5 CSV files per session; which inputs appear is parser-specific. The upload route in [routes.py](routes.py) dynamically shows fields based on the selected parser.
