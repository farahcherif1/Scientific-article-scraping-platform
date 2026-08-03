import { useState } from "react";
import type { YearCount } from "../api/articles";

interface Props {
  data: YearCount[];
}

const CHART_HEIGHT = 180;
const BAR_GAP = 14;
const BAR_RADIUS = 4;
const AXIS_LABEL_WIDTH = 36;
const GRIDLINE_COUNT = 4;

/** Picks a "nice" axis ceiling (e.g. 47 -> 60, 118 -> 120) so gridline labels read as round numbers. */
function niceCeiling(max: number): number {
  if (max <= 0) return GRIDLINE_COUNT;
  const roughStep = max / GRIDLINE_COUNT;
  const magnitude = 10 ** Math.floor(Math.log10(roughStep));
  const normalized = roughStep / magnitude;
  const niceStep = (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) * magnitude;
  return Math.ceil(max / niceStep) * niceStep;
}

export default function ArticlesPerYearChart({ data }: Props) {
  const [hovered, setHovered] = useState<number | null>(null);

  if (data.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-slate-400">
        No dated articles to chart yet.
      </div>
    );
  }

  const maxCount = Math.max(...data.map((d) => d.count), 1);
  const axisMax = niceCeiling(maxCount);
  const gridlineValues = Array.from({ length: GRIDLINE_COUNT + 1 }, (_, i) =>
    Math.round((axisMax / GRIDLINE_COUNT) * i)
  ).reverse();

  const barWidth = Math.max(24, Math.min(56, 480 / data.length - BAR_GAP));
  const plotWidth = data.length * (barWidth + BAR_GAP);
  const totalWidth = plotWidth + AXIS_LABEL_WIDTH;

  return (
    <div className="w-full overflow-x-auto">
      <svg
        role="img"
        aria-label="Articles published per year"
        width={totalWidth}
        height={CHART_HEIGHT + 28}
        className="min-w-full"
      >
        {/* Gridlines + axis labels */}
        {gridlineValues.map((value) => {
          const y = CHART_HEIGHT - (value / axisMax) * CHART_HEIGHT;
          return (
            <g key={value}>
              <text
                x={AXIS_LABEL_WIDTH - 10}
                y={y + 4}
                textAnchor="end"
                className="fill-slate-400 text-[11px]"
              >
                {value}
              </text>
              <line
                x1={AXIS_LABEL_WIDTH}
                x2={totalWidth}
                y1={y}
                y2={y}
                className="stroke-slate-200"
                strokeWidth={1}
                strokeDasharray="3 3"
              />
            </g>
          );
        })}

        {data.map((d, i) => {
          const barHeight = axisMax > 0 ? Math.max(2, (d.count / axisMax) * CHART_HEIGHT) : 2;
          const x = AXIS_LABEL_WIDTH + i * (barWidth + BAR_GAP);
          const y = CHART_HEIGHT - barHeight;
          const isHovered = hovered === i;
          return (
            <g
              key={d.year}
              onMouseEnter={() => setHovered(i)}
              onMouseLeave={() => setHovered(null)}
              className="cursor-default"
            >
              {isHovered && (
                <text
                  x={x + barWidth / 2}
                  y={y - 8}
                  textAnchor="middle"
                  className="fill-slate-700 text-xs font-semibold"
                >
                  {d.count}
                </text>
              )}
              <rect
                x={x}
                y={y}
                width={barWidth}
                height={barHeight}
                rx={BAR_RADIUS}
                className={isHovered ? "fill-emerald-700" : "fill-emerald-600"}
              />
              <text
                x={x + barWidth / 2}
                y={CHART_HEIGHT + 18}
                textAnchor="middle"
                className="fill-slate-500 text-xs"
              >
                {d.year}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
