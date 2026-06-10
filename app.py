import os

from flask import Flask, session as flask_session
from config import SQLALCHEMY_DATABASE_URI, SQLALCHEMY_TRACK_MODIFICATIONS, UPLOAD_FOLDER
from models import db, TimeKeeper, User


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = SQLALCHEMY_TRACK_MODIFICATIONS
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(os.path.dirname(SQLALCHEMY_DATABASE_URI.replace("sqlite:///", "")), exist_ok=True)

    db.init_app(app)

    with app.app_context():
        db.create_all()
        _seed_time_keepers()
        _seed_admin()

    # Context processor: inject current_user into all templates
    @app.context_processor
    def inject_current_user():
        user_id = flask_session.get("user_id")
        user = None
        if user_id:
            user = db.session.get(User, user_id)
        return dict(current_user=user)

    from routes import bp
    app.register_blueprint(bp)

    return app


def _seed_time_keepers():
    from parsers import PARSER_REGISTRY
    for key, parser in PARSER_REGISTRY.items():
        if not TimeKeeper.query.filter_by(name=parser.name).first():
            db.session.add(TimeKeeper(name=parser.name, parser_module=key, description=parser.description))
    db.session.commit()


def _seed_admin():
    """Create default admin account if no users exist."""
    if User.query.count() == 0:
        admin = User(username="admin", is_admin=True)
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()
