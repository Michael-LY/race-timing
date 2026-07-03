"""赛道计时应用 - Flask 应用工厂"""

import os
import secrets

from flask import Flask, session as flask_session, request, abort
from sqlalchemy import inspect, text

from config import SQLALCHEMY_DATABASE_URI, SQLALCHEMY_TRACK_MODIFICATIONS, UPLOAD_FOLDER, SECRET_KEY
from models import db, TimeKeeper, User


def create_app():
    """创建并配置 Flask 应用实例"""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = SQLALCHEMY_TRACK_MODIFICATIONS
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    app.config["SECRET_KEY"] = SECRET_KEY

    # 确保上传目录和数据库目录存在
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    db_dir = SQLALCHEMY_DATABASE_URI.replace("sqlite:///", "")
    if db_dir:
        os.makedirs(os.path.dirname(db_dir), exist_ok=True)

    db.init_app(app)

    # 启动时自动建表 + 运行内联迁移（兼容旧数据库）
    with app.app_context():
        db.create_all()
        _ensure_session_sort_order_column()
        _ensure_lap_record_time_columns()
        _ensure_car_model_columns()
        _ensure_series_color_columns()
        _ensure_model_color_columns()
        _ensure_gap_text_columns()
        _ensure_event_is_hidden_column()
        _ensure_track_limit_column()
        _seed_time_keepers()
        _seed_admin()

    # 上下文处理器：向所有模板注入 current_user 和 csrf_token
    @app.context_processor
    def inject_globals():
        user_id = flask_session.get("user_id")
        user = None
        if user_id:
            user = db.session.get(User, user_id)
        # 提前生成 CSRF token，确保模板中始终可用
        if "_csrf_token" not in flask_session:
            flask_session["_csrf_token"] = secrets.token_hex(32)
        return dict(current_user=user, csrf_token=flask_session["_csrf_token"])

    # 全局 CSRF 保护：拦截所有 POST 请求（除 /api/ 端点外）
    @app.before_request
    def csrf_protect():
        if request.method != "POST":
            return
        # /api/ 端点使用 token 认证，跳过 CSRF
        if request.path.startswith("/api/"):
            return
        token = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token")
        if not token or not _verify_csrf_token(token):
            abort(403)

    from routes import bp
    app.register_blueprint(bp)

    # 模板过滤器：从日期中提取 ISO 周数
    @app.template_filter("isoweek")
    def _iso_week_filter(date):
        if date is None:
            return None
        return date.isocalendar()[1]

    return app


def _verify_csrf_token(token: str) -> bool:
    """验证 CSRF token 是否与会话中的 token 匹配"""
    expected = flask_session.get("_csrf_token")
    if not expected or not token:
        return False
    return secrets.compare_digest(token, expected)


def _ensure_session_sort_order_column():
    """确保 sessions 表有 sort_order 列（内联迁移）"""
    inspector = inspect(db.engine)
    if "sessions" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("sessions")}
    if "sort_order" not in columns:
        with db.engine.begin() as connection:
            connection.execute(text("ALTER TABLE sessions ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"))


def _ensure_lap_record_time_columns():
    """确保 lap_records 表有 time_out_lap / time_in_lap 列"""
    inspector = inspect(db.engine)
    if "lap_records" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("lap_records")}
    if "time_out_lap" not in columns:
        with db.engine.begin() as connection:
            connection.execute(text("ALTER TABLE lap_records ADD COLUMN time_out_lap FLOAT"))
    if "time_in_lap" not in columns:
        with db.engine.begin() as connection:
            connection.execute(text("ALTER TABLE lap_records ADD COLUMN time_in_lap FLOAT"))


def _ensure_car_model_columns():
    """确保 standings 和 lap_records 表有 car_model 列"""
    inspector = inspect(db.engine)
    if "standings" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("standings")}
        if "car_model" not in columns:
            with db.engine.begin() as connection:
                connection.execute(text("ALTER TABLE standings ADD COLUMN car_model VARCHAR(100) DEFAULT ''"))
    if "lap_records" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("lap_records")}
        if "car_model" not in columns:
            with db.engine.begin() as connection:
                connection.execute(text("ALTER TABLE lap_records ADD COLUMN car_model VARCHAR(100) DEFAULT ''"))


def _ensure_series_color_columns():
    """确保 standings 和 lap_records 表有 series_color 列"""
    inspector = inspect(db.engine)
    if "standings" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("standings")}
        if "series_color" not in columns:
            with db.engine.begin() as connection:
                connection.execute(text("ALTER TABLE standings ADD COLUMN series_color VARCHAR(20) DEFAULT ''"))
    if "lap_records" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("lap_records")}
        if "series_color" not in columns:
            with db.engine.begin() as connection:
                connection.execute(text("ALTER TABLE lap_records ADD COLUMN series_color VARCHAR(20) DEFAULT ''"))


def _ensure_model_color_columns():
    """确保 standings / lap_records / car_configs 表有 model_color 列"""
    inspector = inspect(db.engine)
    for table in ("standings", "lap_records", "car_configs"):
        if table in inspector.get_table_names():
            columns = {column["name"] for column in inspector.get_columns(table)}
            if "model_color" not in columns:
                with db.engine.begin() as connection:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN model_color VARCHAR(20) DEFAULT ''"))


def _ensure_gap_text_columns():
    """确保 standings 表有 gap_text / diff_text 列"""
    inspector = inspect(db.engine)
    if "standings" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("standings")}
        if "gap_text" not in columns:
            with db.engine.begin() as connection:
                connection.execute(text("ALTER TABLE standings ADD COLUMN gap_text VARCHAR(50) DEFAULT ''"))
        if "diff_text" not in columns:
            with db.engine.begin() as connection:
                connection.execute(text("ALTER TABLE standings ADD COLUMN diff_text VARCHAR(50) DEFAULT ''"))


def _ensure_event_is_hidden_column():
    """确保 events 表有 is_hidden 列"""
    inspector = inspect(db.engine)
    if "events" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("events")}
    if "is_hidden" not in columns:
        with db.engine.begin() as connection:
            connection.execute(text("ALTER TABLE events ADD COLUMN is_hidden BOOLEAN NOT NULL DEFAULT 0"))


def _ensure_track_limit_column():
    """确保 lap_records 表有 track_limit 列"""
    inspector = inspect(db.engine)
    if "lap_records" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("lap_records")}
    if "track_limit" not in columns:
        with db.engine.begin() as connection:
            connection.execute(text("ALTER TABLE lap_records ADD COLUMN track_limit BOOLEAN NOT NULL DEFAULT 0"))


def _seed_time_keepers():
    """将注册的解析器写入 TimeKeeper 表"""
    from parsers import PARSER_REGISTRY
    for key, parser in PARSER_REGISTRY.items():
        if not TimeKeeper.query.filter_by(name=parser.name).first():
            db.session.add(TimeKeeper(name=parser.name, parser_module=key, description=parser.description))
    db.session.commit()


def _seed_admin():
    """无用户时创建默认管理员账号 admin / admin123"""
    if User.query.count() == 0:
        admin = User(username="admin", is_admin=True)
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()
