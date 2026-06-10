# Copilot instructions

Use [AGENTS.md](../AGENTS.md) as the primary guidance for this repository.

Keep changes aligned with the existing Flask + SQLAlchemy + server-rendered Jinja2 architecture. Prefer the standard library CSV parser over adding dependencies, preserve the normalized lap and standing fields, and add or update tests in [tests/](../tests/) when import or display behavior changes.

Useful commands:
- `pip install -r requirements.txt`
- `python run.py`
- `python -m unittest discover -s tests`
