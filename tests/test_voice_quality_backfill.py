import unittest

from scripts import backfill_vapi_voice_quality


class VoiceQualityBackfillCliTests(unittest.TestCase):
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
