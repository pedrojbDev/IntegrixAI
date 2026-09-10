export function mergeVoiceQualitySeries(
  latency: Array<{ timestamp: string; value: number }>,
  interruptions: Array<{ timestamp: string; value: number }>,
) {
  const points = new Map<string, { timestamp: string; latency: number | null; interruptions: number | null }>()
  for (const [items, key] of [[latency, "latency"], [interruptions, "interruptions"]] as const) {
    for (const item of items) {
      const existing = points.get(item.timestamp) || { timestamp: item.timestamp, latency: null, interruptions: null }
      points.set(item.timestamp, { ...existing, [key]: item.value })
    }
  }
  return [...points.values()].sort((left, right) => left.timestamp.localeCompare(right.timestamp))
}
