# Copilot instructions

Use [AGENTS.md](../AGENTS.md) as the primary guidance for this repository.

Keep changes aligned with the existing Flask + SQLAlchemy + server-rendered Jinja2 architecture, and prefer the standard library CSV parser over adding new dependencies. When changing parsers, imports, or display logic, preserve the normalized lap and standing fields and add or update tests in [tests/](../tests/).

Useful commands:
- `pip install -r requirements.txt`
- `python run.py`
- `python -m unittest discover -s tests`
