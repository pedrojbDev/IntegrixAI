import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

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
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer height="100%" width="100%">
        <AreaChart data={data} margin={{ bottom: 0, left: -18, right: 10, top: 8 }}>
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
      </ResponsiveContainer>
    </div>
  )
}
