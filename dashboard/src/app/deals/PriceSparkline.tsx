"use client";

import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type Point = { observed_at: string; price: number | null; loyalty_price: number | null };

export function PriceSparkline({ data }: { data: Point[] }) {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const isDark = mounted && resolvedTheme === "dark";
  const axis = isDark ? "#71717a" : "#a1a1aa";       // zinc-500/400
  const grid = isDark ? "#27272a" : "#e4e4e7";       // zinc-800/200
  const tooltipBg = isDark ? "#18181b" : "#ffffff";
  const tooltipFg = isDark ? "#e4e4e7" : "#27272a";
  const accent = isDark ? "#38bdf8" : "#0ea5e9";     // sky-400/500

  const series = data
    .filter((p) => p.price != null)
    .map((p) => ({
      label: new Date(p.observed_at).toLocaleDateString("de-DE", {
        day: "2-digit",
        month: "2-digit",
      }),
      price: Number(p.price),
      loyalty: p.loyalty_price != null ? Number(p.loyalty_price) : null,
    }));

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={series} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <defs>
            <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={accent} stopOpacity={0.25} />
              <stop offset="100%" stopColor={accent} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={grid} vertical={false} />
          <XAxis
            dataKey="label"
            stroke={axis}
            tick={{ fontSize: 11, fill: axis }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            stroke={axis}
            tick={{ fontSize: 11, fill: axis }}
            tickFormatter={(v) => `${v.toFixed(2)} €`}
            tickLine={false}
            axisLine={false}
            domain={["auto", "auto"]}
          />
          <Tooltip
            cursor={{ stroke: grid, strokeWidth: 1 }}
            formatter={(v) => (typeof v === "number" ? `${v.toFixed(2)} €` : "—")}
            contentStyle={{
              backgroundColor: tooltipBg,
              border: `1px solid ${grid}`,
              borderRadius: 6,
              fontSize: 12,
              padding: "6px 10px",
            }}
            labelStyle={{ color: tooltipFg, fontSize: 12, fontWeight: 500 }}
            itemStyle={{ color: tooltipFg }}
          />
          <Area
            type="monotone"
            dataKey="price"
            stroke={accent}
            strokeWidth={2}
            fill="url(#priceFill)"
            name="Preis"
            dot={false}
            activeDot={{ r: 4, strokeWidth: 0 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
