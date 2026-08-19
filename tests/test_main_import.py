import unittest

from app.main import app


class MainImportTests(unittest.TestCase):
    def test_app_import_smoke(self) -> None:
        self.assertIsNotNone(app)


if __name__ == "__main__":
    unittest.main()
