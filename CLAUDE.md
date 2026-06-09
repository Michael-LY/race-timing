# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Race timing analysis web app (like HH Timing) deployed on a server with browser-based access. Users upload time-keeper CSV files which are parsed and stored in SQLite. An event contains multiple sessions (Practice, Qualifying, Race).

**Tech stack:** Python Flask + SQLAlchemy + SQLite + Bootstrap 5 + Chart.js. No frontend build step — server-rendered Jinja2 templates with CDN assets.

## Commands

```bash
pip install -r requirements.txt   # Flask + Flask-SQLAlchemy only
python run.py                      # http://localhost:5000, debug=True, binds 0.0.0.0
rm instance/timing.db && python run.py   # fresh start
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
- **Session** — belongs to Event; type is `Practice|Qualifying|Race`; has many LapRecords and many Standings
- **Standing** — per-car classification result: position, team_name, class_name, nationality, total_time, gap, diff, laps_completed, fastest_lap, fastest_lap_no, fastest_lap_speed, pit_stops, is_classified
- **LapRecord** — single lap. Fields: car_number, driver_name, lap_number, lap_time, sector_1/2/3, speed_trap_1-4, time_of_day, session_time, out_lap/in_lap booleans, is_best flag
- **TimeKeeper** — registered parser formats, seeded from `PARSER_REGISTRY` on first run

### Parser system (`parsers/`)

`BaseParser` (ABC) requires: `name`, `description`, `parse()` returning `{session_name, session_type, laps[], standings[]}`, and `detect()`.

**TSLTimingParser** (`parsers/tsl.py`) — handles GTWC Asia TSL Timing CSV pair:

| CSV file | Key columns |
|---|---|
| Classification | Pos, No., Name, Class, Nationality, Total Time, Gap, Diff, Laps, Fastest Lap, Fast Lap No., Pit Stops |
| Sector Analysis | nr, lapnumber, laptime, sector_1/2/3_time, speedTrap_1-4_Speed, out_lap, in_lap, time_of_day, session_time, driver_name |

`parse()` accepts both files as keyword arguments: `parse(classification_path=..., sector_path=...)`. Either can be omitted.

To add a new time keeper: subclass `BaseParser`, register in `parsers/__init__.py` `PARSER_REGISTRY`.

### Routes (`routes.py`)

| Route | Purpose |
|---|---|
| `GET /` | Event list |
| `GET/POST /events/new` | Create event |
| `GET /events/<id>` | Event detail with session list |
| `GET/POST /events/<id>/upload` | Upload CSV(s) — dual file inputs for TSL |
| `GET /sessions/<id>` | Session detail — all 5 views rendered inline |
| `GET /sessions/<id>/drivers` | Standalone driver analysis page |
| `GET /api/sessions/<id>/laps` | JSON API for Chart.js |

The `session_detail` route computes via `_compute_session_stats()`:
- **overall** — best lap time, S1, S2, S3 across all cars (for purple highlight)
- **per_car_bests** — best S1, S2, S3 per car (for green highlight)
- **car_groups** — laps grouped by car_number
- **drivers** — driver analysis data (same computation as `/drivers` route)

### Templates

Server-rendered Jinja2 with Bootstrap 5 CDN. Session detail page (`session_detail.html`) has **5 inline-switchable views** toggled by buttons — no page navigation:

1. **Classification** — standings table, NC cars pushed below classified finishers with separator row
2. **Lap Summary** — best lap per car, sorted by lap time
3. **Lap-by-Lap** — every lap for every car; pit-in (yellow) / pit-out (blue) row coloring; per-car filter dropdown
4. **Drivers** — per-driver: laps, best lap, theoretical lap (best S1+S2+S3), gap to best; embedded inline (not a separate page load)
5. **Chart** — Chart.js line graph of lap times by car

### Visual highlighting

- **Purple background** (`bg-purple`) = overall best (fastest lap / S1 / S2 / S3 across all cars)
- **Green background** (`bg-green`) = per-car best (car's own best S1 / S2 / S3 / lap time)
- All best values are **bold**
- All three tables (Classification, Lap Summary, Lap-by-Lap, Drivers) support **click-to-sort** on column headers, with ▲/▼ indicators

### Session type auto-detection

Parsers detect session type from the CSV **filename** (not full path) by matching keywords:
- `practice|free practice|fp` → Practice
- `qualifying|qual|qualification` → Qualifying
- `race` → Race
Falls back to "Practice".

## Key design decisions

- **No pandas** — stdlib `csv` module handles all parsing, avoiding C compiler dependency on Windows
- **Dual CSV upload** — TSL Timing requires two files. Upload page shows both file inputs when `tsl_timing` is selected; either can be empty
- **Best lap detection** — computed per car during import: min positive `lap_time` → `is_best=True`
- **All views inline** — all 5 session views are rendered in a single page and toggled via JS `showView()`, avoiding extra HTTP requests
- **SQLite by default** — swap to PostgreSQL by changing `DATABASE_URL` env var in `config.py`
