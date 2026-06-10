import importlib
import os
import tempfile
import unittest

import config
import app as app_module_import
from models import Event, LapRecord, Session, Standing, db


class EventDeletionTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{self.tmp_db.name}"

        imported_app_module = importlib.reload(app_module_import)
        self.app = imported_app_module.create_app()
        self.app.config["TESTING"] = True

        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()
        with self.app.app_context():
            db.engine.dispose()
        if os.path.exists(self.tmp_db.name):
            os.remove(self.tmp_db.name)

    def test_deleting_event_removes_related_sessions_and_laps(self):
        event = Event(name="Test Event")
        db.session.add(event)
        db.session.flush()

        session = Session(event_id=event.id, name="Race", session_type="Race")
        db.session.add(session)
        db.session.flush()

        lap = LapRecord(session_id=session.id, car_number="1", lap_number=1, lap_time=1.23)
        standing = Standing(session_id=session.id, position=1, car_number="1")
        db.session.add_all([lap, standing])
        db.session.commit()

        db.session.delete(event)
        db.session.commit()

        self.assertIsNone(db.session.get(Event, event.id))
        self.assertIsNone(db.session.get(Session, session.id))
        self.assertIsNone(db.session.get(LapRecord, lap.id))
        self.assertIsNone(db.session.get(Standing, standing.id))


if __name__ == "__main__":
    unittest.main()
