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
- Do not assume database migrations exist; tables are created from the models at startup.

## Commands
- Install dependencies: `pip install -r requirements.txt`
- Run the app: `python run.py`
- Run tests: `python -m unittest discover -s tests`
- Reset the local database if needed: `rm instance/timing.db && python run.py`

## Agent guidance
- Keep UI changes consistent with the existing server-rendered Tailwind/Jinja approach.
- If a parser change affects import behavior, verify the downstream display logic and tests that depend on the normalized payload.
- Prefer small, targeted changes over architectural rewrites.
