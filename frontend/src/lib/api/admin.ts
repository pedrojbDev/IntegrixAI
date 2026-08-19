import { z } from "zod"

import type { OpsRole, OpsUser } from "@/types/dashboard"

import { apiRequest } from "./client"
import {
  createdUserSchema,
  opsUserSchema,
  opsUsersSchema,
  temporaryPasswordSchema,
} from "./schemas"

function mapUser(raw: z.infer<typeof opsUserSchema>): OpsUser {
  return {
    id: raw.id,
    email: raw.email,
    role: raw.role,
    tenantIds: raw.tenant_ids,
    mustChangePassword: raw.must_change_password,
    isActive: raw.is_active,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  }
}

export async function listUsers() {
  return (await apiRequest("/ops/admin/users", { schema: opsUsersSchema })).map(mapUser)
}

export async function createUser(input: { email: string; role: OpsRole; tenantIds: string[] }) {
  const response = await apiRequest("/ops/admin/users", {
    method: "POST",
    body: { email: input.email, role: input.role, tenant_ids: input.tenantIds },
    schema: createdUserSchema,
  })
  return { user: mapUser(response.user), temporaryPassword: response.temporary_password }
}

export async function updateUser(
  userId: string,
  input: { role?: OpsRole; tenantIds?: string[]; isActive?: boolean },
) {
  const response = await apiRequest(`/ops/admin/users/${userId}`, {
    method: "PATCH",
    body: {
      role: input.role,
      tenant_ids: input.tenantIds,
      is_active: input.isActive,
    },
    schema: opsUserSchema,
  })
  return mapUser(response)
}

export async function resetUserPassword(userId: string) {
  const response = await apiRequest(`/ops/admin/users/${userId}/reset-password`, {
    method: "POST",
    schema: temporaryPasswordSchema,
  })
  return response.temporary_password
}
