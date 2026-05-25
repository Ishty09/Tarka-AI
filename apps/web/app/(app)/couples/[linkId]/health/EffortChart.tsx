// Lightweight SVG bar chart — no chart library dependency. Two bars
// per day (one per partner). Missing days render as a dotted outline
// so gaps are visible.

interface Series {
  date: string;
  a: number | null;
  b: number | null;
}

export function EffortChart({
  series,
  aName,
  bName,
}: {
  series: Series[];
  aName: string;
  bName: string;
}) {
  const width = 560;
  const height = 160;
  const padding = { top: 8, right: 8, bottom: 24, left: 24 };
  const innerW = width - padding.left - padding.right;
  const innerH = height - padding.top - padding.bottom;
  const dayWidth = innerW / series.length;
  const barW = (dayWidth - 6) / 2; // 2 bars per day with a small gap

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-44 w-full"
      role="img"
      aria-label={`7-day effort: ${aName} vs ${bName}`}
    >
      {/* Y axis ticks */}
      {[1, 2, 3, 4, 5].map((v) => {
        const y = padding.top + innerH - (v / 5) * innerH;
        return (
          <g key={v}>
            <line
              x1={padding.left}
              y1={y}
              x2={width - padding.right}
              y2={y}
              className="stroke-border"
              strokeWidth={1}
              strokeDasharray={v === 5 ? "" : "2 4"}
            />
            <text
              x={padding.left - 6}
              y={y + 3}
              textAnchor="end"
              className="fill-muted-foreground text-[9px]"
            >
              {v}
            </text>
          </g>
        );
      })}

      {/* Bars */}
      {series.map((d, i) => {
        const xBase = padding.left + i * dayWidth + 3;
        const aHeight = d.a ? (d.a / 5) * innerH : 0;
        const bHeight = d.b ? (d.b / 5) * innerH : 0;
        const dateLabel = new Date(d.date).toLocaleDateString(undefined, {
          weekday: "short",
        });
        return (
          <g key={d.date}>
            {/* Partner A bar */}
            <rect
              x={xBase}
              y={padding.top + innerH - aHeight}
              width={barW}
              height={aHeight || 4}
              rx={2}
              className={d.a ? "fill-emerald-500" : "fill-emerald-500/15 stroke-emerald-500/40"}
              strokeDasharray={d.a ? "" : "2 2"}
            />
            {/* Partner B bar */}
            <rect
              x={xBase + barW + 2}
              y={padding.top + innerH - bHeight}
              width={barW}
              height={bHeight || 4}
              rx={2}
              className={d.b ? "fill-violet-500" : "fill-violet-500/15 stroke-violet-500/40"}
              strokeDasharray={d.b ? "" : "2 2"}
            />
            {/* Day label */}
            <text
              x={xBase + (dayWidth - 6) / 2}
              y={height - 8}
              textAnchor="middle"
              className="fill-muted-foreground text-[10px]"
            >
              {dateLabel}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
