const numberFormatter = new Intl.NumberFormat("pt-BR")
const percentFormatter = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})
const brlFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 6,
})

export function formatNumberBR(value: number | null | undefined) {
  return numberFormatter.format(Number(value || 0))
}

export function formatPercent(value: number | null | undefined) {
  return `${percentFormatter.format(Number(value || 0))}%`
}

export function formatCurrencyBRL(value: number | null | undefined) {
  return brlFormatter.format(Number(value || 0))
}

export function formatDuration(value: number | null | undefined) {
  const ms = Number(value || 0)
  if (ms >= 60_000) {
    return `${(ms / 60_000).toFixed(1).replace(".", ",")} min`
  }
  if (ms >= 1_000) {
    return `${(ms / 1_000).toFixed(1).replace(".", ",")} s`
  }
  return `${Math.round(ms)} ms`
}

export function formatDateTimeBR(value: string | null | undefined) {
  if (!value) {
    return "-"
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return "-"
  }
  return date.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}
