import { z } from "zod"

import { apiRequest } from "./client"
import { loginRequestSchema, sessionResponseSchema } from "./schemas"

export type LoginInput = z.infer<typeof loginRequestSchema>

export async function login(input: LoginInput) {
  const body = loginRequestSchema.parse(input)
  await apiRequest("/ops/session", { method: "POST", body, schema: z.void() })
}

export async function getSession() {
  return apiRequest("/ops/session", { schema: sessionResponseSchema })
}

export async function logout() {
  await apiRequest("/ops/session", { method: "DELETE", schema: z.void() })
}
