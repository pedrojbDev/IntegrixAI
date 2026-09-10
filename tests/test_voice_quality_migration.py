import importlib.util
from pathlib import Path
import unittest

from sqlalchemy import Float, Integer


class VoiceQualityMigrationTests(unittest.TestCase):
    def test_upgrade_adds_nullable_quality_columns_and_downgrade_removes_them(self) -> None:
        """A missing migration operation would desynchronize deployed schema and the model."""
        path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0013_vapi_voice_quality.py"
        spec = importlib.util.spec_from_file_location("voice_quality_migration", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        operations: list[tuple[str, str, object]] = []

        class FakeOp:
            @staticmethod
            def add_column(table, column):
                operations.append(("add", table, column))

            @staticmethod
            def drop_column(table, column):
                operations.append(("drop", table, column))

        module.op = FakeOp()
        module.upgrade()
        module.downgrade()

        added = {column.name: column for action, _table, column in operations if action == "add"}
        self.assertIsInstance(added["turn_latency_average_ms"].type, Float)
        self.assertIsInstance(added["assistant_interruptions"].type, Integer)
        self.assertTrue(added["turn_latency_average_ms"].nullable)
        self.assertTrue(added["assistant_interruptions"].nullable)
        self.assertEqual(
            [("drop", "vapi_call_costs", "assistant_interruptions"), ("drop", "vapi_call_costs", "turn_latency_average_ms")],
            [operation for operation in operations if operation[0] == "drop"],
        )
