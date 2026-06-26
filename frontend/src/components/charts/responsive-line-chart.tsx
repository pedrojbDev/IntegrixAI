import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { useEffect, useRef, useState } from "react"

import { formatDateTimeBR, formatNumberBR } from "@/lib/format"

type SeriesConfig = {
  key: string
  label: string
  color: string
  area?: boolean
}

type ResponsiveLineChartProps = {
  data: Array<Record<string, string | number>>
  series: SeriesConfig[]
}

export function ResponsiveLineChart({ data, series }: ResponsiveLineChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [chartWidth, setChartWidth] = useState(0)

  useEffect(() => {
    const container = containerRef.current
    if (!container) {
      return
    }

    const updateWidth = () => {
      setChartWidth(Math.floor(container.clientWidth))
    }
    updateWidth()

    const observer = new ResizeObserver(updateWidth)
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  return (
    <div className="h-64 w-full min-w-0" ref={containerRef}>
      {chartWidth > 0 ? (
        <AreaChart data={data} height={256} margin={{ bottom: 0, left: -18, right: 10, top: 8 }} width={chartWidth}>
          <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="timestamp"
            minTickGap={28}
            stroke="hsl(var(--muted-foreground))"
            tickFormatter={(value) => formatDateTimeBR(String(value))}
            tickLine={false}
            tickMargin={10}
          />
          <YAxis
            stroke="hsl(var(--muted-foreground))"
            tickFormatter={(value) => formatNumberBR(Number(value))}
            tickLine={false}
            width={58}
          />
          <Tooltip
            contentStyle={{
              background: "hsl(var(--popover))",
              border: "1px solid hsl(var(--border))",
              borderRadius: "8px",
              color: "hsl(var(--popover-foreground))",
            }}
            labelFormatter={(value) => formatDateTimeBR(String(value))}
          />
          {series.map((item) =>
            item.area ? (
              <Area
                dataKey={item.key}
                fill={item.color}
                fillOpacity={0.12}
                key={item.key}
                name={item.label}
                stroke={item.color}
                strokeWidth={2}
                type="monotone"
              />
            ) : (
              <Line
                dataKey={item.key}
                dot={false}
                key={item.key}
                name={item.label}
                stroke={item.color}
                strokeWidth={2}
                type="monotone"
              />
            ),
          )}
        </AreaChart>
      ) : null}
    </div>
  )
}
