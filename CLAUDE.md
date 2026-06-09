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
| `GET /api/sessions/<id>/laps` | JSON API for lap data (includes session_time) |
| `GET /api/sessions/<id>/analytics` | Pre-computed stats: per-car (min/Q1/median/Q3/max for box plots, best sectors, top speed), all lap times, pit stops, position progression |

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
5. **Chart** — 7 tabbed sub-views within the chart card:
   - **Lap Times** — line chart per car, session-best dashed reference line, out/in laps excluded
   - **Delta** — gap to session best lap per car, by lap number
   - **Sectors** — stacked bar of best S1+S2+S3 (=theoretical) per car, line overlay of actual best
   - **Speed** — horizontal bar of top speed trap per car
   - **Box Plot** — manual stacked-bar: min→Q1→median→Q3→max per car, colored IQR box + gray whiskers
   - **Pit Stops** — horizontal bar of each pit lane time (= out_lap_time − median_clean_lap_time)
   - **Position** — lap-by-lap position progression (Race only, hidden for Practice/Qualifying)

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

### Charts & Analytics API

`GET /api/sessions/<id>/analytics` returns pre-computed data for all charts in a single request:

| Field | Content |
|---|---|
| `per_car` | Per-car stats: best_lap, best_s1/s2/s3, theoretical, top_speed, avg_lap, min_lap, q1, median, q3, max_lap |
| `lap_times` | All valid laps with car_number, lap_number, lap_time, sectors, session_time, out_lap/in_lap flags |
| `overall_best_lap` | Fastest lap time across all cars (for delta reference) |
| `pit_stops` | List of `{car_number, driver_name, in_lap, out_lap, pit_time}` — pit_time = out_lap_time − car's median clean lap time |
| `position_progression` | (Race only) Per-lap position per car, computed by sorting by session_time at each lap number |

Chart JS uses a single `<canvas id="analysisChart">` element — each render function destroys the previous Chart.js instance and creates a new one. All chart data is cached client-side after the first API fetch. Consistent car color palette across all 7 chart types.

Pit stop detection: pairs consecutive in_lap→out_lap transitions within a car's sorted laps.

## Key design decisions

- **No pandas** — stdlib `csv` module handles all parsing, avoiding C compiler dependency on Windows
- **Dual CSV upload** — TSL Timing requires two files. Upload page shows both file inputs when `tsl_timing` is selected; either can be empty
- **Best lap detection** — computed per car during import: min positive `lap_time` → `is_best=True`
- **Pit stop time** — computed as `out_lap_time − median_clean_lap_time` per car (clean = not in/out lap); referenced from median to avoid outlier skew
- **All views inline** — all 5 session views are rendered in a single page and toggled via JS `showView()`, avoiding extra HTTP requests
- **Chart tabs** — 7 chart sub-types share one canvas; tab switching destroys/recreates the Chart.js instance
- **SQLite by default** — swap to PostgreSQL by changing `DATABASE_URL` env var in `config.py`
