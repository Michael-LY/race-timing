# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Race timing analysis web app (like HH Timing) deployed on a server with browser-based access. Users upload time-keeper CSV files which are parsed and stored in SQLite. An event contains multiple sessions (Practice, Qualifying, Race).

**Tech stack:** Python Flask + SQLAlchemy + SQLite + Bootstrap 5 + Chart.js. No frontend build step — server-rendered Jinja2 templates with CDN assets.

## Commands

```bash
# Install (only Flask + Flask-SQLAlchemy needed — CSV parsing uses stdlib `csv`)
pip install -r requirements.txt

# Run dev server
python run.py          # http://localhost:5000, debug=True, binds 0.0.0.0

# Delete all data and start fresh
rm instance/timing.db && python run.py
```

No tests, linters, or formatters configured yet.

## Architecture

### Data flow
```
CSV upload → Parser → dict → Flask route → SQLAlchemy models → SQLite
                                              ↓
                                       Jinja2 template → HTML page
```

### Database models (`models.py`)

- **Event** — name, track, event_date; linked to a TimeKeeper; has many Sessions
- **Session** — belongs to Event; type is one of `Practice|Qualifying|Race`; has many LapRecords and many Standings
- **Standing** — per-car classification result from Classification CSV (position, gap, fastest_lap, pit_stops, is_classified for DNF/NC)
- **LapRecord** — single lap. Fields: car_number, driver_name, lap_number, lap_time, sector_1/2/3, speed_trap_1-4, time_of_day, session_time, out_lap/in_lap booleans, is_best flag
- **TimeKeeper** — registered parser formats, seeded from `PARSER_REGISTRY` on first run

### Parser system (`parsers/`)

`BaseParser` (ABC) defines three required members: `name` (str), `description` (str), `parse(filepath) -> dict`.

The only active parser is **TSLTimingParser** (`parsers/tsl.py`) — handles the TSL Timing CSV pair used by GTWC Asia:

| CSV file | Key columns |
|---|---|
| Classification | Pos, No., Name, Class, Nationality, Total Time, Gap, Diff, Laps, Fastest Lap, Fast Lap No., Pit Stops |
| Sector Analysis | nr, lapnumber, laptime, sector_1/2/3_time, speedTrap_1-4_Speed, out_lap, in_lap, time_of_day, session_time, driver_name |

`parse()` accepts both files as keyword arguments: `parse(classification_path=..., sector_path=...)`. Either can be omitted (e.g. practice sessions may only have sector data).

To add a new time keeper: subclass `BaseParser`, implement `parse()` returning `{session_name, session_type, laps[], standings[]}`, register in `parsers/__init__.py` `PARSER_REGISTRY`.

### Routes (`routes.py`)

| Route | Purpose |
|---|---|
| `GET /` | Event list |
| `GET/POST /events/new` | Create event |
| `GET /events/<id>` | Event detail with session list |
| `GET/POST /events/<id>/upload` | Upload CSV(s) — dual file inputs for TSL |
| `GET /sessions/<id>` | Session detail (classification + lap summary + lap-by-lap + chart) |
| `GET /api/sessions/<id>/laps` | JSON API for Chart.js consumption |

### Templates

Server-rendered Jinja2 with Bootstrap 5 CDN. Session detail page has four switchable views: Classification standings table, Lap summary (best lap per car), Lap-by-lap table (with pit in/out highlighting), and a Chart.js line graph of lap times.

### Session type auto-detection

Parsers detect session type from the CSV **filename** (not full path) by matching keywords:
- `practice|free practice|fp` → Practice
- `qualifying|qual|qualification` → Qualifying
- `race` → Race
Falls back to "Practice".

## Key design decisions

- **No pandas** — the stdlib `csv` module handles all parsing to avoid C compiler dependency issues on Windows
- **Dual CSV upload** — TSL Timing requires two separate files. The upload page shows both file inputs when `tsl_timing` is selected; either can be empty
- **Best lap detection** — computed per car during import by scanning all laps and taking the minimum positive `lap_time`; stored as boolean `is_best` on LapRecord
- **SQLite by default** — database URI in `config.py`, easily swapped to PostgreSQL by changing the environment variable
