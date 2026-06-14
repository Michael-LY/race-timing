# AGENTS.md

Flask app for importing race timing CSV files, storing lap/standing data in SQLite, and rendering server-side analysis pages with interactive charts. Deployed on Ubuntu + Nginx + systemd + Gunicorn.

## Commands

```bash
pip install -r requirements.txt         # Flask + Flask-SQLAlchemy only
python run.py                            # dev: http://localhost:5000, debug, 0.0.0.0
rm instance/timing.db && python run.py   # fresh DB + seed (admin/admin123)
python -m unittest discover -s tests     # all tests
python -m unittest tests.test_standings_sorting  # single test file
```

## Architecture

- **app.py** — `create_app()` factory; runs `db.create_all()` then inline `ALTER TABLE` migrations via `_ensure_*()` functions. CSRF protection on all POST (skips `/api/`). Context processor injects `current_user` + `csrf_token`.
- **models.py** — `User`, `TimeKeeper`, `Event`, `Session`, `Standing`, `LapRecord`, `CarConfig` (event-level car display config), `CarModelColor` (global model→color mapping).
- **routes.py** — All routes in a single `Blueprint("main")`. Key sections: auth, event CRUD, upload CSV, session detail (5 inline views), analytics API, car config editor (event-level + global model colors).
- **parsers/** — `BaseParser` ABC with `parse(**kwargs)` returning `{session_name, session_type, laps[], standings[]}`. Two parsers: `TSLTimingParser` (2-file CSV pair) and `SwissTimingParser` (up to 5 files). Registered in `PARSER_REGISTRY` dict.
- **templates/** — 13 Jinja2 templates, no frontend build step. CDN deps: Tailwind CSS, Chart.js 4.4.7 + zoom plugin, Lucide icons, JetBrains Mono + Syne fonts.
- **static/** — `theme.css` (light/dark CSS vars), `theme.js` (localStorage theme toggle), `charts.js` (Chart.js rendering for 14+ chart types), `table-sort.js` (client-side column sorting).

## Database models — key fields beyond basic

- **Standing**: `gap_text`/`diff_text` (String, stores raw CSV strings like "1 Lap"), `car_model`/`series_color`/`model_color` (color system).
- **CarConfig**: event-level overrides for `car_model`, `series_color`, `model_color`, `team_name`, `class_name`. One row per `(event_id, car_number)`.
- **CarModelColor**: global `car_model` → `model_color` mapping, used by "By Model" chart mode across all events.

## Color system (By Model / By Car #)

Priority for chart colors (`getCarColor()` in charts.js):
- **By Car # mode**: `series_color` (per-car override) → car number hash into COLORS array
- **By Model mode**: `model_color` (from standings/CarConfig, overridden by global `CarModelColor` table) → model name hash fallback

Server-side `model_to_color()` replicates JS `getModelColor()` (Java string hash → COLORS array index). Defined as module-level function in routes.py.

Three levels of row/cell highlighting:
- **bg-purple** (`--highlight-overall-bg`, 70% opacity): best across all cars (overall best lap/sector)
- **bg-green** (`--highlight-car-bg`, 70% opacity): per-car best
- **bg-orange** (`--highlight-stint-bg`, 70% opacity): per-stint best (between pit stops/driver changes)

## Session detail page — 5 inline views

1. **Classification** — standings table with class filter, car model color toggle (Color button, click/dbl-click rows), raw gap_text/diff_text shown when available
2. **Lap Summary** — best lap per car, same Color toggle with `data-car-color`
3. **Lap-by-Lap** — every lap, pit-in/out coloring, three-level best highlighting (purple/green/orange), per-car filter, per-stint bests
4. **Drivers** — per-driver analysis with theoretical lap, overall best sector highlight
5. **Chart** — 14 chart sub-types (lapTime, delta, sector, speed, boxPlot, pitStops, position, driverS1/S2/S3, driverLap, consistency, strategy) in toggleable checkboxes

Table row color toggle: Color button master ON/OFF controls all rows. Single click (Color ON) or double-click detection via 350ms timer (Color OFF) toggles individual row car color via `--row-car-color` CSS variable at `rgba(r,g,b,0.60)`.

## Upload & import

- Accepts up to 5 CSV files per session (sector, classification, pitstops, TLW, messages). Parser-specific file inputs shown dynamically.
- On import: auto-computes `model_color = model_to_color(car_model)`. If `car_model` is empty, falls back to sibling events (same championship + year) from CarConfig or Standing.
- Session type auto-detected from CSV filename keywords (Paid-Test → Practice → Bronze-Session → Pre-Qualifying → Qualifying → Warm-up → Race). Falls back to "Practice".
- Standings sorted by position ASC with NC cars (pos=0) below classified, sorted by laps DESC.

## Routes (admin-only marked)

| Route | Auth | Purpose |
|---|---|---|
| `GET/POST /login` | — | Login |
| `GET /logout` | — | Logout |
| `GET/POST /register` | admin | Register user |
| `GET/POST /events/new` | admin | Create event |
| `GET /events/<id>` | — | Event detail with session list |
| `GET/POST /events/<id>/edit` | admin | Edit event |
| `POST /events/<id>/delete` | admin | Delete event (cascades) |
| `GET/POST /events/<id>/upload` | admin | Upload CSV |
| `POST /events/<id>/sessions/reorder` | admin | Drag-drop reorder |
| `GET/POST /events/<id>/car-config` | admin | Per-event car config editor |
| `GET/POST /car-model-colors` | admin | Global car model color editor |
| `GET/POST /sessions/<id>/edit` | admin | Edit session |
| `POST /sessions/<id>/delete` | admin | Delete session |
| `GET /sessions/<id>` | — | Session detail (all 5 views) |
| `GET /sessions/<id>/drivers` | — | Standalone driver analysis |
| `GET /api/sessions/<id>/laps` | — | Lap data JSON |
| `GET /api/sessions/<id>/analytics` | — | Pre-computed stats for all charts |
| `POST /api/sessions/<id>/car-models` | admin | Batch update car models |

## Conventions

- stdlib `csv` module only — no pandas, no frontend build pipeline.
- One import per line, order: stdlib → Flask → local modules.
- `unittest.TestCase` (not pytest). Each test creates its own temp DB via `create_app(config_override)`.
- Default admin: `admin` / `admin123` (seeded on first boot, never hardcode in templates).
- No DB migration framework — `db.create_all()` + inline `ALTER TABLE` on startup.
- `session_time` is Float (seconds from session start), not datetime. Used as chart X-axis.
- Chart zoom: Y-axis only. Drag to zoom, Shift+drag to pan, double-click to reset.
- Analytics API has 5-minute in-memory cache (`_analytics_cache`). Invalidated per-session or all at once via `_invalidate_all_analytics_caches()`.

## Notes

