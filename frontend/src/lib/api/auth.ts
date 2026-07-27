import { z } from "zod"

import { apiRequest } from "./client"
import { loginRequestSchema, sessionResponseSchema } from "./schemas"
import type { SessionPrincipal } from "@/types/dashboard"

export type LoginInput = z.infer<typeof loginRequestSchema>

function mapPrincipal(raw: z.infer<typeof sessionResponseSchema>["principal"]): SessionPrincipal {
  return {
    id: raw.id,
    email: raw.email,
    role: raw.role,
    tenantIds: raw.tenant_ids,
    mustChangePassword: raw.must_change_password,
  }
}

export async function login(input: LoginInput) {
  const body = loginRequestSchema.parse(input)
  const response = await apiRequest("/ops/session", { method: "POST", body, schema: sessionResponseSchema })
  return { authenticated: true as const, principal: mapPrincipal(response.principal) }
}

export async function getSession() {
  const response = await apiRequest("/ops/session", { schema: sessionResponseSchema })
  return { authenticated: true as const, principal: mapPrincipal(response.principal) }
}

export async function logout() {
  await apiRequest("/ops/session", { method: "DELETE", schema: z.void() })
}

export async function changePassword(input: { currentPassword: string; newPassword: string }) {
  await apiRequest("/ops/session/password", {
    method: "POST",
    body: {
      current_password: input.currentPassword,
      new_password: input.newPassword,
    },
    schema: z.void(),
  })
}

export async function bootstrap(input: { token: string; email: string; password: string }) {
  const response = await apiRequest("/ops/bootstrap", {
    method: "POST",
    body: input,
    schema: sessionResponseSchema,
  })
  return { authenticated: true as const, principal: mapPrincipal(response.principal) }
}
