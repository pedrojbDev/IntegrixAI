import assert from "node:assert/strict"
import test from "node:test"

import { mergeVoiceQualitySeries } from "../src/pages/diagnostics/voice-quality-series.ts"

test("missing voice observations stay null while recorded zero stays zero", () => {
  assert.deepEqual(
    mergeVoiceQualitySeries(
      [{ timestamp: "2026-09-10T10:00:00Z", value: 450 }],
      [{ timestamp: "2026-09-10T11:00:00Z", value: 0 }],
    ),
    [
      { timestamp: "2026-09-10T10:00:00Z", latency: 450, interruptions: null },
      { timestamp: "2026-09-10T11:00:00Z", latency: null, interruptions: 0 },
    ],
  )
})

test("matching observations share a bucket and output stays chronological", () => {
  assert.deepEqual(
    mergeVoiceQualitySeries(
      [{ timestamp: "2026-09-10T11:00:00Z", value: 600 }, { timestamp: "2026-09-10T10:00:00Z", value: 0 }],
      [{ timestamp: "2026-09-10T11:00:00Z", value: 2 }],
    ),
    [
      { timestamp: "2026-09-10T10:00:00Z", latency: 0, interruptions: null },
      { timestamp: "2026-09-10T11:00:00Z", latency: 600, interruptions: 2 },
    ],
  )
  assert.deepEqual(mergeVoiceQualitySeries([], []), [])
})
