function normalizeBasename(value: string | undefined) {
  if (!value || value === "/") {
    return "/"
  }
  const withLeading = value.startsWith("/") ? value : `/${value}`
  return withLeading.endsWith("/") ? withLeading.slice(0, -1) : withLeading
}

function normalizeApiBase(value: string | undefined) {
  if (!value) {
    return ""
  }
  return value.endsWith("/") ? value.slice(0, -1) : value
}

export const env = {
  apiBaseUrl: normalizeApiBase(import.meta.env.VITE_API_BASE_URL),
  appBasename: normalizeBasename(
    import.meta.env.VITE_APP_BASENAME || (import.meta.env.PROD ? "/dashboard" : "/"),
  ),
}
