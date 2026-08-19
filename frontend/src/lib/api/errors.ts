export type ApiErrorKind =
  | "unauthorized"
  | "forbidden"
  | "validation"
  | "tenant-required"
  | "server"
  | "network"
  | "unknown"

export type ApiErrorShape = {
  kind: ApiErrorKind
  status?: number
  message: string
  detail?: unknown
  fieldErrors?: Record<string, string[]>
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status?: number
  readonly detail?: unknown
  readonly fieldErrors?: Record<string, string[]>

  constructor(error: ApiErrorShape) {
    super(error.message)
    this.name = "ApiError"
    this.kind = error.kind
    this.status = error.status
    this.detail = error.detail
    this.fieldErrors = error.fieldErrors
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}
