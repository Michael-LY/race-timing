# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Race timing analysis web app (like HH Timing) deployed on a server with browser-based access. Users upload time-keeper CSV files which are parsed and stored in SQLite. An event contains multiple sessions (Practice, Qualifying, Race).

**Tech stack:** Python Flask + SQLAlchemy + SQLite + Tailwind CSS (CDN) + Chart.js + chartjs-plugin-zoom (CDN). No frontend build step — server-rendered Jinja2 templates with CDN assets. Fonts: JetBrains Mono (data) + Syne (headings) via Google Fonts CDN. Icons via Lucide CDN.

## Commands

```bash
pip install -r requirements.txt           # Flask + Flask-SQLAlchemy only
python run.py                              # http://localhost:5000, debug=True, binds 0.0.0.0
rm instance/timing.db && python run.py     # fresh DB + seed (admin/admin123)
python -m unittest discover -s tests       # run all tests
python -m unittest tests.test_standings_sorting  # run single test file
python -m unittest tests.test_standings_sorting.TestName.test_method  # run single test
```

Tests use `unittest.TestCase` (not pytest). Each test creates its own temp DB via `app.create_app(config_override)`.

`config.py` sets `MAX_CONTENT_LENGTH = 16 * 1024 * 1024` (16 MB upload limit).

## Architecture

### Data flow
```
CSV upload → Parser → dict → Flask route → SQLAlchemy models → SQLite
                                              ↓
                                       Jinja2 template → HTML page
```

### Database models (`models.py`)

- **User** — authentication account. Fields: username (unique), password_hash (werkzeug pbkdf2), is_admin flag, created_at. Methods: `set_password()`, `check_password()`. Default admin seeded on first run: `admin` / `admin123`
- **Event** — name, track, year (Integer), championship (String), event_date, created_at; linked to a TimeKeeper; has many Sessions and CarConfigs
- **Session** — belongs to Event; type is `Paid-Test|Practice|Bronze-Session|Pre-Qualifying|Qualifying|Warm-up|Race` (hyphenated; `normalize_session_type()` in routes.py maps spaced forms); sort_order for drag-and-drop reordering; has many LapRecords and many Standings
- **Standing** — per-car classification result. Fields: position, car_number, team_name, class_name, nationality, total_time, gap, diff, gap_text, diff_text (String, stores raw CSV strings like "1 Lap"), laps_completed, fastest_lap, fastest_lap_no, fastest_lap_speed, pit_stops, is_classified, car_model, series_color, model_color. Standings ordered by position ASC at model level; route re-sorts to push pos=0 (NC) below classified with laps DESC
- **LapRecord** — single lap. Fields: car_number, driver_name, category, lap_number, lap_time, sector_1/2/3, gap, speed (general avg), speed_trap_1-4, time_of_day, session_time, out_lap/in_lap booleans, is_best flag, position, time_out_lap/time_in_lap (float timestamps for pit stop calculation), car_model, series_color, model_color
- **CarConfig** — event-level car display config (one row per car per event): car_number, car_model, series_color, model_color, team_name, class_name. Used for per-event overrides
- **CarModelColor** — global car_model → model_color mapping. Used by "By Model" chart mode across all events
- **TimeKeeper** — registered parser formats, seeded from `PARSER_REGISTRY` on first run

### Parser system (`parsers/`)

`BaseParser` (ABC) requires: `name`, `description`, `parse()` returning `{session_name, session_type, laps[], standings[]}`, and `detect()`.

**TSLTimingParser** (`parsers/tsl.py`) — handles GTWC Asia TSL Timing CSV pair:

| CSV file | Key columns |
|---|---|
| Classification | Pos, No., Name, Class, Nationality, Total Time, Gap, Diff, Laps, Fastest Lap, Fast Lap No., Pit Stops |
| Sector Analysis | nr, lapnumber, laptime, sector_1/2/3_time, speedTrap_1-4_Speed, out_lap, in_lap, time_of_day, session_time, driver_name, pos, class, time_out_lap, time_in_lap |

`parse()` accepts both files as keyword arguments: `parse(classification_path=..., sector_path=...)`. Either can be omitted. Comma-delimited, UTF-8-sig encoding.

**SwissTimingParser** (`parsers/swiss_timing.py`) — handles Swiss Timing CSV export with up to 5 files:

| CSV file | Key columns | Required |
|---|---|---|
| SectorListCSV | Nr, Laps, Sector times, Speed traps | Yes |
| ResultListCSV | Position, Car, Team, Class, Total Time, Gap, Laps | No |
| PitStopsCsv | Car, Driver, In/Out times | No |
| TLWlistMessage | Penalty/tow messages | No |
| MessageListCSV | Race control messages | No |

`parse()` accepts keyword args: `parse(sector_path=..., classification_path=..., pitstops_path=..., tlw_path=..., messages_path=...)`. Semicolon-delimited, Latin-1/UTF-8 encoding. Builds standings from lap data when no ResultListCSV is provided. Assigns driver names per-stint using PitStopsCsv data.

To add a new time keeper: subclass `BaseParser`, register in `parsers/__init__.py` `PARSER_REGISTRY`.

### Routes (`routes.py`)

| Route | Auth | Purpose |
|---|---|---|
| `GET/POST /login` | — | Login page |
| `GET /logout` | — | Logout (clears session) |
| `GET/POST /register` | admin | Register new user |
| `GET /` | — | Event list (with year/championship/track filter dropdowns) |
| `GET/POST /events/new` | admin | Create event |
| `GET /events/<id>` | — | Event detail with session list |
| `GET/POST /events/<id>/edit` | admin | Edit event name/track/year/championship/date |
| `POST /events/<id>/delete` | admin | Delete event (cascades to sessions) |
| `GET/POST /events/<id>/upload` | admin | Upload CSV(s) — up to 5 file inputs; parser-specific inputs shown dynamically |
| `POST /events/<id>/sessions/reorder` | admin | Drag-and-drop session reordering |
| `GET/POST /events/<id>/car-config` | admin | Per-event car config editor |
| `GET/POST /car-model-colors` | admin | Global car model color editor |
| `GET/POST /sessions/<id>/edit` | admin | Edit session name/type |
| `POST /sessions/<id>/delete` | admin | Delete session |
| `GET /sessions/<id>` | — | Session detail — all 5 views rendered inline |
| `GET /sessions/<id>/drivers` | — | Standalone driver analysis page |
| `GET /api/sessions/<id>/laps` | — | JSON API for lap data (includes session_time) |
| `GET /api/sessions/<id>/analytics` | — | Pre-computed stats for all charts |
| `POST /api/sessions/<id>/car-models` | admin | Batch update car models |

The `session_detail` route computes via `_compute_session_stats()` returning 4 items:
- **overall** — best lap time, S1, S2, S3 across all cars (for purple highlight)
- **per_car_bests** — best S1, S2, S3 per car (for green highlight)
- **car_groups** — laps grouped by car_number
- **stint_bests** — keyed by lap.id, each value is a dict `{lap, s1, s2, s3}` indicating whether that lap is the stint best for its metric (for orange highlight); a stint is a run of consecutive laps between pit stops/driver changes

Driver analysis data is computed separately in the `session_detail` route handler (not from `_compute_session_stats()`).

### Templates

Server-rendered Jinja2 with Tailwind CSS CDN. Session detail page (`session_detail.html`) has **5 inline-switchable views** toggled by buttons — no page navigation:

1. **Classification** — standings table, NC cars pushed below classified finishers with separator row; class filter dropdown and car highlight input field
2. **Lap Summary** — best lap per car, sorted by lap time
3. **Lap-by-Lap** — every lap for every car; pit-in (yellow) / pit-out (blue) row coloring; per-car filter dropdown; three-level highlighting (purple=overall best, green=car best, orange=stint best)
4. **Drivers** — per-driver: laps, best lap, theoretical lap (best S1+S2+S3), gap to best; embedded inline (not a separate page load)
5. **Chart** — 13 chart sub-types in toggleable checkboxes:
   - **Lap Times** — line chart per car, session-best dashed reference line, out/in laps and safety car laps excluded
   - **Delta** — gap to session best lap per car, by lap number
   - **Sectors** — stacked bar of best S1+S2+S3 (=theoretical) per car, line overlay of actual best
   - **Speed** — horizontal bar of top speed trap per car
   - **Box Plot** — manual stacked-bar: min→Q1→median→Q3→max per car, colored IQR box + gray whiskers
   - **Pit Stops** — horizontal bar of pit lane time per car (uses `time_out_lap - time_in_lap` raw timestamps when available)
   - **Position** — lap-by-lap position progression (Race only, hidden for Practice/Qualifying)
   - **Driver S1/S2/S3** — per-driver sector breakdowns
   - **Driver Lap** — lap time by driver
   - **Consistency** — lap time standard deviation
   - **Strategy** — stint map visualization

All charts support Y-axis drag-to-zoom, shift+drag to pan, and double-click to reset (via chartjs-plugin-zoom).

Event detail page (`event_detail.html`) supports client-side sort buttons (by Type, Name, Laps) and admin drag-and-drop session reordering.

### Visual highlighting

Three-level best highlighting in the Lap-by-Lap view:
- **Purple background** (`bg-purple`) = overall best (fastest lap / S1 / S2 / S3 across all cars)
- **Green background** (`bg-green`) = per-car best (car's own best S1 / S2 / S3 / lap time)
- **Orange background** (`bg-orange`) = per-stint best (best within a run of consecutive laps between pit stops/driver changes)

All best values are **bold**. All four tables (Classification, Lap Summary, Lap-by-Lap, Drivers) support **click-to-sort** on column headers, with ▲/▼ indicators. Client-side sorting logic is in `static/js/table-sort.js`.

### Color system (By Model / By Car #)

Two color modes toggled by a "Color" button on the session detail page:

- **By Car # mode**: `series_color` (per-car override) → car number hash into COLORS array
- **By Model mode**: `model_color` (from standings/CarConfig, overridden by global CarModelColor table) → model name hash fallback

Server-side `model_to_color()` in routes.py replicates JS `getModelColor()` (Java string hash → COLORS array index). The COLORS array is defined identically in both `static/js/charts.js` and `routes.py` (must stay in sync).

Row color toggle: Color button master ON/OFF controls all rows. Single click (Color ON) or double-click (Color OFF, 350ms timer) toggles individual row car color via `--row-car-color` CSS variable.

### Session type auto-detection

Parsers detect session type from the CSV **filename** (not full path) by matching keywords. Type ordering: Paid-Test → Practice → Bronze-Session → Pre-Qualifying → Qualifying → Warm-up → Race.

- `paid test|paidtest|paid_test` → Paid-Test
- `practice|free practice|fp` → Practice
- `bronze session|bronzesession|bronze_session` → Bronze-Session
- `pre-qualifying|prequalifying|pre-qual|prequal` → Pre-Qualifying
- `qualifying|qual|qualification|q` → Qualifying
- `warm-up|warmup|warm_up` → Warm-up
- `race|r` → Race

Falls back to "Practice". Upload page allows manual session name and type override.

### Charts & Analytics API

`GET /api/sessions/<id>/analytics` returns pre-computed data for all charts in a single request:

| Field | Content |
|---|---|
| `per_car` | Per-car stats: best_lap, best_s1/s2/s3, theoretical, top_speed, avg_lap, min_lap, q1, median, q3, max_lap, car_model |
| `lap_times` | All valid laps with car_number, lap_number, lap_time, sectors, session_time, out_lap/in_lap flags, sc_lap boolean, car_model, series_color, model_color |
| `overall_best_lap` | Fastest lap time across all cars (for delta reference) |
| `pit_stops` | List of `{car_number, driver_name, in_lap, out_lap, pit_time}` |
| `position_progression` | (Race only) Per-lap position per car, computed by sorting by session_time at each lap number |
| `car_stints` | Per-car stint info (used for strategy chart) |

**Analytics cache:** 5-minute in-memory cache (`_analytics_cache`, max 50 entries). Invalidated per-session via `_invalidate_analytics_cache()` or globally via `_invalidate_all_analytics_caches()`.

Chart.js uses a single `<canvas id="analysisChart">` element — each render function destroys the previous Chart.js instance and creates a new one. All chart data is cached client-side after the first API fetch. Consistent car color palette across all chart types.

**Safety car detection:** Laps exceeding 1.35× the car's median clean lap time are flagged as `sc_lap: true` in the analytics API. The Lap Times chart filters these out.

**Pit stop detection:** Pairs consecutive in_lap→out_lap transitions within a car's sorted laps. Pit time uses `time_out_lap - time_in_lap` raw timestamps when available from the CSV.

## Theme system

Dark/light mode toggle persisted in `localStorage` with `prefers-color-scheme` fallback. CSS variables defined in `static/css/theme.css`, toggle logic in `static/js/theme.js` (loaded in `<head>` to prevent FOUC). Toggle button in navbar visible to all users.

## Key design decisions

- **No pandas** — stdlib `csv` module handles all parsing, avoiding C compiler dependency on Windows
- **Multi-file upload** — TSL requires 2 files (classification + sector); Swiss Timing requires 1+ files (sector required, 4 optional). Upload page shows inputs dynamically per parser
- **Upload auto-compute** — On import: auto-computes `model_color = model_to_color(car_model)`. If `car_model` is empty, falls back to sibling events (same championship + year) from CarConfig or Standing
- **Best lap detection** — computed per car during import: min positive `lap_time` → `is_best=True`
- **Pit stop time** — uses `time_out_lap - time_in_lap` raw timestamps from CSV when available; falls back to median-based estimation
- **Three-level best highlighting** — overall best (purple) > car best (green) > stint best (orange). Stint = consecutive laps between pit stops or driver changes, computed by detecting out_lap boundaries
- **Chart tabs** — 13 chart sub-types share one canvas; tab switching destroys/recreates the Chart.js instance
- **SQLite by default** — swap to PostgreSQL by changing `DATABASE_URL` env var in `config.py`
- **Live schema migrations** — `app.py` runs migration functions on startup (`_ensure_session_sort_order_column()`, `_ensure_lap_record_time_columns()`, etc.) to add columns to existing databases without a migration framework
- **No DB migration framework** — `db.create_all()` runs on every startup. Schema changes require manual `ALTER TABLE` or DB wipe

## Authentication & Authorization

Flask session-based auth using `werkzeug.security` password hashing — no extra dependencies. Two decorators in `routes.py`:

- `@login_required` — redirects to `/login` if no `user_id` in session
- `@admin_required` — redirects to `/login` (unauthenticated) or `/` with flash "Admin access required" (non-admin)

**CSRF protection:** All POST routes require CSRF token (skips `/api/` endpoints). Token injected into all templates via `app.context_processor`.

`current_user` is injected into all templates via `app.context_processor`. Templates conditionally show admin buttons (`{% if current_user and current_user.is_admin %}`).

Default admin account is seeded by `_seed_admin()` in `app.py` — only created when the users table is empty.

## Utility scripts

- `scripts/repair_swiss_timing_driver_names.py` — re-parses Swiss Timing uploads to fix driver names and pit in/out flags on existing sessions

## Important notes

- **`session_time` is a Float** (seconds from session start), not a datetime. Used as chart X-axis for Lap Times / Delta views (displayed in minutes).
- **Import order**: stdlib → Flask → local modules. One import per line.
- **`current_user`** is injected into all templates via `app.context_processor` — no need to pass it explicitly in route handlers.
