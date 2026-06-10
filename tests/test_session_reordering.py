import importlib
import os
import tempfile
import unittest

import config
import app as app_module_import
from models import Event, Session, User, db


class SessionReorderingTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{self.tmp_db.name}"

        imported_app_module = importlib.reload(app_module_import)
        self.app = imported_app_module.create_app()
        self.app.config["TESTING"] = True

        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()
        with self.app.app_context():
            db.engine.dispose()
        if os.path.exists(self.tmp_db.name):
            os.remove(self.tmp_db.name)

    def test_admin_can_reorder_sessions(self):
        admin = User(username="reorder-admin", is_admin=True)
        admin.set_password("secret123")
        db.session.add(admin)
        db.session.flush()

        event = Event(name="Test Event")
        db.session.add(event)
        db.session.flush()

        session_a = Session(event_id=event.id, name="Session A", session_type="Practice")
        session_b = Session(event_id=event.id, name="Session B", session_type="Race")
        db.session.add_all([session_a, session_b])
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess["user_id"] = admin.id

        response = self.client.post(
            f"/events/{event.id}/sessions/reorder",
            data={"session_ids": [str(session_b.id), str(session_a.id)]},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        db.session.expire_all()
        self.assertEqual(db.session.get(Session, session_b.id).sort_order, 0)
        self.assertEqual(db.session.get(Session, session_a.id).sort_order, 1)

    def test_non_admin_cannot_reorder_sessions(self):
        user = User(username="reorder-viewer", is_admin=False)
        user.set_password("secret123")
        db.session.add(user)
        db.session.flush()

        event = Event(name="Test Event")
        db.session.add(event)
        db.session.flush()

        session = Session(event_id=event.id, name="Session A", session_type="Practice")
        db.session.add(session)
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess["user_id"] = user.id

        response = self.client.post(
            f"/events/{event.id}/sessions/reorder",
            data={"session_ids": [str(session.id)]},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/", response.headers["Location"])


if __name__ == "__main__":
    unittest.main()
