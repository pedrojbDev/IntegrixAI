import os
from pathlib import Path
import subprocess
import sys
import unittest

from scripts import backfill_vapi_voice_quality


class VoiceQualityBackfillCliTests(unittest.TestCase):
    def test_documented_direct_command_runs_from_repository_root(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        environment = {key: value for key, value in os.environ.items() if key != 'PYTHONPATH'}
        result = subprocess.run(
            [sys.executable, '-B', 'scripts/backfill_vapi_voice_quality.py', '--help'],
            cwd=repository, env=environment, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        for argument in ('--tenant-id', '--start', '--end'):
            self.assertIn(argument, result.stdout)

    def test_parse_args_requires_explicit_tenant_and_half_open_window_bounds(self) -> None:
        """Dropping a required bound would permit a cross-tenant or unbounded import."""
        for args in (
            [],
            ["--tenant-id", "tenant_a", "--start", "2026-09-01T00:00:00+00:00"],
            ["--start", "2026-09-01T00:00:00+00:00", "--end", "2026-09-08T00:00:00+00:00"],
        ):
            with self.subTest(args=args), self.assertRaises(SystemExit):
                backfill_vapi_voice_quality.parse_args(args)

    def test_parse_args_rejects_non_increasing_window(self) -> None:
        """Allowing an empty or reversed interval breaks the documented [start, end) scope."""
        with self.assertRaises(SystemExit):
            backfill_vapi_voice_quality.parse_args(
                [
                    "--tenant-id", "tenant_a",
                    "--start", "2026-09-08T00:00:00+00:00",
                    "--end", "2026-09-01T00:00:00+00:00",
                ]
            )
