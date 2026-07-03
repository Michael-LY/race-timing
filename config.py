"""赛道计时应用 - 配置文件"""

import os
import secrets

# 应用根目录
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# 数据库连接地址（默认 SQLite，可通过环境变量切换 PostgreSQL）
SQLALCHEMY_DATABASE_URI = os.environ.get(
    "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'timing.db')}"
)
SQLALCHEMY_TRACK_MODIFICATIONS = False
# CSV 文件上传目录
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
# 最大上传大小：16 MB
MAX_CONTENT_LENGTH = 16 * 1024 * 1024

# 安全密钥：生产环境必须通过环境变量设置
# 开发模式（无环境变量）随机生成，每次重启变化，确保会话无法跨重启复用
_is_dev = not os.environ.get("DATABASE_URL") and not os.environ.get("SECRET_KEY")
SECRET_KEY = os.environ.get("SECRET_KEY") or (
    secrets.token_hex(32) if _is_dev else None
)

if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY environment variable is required in production. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
