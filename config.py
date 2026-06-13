import os
import secrets

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

SQLALCHEMY_DATABASE_URI = os.environ.get(
    "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'timing.db')}"
)
SQLALCHEMY_TRACK_MODIFICATIONS = False
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB

# Secret key: MUST be set via environment variable in production.
# In dev mode (no env var), generate a random key that changes each startup
# so sessions are not reusable across restarts — but never hardcode a value.
_is_dev = not os.environ.get("DATABASE_URL") and not os.environ.get("SECRET_KEY")
SECRET_KEY = os.environ.get("SECRET_KEY") or (
    secrets.token_hex(32) if _is_dev else None
)

if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY environment variable is required in production. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
