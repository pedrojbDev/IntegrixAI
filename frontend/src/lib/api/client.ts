import type { z } from "zod"

import { env } from "@/lib/env/env"

import { ApiError } from "./errors"

type QueryParams = Record<string, string | number | boolean | undefined | null>

type RequestOptions<TSchema extends z.ZodType> = {
  method?: "GET" | "POST" | "DELETE"
  body?: unknown
  params?: QueryParams
  schema?: TSchema
}

function buildUrl(path: string, params?: QueryParams) {
  const base = env.apiBaseUrl || window.location.origin
  const url = new URL(path, base)

  for (const [key, value] of Object.entries(params || {})) {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value))
    }
  }

  if (!env.apiBaseUrl) {
    return `${url.pathname}${url.search}`
  }
  return url.toString()
}

function filenameFromDisposition(contentDisposition: string | null, fallback: string) {
  const match = contentDisposition?.match(/filename="?([^";]+)"?/i)
  return match?.[1] || fallback
}

async function readErrorPayload(response: Response) {
  try {
    return await response.json()
  } catch {
    return await response.text()
  }
}

function normalizeHttpError(status: number, payload: unknown) {
  const detail = typeof payload === "object" && payload !== null && "detail" in payload ? payload.detail : payload
  const detailText = typeof detail === "string" ? detail : undefined
  const fieldErrors =
    status === 422 && Array.isArray(detail)
      ? detail.reduce<Record<string, string[]>>((errors, item) => {
          if (typeof item !== "object" || item === null || !("loc" in item) || !("msg" in item)) {
            return errors
          }
          const itemWithFields = item as { loc: unknown; msg: unknown }
          const loc = Array.isArray(itemWithFields.loc) ? itemWithFields.loc.join(".") : String(itemWithFields.loc)
          const msg = String(itemWithFields.msg)
          errors[loc] = [...(errors[loc] || []), msg]
          return errors
        }, {})
      : undefined

  if (status === 401) {
    return new ApiError({ kind: "unauthorized", status, message: "Sessão expirada.", detail })
  }
  if (status === 403) {
    return new ApiError({ kind: "forbidden", status, message: "Acesso negado.", detail })
  }
  if (status === 422) {
    return new ApiError({ kind: "validation", status, message: "Revise os campos informados.", detail, fieldErrors })
  }
  if (status === 400 && detailText === "tenant_id obrigatorio em producao") {
    return new ApiError({
      kind: "tenant-required",
      status,
      message: "Informe um tenant para consultar este ambiente.",
      detail,
    })
  }
  if (status >= 500) {
    return new ApiError({ kind: "server", status, message: "Falha operacional no backend.", detail })
  }
  return new ApiError({ kind: "unknown", status, message: detailText || `Erro HTTP ${status}.`, detail })
}

export async function apiRequest<TSchema extends z.ZodType>(
  path: string,
  options: RequestOptions<TSchema> = {},
): Promise<z.infer<TSchema>> {
  const headers = new Headers()
  let body: BodyInit | undefined

  if (options.body !== undefined) {
    headers.set("content-type", "application/json")
    body = JSON.stringify(options.body)
  }

  try {
    const response = await fetch(buildUrl(path, options.params), {
      method: options.method || "GET",
      headers,
      body,
      credentials: "include",
    })

    if (!response.ok) {
      const error = normalizeHttpError(response.status, await readErrorPayload(response))
      if (error.kind === "unauthorized") {
        window.dispatchEvent(new CustomEvent("ops-session-expired"))
      }
      throw error
    }

    if (response.status === 204) {
      return undefined as z.infer<TSchema>
    }

    const payload = await response.json()
    return options.schema ? options.schema.parse(payload) : payload
  } catch (error) {
    if (error instanceof ApiError) {
      throw error
    }
    throw new ApiError({
      kind: "network",
      message: "Não foi possível conectar ao backend.",
      detail: error,
    })
  }
}

export async function downloadFile(path: string, params: QueryParams, fallbackFilename: string) {
  try {
    const response = await fetch(buildUrl(path, params), { credentials: "include" })
    if (!response.ok) {
      const error = normalizeHttpError(response.status, await readErrorPayload(response))
      if (error.kind === "unauthorized") {
        window.dispatchEvent(new CustomEvent("ops-session-expired"))
      }
      throw error
    }

    const downloadUrl = URL.createObjectURL(await response.blob())
    const anchor = document.createElement("a")
    anchor.href = downloadUrl
    anchor.download = filenameFromDisposition(response.headers.get("content-disposition"), fallbackFilename)
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(downloadUrl)
  } catch (error) {
    if (error instanceof ApiError) {
      throw error
    }
    throw new ApiError({
      kind: "network",
      message: "Não foi possível gerar o relatório.",
      detail: error,
    })
  }
}
