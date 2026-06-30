- [Git Commit After Work](git-commit-after-work.md) — always commit file changes after completing a task, don't wait for user to ask
- [Git Commit Language](git-commit-language.md) — git commit messages must be written in Chinese

# Project memory

## Rules
- User communicates in Chinese; all git commit messages must be in Chinese
- Always auto-commit after completing any file-modifying task
- No frontend build pipeline — Tailwind CSS CDN, Chart.js CDN, Lucide CDN only
- stdlib `csv` module only — no pandas
- `unittest.TestCase` (not pytest)

## Architecture decisions
- **2026-06-10**: Bootstrap → Tailwind CSS (CDN) + Lucide Static CDN for all templates [ses_14a51a92]
- **2026-06-10**: Chart view uses checkboxes (not tabs) for multi-chart display [ses_14a51a81]
- **2026-06-10**: Flask session-based auth with werkzeug.security, no extra deps [ses_14a51a8b]
- **2026-06-10**: Dark/light theme via CSS variables in `static/css/theme.css` + `static/js/theme.js` [ses_14a51a90]
- **2026-06-10**: Fonts: JetBrains Mono (data) + Syne (headings) via Google Fonts CDN [ses_14a51a90]
- **2026-06-12**: SECRET_KEY — production raises RuntimeError if unset; dev auto-generates random key [ses_145bc]
- **2026-06-12**: CSRF protection on all POST routes (skips `/api/`), token eagerly initialized in context processor [ses_145bc]
- **2026-06-12**: `_best_sectors()` shared helper extracted for `_compute_session_stats` and `_compute_driver_analysis` [ses_145bc]
- **2026-06-12**: `parseSortValue` + `initTableSort` extracted to `static/js/table-sort.js` [ses_145bc]
- **2026-06-12**: Position chart uses O(1) Map lookup instead of O(n²) `.find()` [ses_145bc]
- **2026-06-12**: `_analytics_cache` capped at 50 entries to prevent memory growth [ses_145bc]

## Gotchas
- CSRF token must be eagerly generated in context processor (not lazily on template render) — lazy init causes test failures because pages without forms never generate the token [ses_145bc]
- Session type keywords are matched from CSV **filename** only, not full path
- `session_time` is Float (seconds from session start), not datetime — used as chart X-axis
- COLORS array in `static/js/charts.js` and `routes.py` must stay in sync
- CI/CD triggers on `master` branch; ensure push target matches
