import { mapCostSync } from "./adapters"
import { apiRequest } from "./client"
import { costSyncSchema } from "./schemas"

export async function syncCosts() {
  const payload = await apiRequest("/ops/costs/sync", {
    method: "POST",
    schema: costSyncSchema,
  })
  return mapCostSync(payload)
}
