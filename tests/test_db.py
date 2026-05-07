import unittest
from unittest.mock import patch

from app.config import Settings
from app.db import get_engine


class DatabaseEngineTests(unittest.TestCase):
    def test_postgres_engine_uses_configured_pool_settings(self) -> None:
        settings = Settings(
            _env_file=None,
            database_url="postgresql+psycopg://app:secret@db.example.com:5432/integrix",
            db_pool_size=7,
            db_max_overflow=3,
            db_pool_timeout_seconds=4.5,
            db_pool_recycle_seconds=900,
        )

        with (
            patch("app.db.get_settings", return_value=settings),
            patch("app.db.create_engine") as create_engine,
        ):
            get_engine()

        create_engine.assert_called_once()
        _, kwargs = create_engine.call_args
        self.assertEqual(7, kwargs["pool_size"])
        self.assertEqual(3, kwargs["max_overflow"])
        self.assertEqual(4.5, kwargs["pool_timeout"])
        self.assertEqual(900, kwargs["pool_recycle"])
        self.assertEqual({"connect_timeout": 2}, kwargs["connect_args"])

    def test_non_postgres_engine_does_not_receive_pool_settings(self) -> None:
        settings = Settings(_env_file=None, database_url="sqlite://")

        with (
            patch("app.db.get_settings", return_value=settings),
            patch("app.db.create_engine") as create_engine,
        ):
            get_engine()

        create_engine.assert_called_once()
        _, kwargs = create_engine.call_args
        self.assertNotIn("pool_size", kwargs)
        self.assertNotIn("max_overflow", kwargs)
        self.assertNotIn("pool_timeout", kwargs)
        self.assertNotIn("pool_recycle", kwargs)
        self.assertEqual({}, kwargs["connect_args"])


if __name__ == "__main__":
    unittest.main()
