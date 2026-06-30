# Race Timing

A Flask web application for importing, storing, and analyzing motorsport race timing data. Upload CSV exports from TSL Timing or Swiss Timing systems, then explore interactive charts, lap-by-lap analysis, and driver statistics.

![Python](https://img.shields.io/badge/python-3.12+-blue)
![Flask](https://img.shields.io/badge/flask-3.1-green)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **Multi-format import** — TSL Timing (2-file CSV) and Swiss Timing (up to 5-file CSV: sector, classification, pit stops, TLW, messages)
- **5 session views** — Classification, Lap Summary, Lap-by-Lap, Driver Analysis, Charts
- **13 chart types** — Lap times, deltas, sectors, speed, box plots, pit stops, position progression, driver sectors, consistency, strategy (Gantt)
- **Smart lap detection** — Out lap / in lap heuristic detection, track limit (TLW) matching, safety car lap filtering
- **Dark / light theme** — System-aware toggle with localStorage persistence
- **Car model colors** — Per-car and per-model color system with "By Car #" and "By Model" chart modes
- **Admin tools** — Refresh out/in lap detection for existing sessions, re-upload TLW files
- **Auto-deploy** — Push to `master` triggers GitHub Actions → Ubuntu server via SSH

## Quick Start

```bash
# Clone and install
git clone https://github.com/Michael-LY/race-timing.git
cd race-timing
pip install -r requirements.txt

# Run development server
python run.py
# → http://localhost:5000

# Default admin account: admin / admin123
```

## Usage

1. **Create an event** — Set track, year, championship, and timing system
2. **Upload CSV files** — Select the timing system format and upload sector/classification/pit stop files
3. **Explore data** — Switch between Classification, Lap Summary, Lap-by-Lap, Drivers, and Chart views
4. **Customize colors** — Click the Color button to toggle car model colors on tables and charts

## Project Structure

```
race-timing/
├── app.py              # Flask app factory, DB migrations
├── config.py           # Configuration constants
├── models.py           # SQLAlchemy models (Event, Session, LapRecord, Standing, ...)
├── routes.py           # All routes: auth, CRUD, upload, session views, analytics API
├── parsers/
│   ├── base.py         # BaseParser ABC
│   ├── tsl.py          # TSL Timing CSV parser
│   ├── swiss_timing.py # Swiss Timing CSV parser (up to 5 files)
│   └── detect_laps.py  # Out lap / in lap / track limit detection
├── templates/          # 17 Jinja2 templates
├── static/
│   ├── css/theme.css   # Light/dark theme CSS variables
│   └── js/
│       ├── charts.js   # Chart.js rendering (13 chart types)
│       ├── theme.js    # Theme toggle
│       └── table-sort.js
├── tests/              # unittest test suite
└── scripts/            # Deploy and utility scripts
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Flask 3.1, Flask-SQLAlchemy, SQLite |
| Frontend | Tailwind CSS (CDN), Chart.js 4.4, Lucide Icons |
| Auth | Flask session + werkzeug.security (bcrypt) |
| Deploy | Gunicorn, Nginx, systemd, GitHub Actions CI/CD |

## CSV Formats

### TSL Timing
- **Sector CSV** — Per-lap sector times and speed traps
- **Classification CSV** — Final standings with gaps and pit stops

### Swiss Timing (semicolon-delimited)
- **SectorListCSV** (required) — Lap times, sector times, speed traps
- **ResultListCSV** (optional) — Classification standings
- **PitStopsCsv** (optional) — Pit stop in/out lap mapping
- **TLWlistMessage** (optional) — Track limit warnings (matched to laps by race time)
- **MessageListCSV** (optional) — Race control messages

## Analytics

The app computes and displays:

- **Best lap** — Per car, per driver, overall (excludes out laps, in laps, track limit laps)
- **Best sectors** — S1/S2/S3 with three-level highlighting (overall / per-car / per-stint)
- **Theoretical lap** — Best S1 + best S2 + best S3
- **Safety car detection** — Laps >1.35x median flagged and filtered from stats
- **Box plots** — Q1/median/Q3 per car or per driver
- **Strategy Gantt** — Stint visualization with pit stop gaps

## Deployment

Push to `master` auto-deploys via GitHub Actions. See [DEPLOYMENT.md](DEPLOYMENT.md) for full setup.

```bash
# Quick overview
git push origin master
# → GitHub Actions builds, tests, and deploys to your Ubuntu server
# → Gunicorn restarts on port 8000, Nginx reverse-proxies on port 80
```

## Running Tests

```bash
python -m unittest discover -s tests
```

## License

MIT
