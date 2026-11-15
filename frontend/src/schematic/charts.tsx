/** Small SVG charts: XY curves, spectrum stems and histograms (engineering tick labels). */
import { formatEng } from "../format";
import { TRACE_COLORS } from "./Scope";

const W = 720;
const H = 340;
const M = { l: 72, r: 16, t: 14, b: 42 };

function ticks(min: number, max: number, n = 6): number[] {
  if (!(max > min)) return [min];
  const raw = (max - min) / n;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step) out.push(v);
  return out;
}

function frame(
  xr: [number, number],
  yr: [number, number],
  xUnit: string,
  yUnit: string,
  xLabel: string,
  yLabel: string,
) {
  const sx = (x: number) => M.l + ((x - xr[0]) / (xr[1] - xr[0] || 1)) * (W - M.l - M.r);
  const sy = (y: number) => H - M.b - ((y - yr[0]) / (yr[1] - yr[0] || 1)) * (H - M.t - M.b);
  const axes = (
    <g className="chart-axes">
      {ticks(xr[0], xr[1]).map((v) => (
        <g key={`x${v}`}>
          <line x1={sx(v)} x2={sx(v)} y1={M.t} y2={H - M.b} className="grid" />
          <text x={sx(v)} y={H - M.b + 16} textAnchor="middle">
            {formatEng(v, xUnit, 3)}
          </text>
        </g>
      ))}
      {ticks(yr[0], yr[1]).map((v) => (
        <g key={`y${v}`}>
          <line x1={M.l} x2={W - M.r} y1={sy(v)} y2={sy(v)} className="grid" />
          <text x={M.l - 6} y={sy(v) + 4} textAnchor="end">
            {formatEng(v, yUnit, 3)}
          </text>
        </g>
      ))}
      <rect x={M.l} y={M.t} width={W - M.l - M.r} height={H - M.t - M.b} className="box" />
      <text x={(W + M.l) / 2} y={H - 6} textAnchor="middle">
        {xLabel}
      </text>
      <text
        x={14}
        y={(H - M.b) / 2}
        transform={`rotate(-90 14 ${(H - M.b) / 2})`}
        textAnchor="middle"
      >
        {yLabel}
      </text>
    </g>
  );
  return { sx, sy, axes };
}

function range(values: number[], pad = 0.05): [number, number] {
  const finite = values.filter(Number.isFinite);
  if (!finite.length) return [0, 1];
  let lo = Math.min(...finite);
  let hi = Math.max(...finite);
  if (lo === hi) [lo, hi] = [lo - 1, hi + 1];
  const d = (hi - lo) * pad;
  return [lo - d, hi + d];
}

export interface XYCurve {
  name: string;
  x: number[];
  y: number[];
}

export function XYPlot({
  curves,
  xUnit,
  yUnit,
  xLabel,
  yLabel,
}: {
  curves: XYCurve[];
  xUnit: string;
  yUnit: string;
  xLabel: string;
  yLabel: string;
}) {
  const xr = range(curves.flatMap((c) => c.x));
  const yr = range(curves.flatMap((c) => c.y));
  const { sx, sy, axes } = frame(xr, yr, xUnit, yUnit, xLabel, yLabel);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Gráfico XY">
      {axes}
      {curves.map((c, i) => (
        <polyline
          key={c.name}
          points={c.x.map((x, k) => `${sx(x).toFixed(1)},${sy(c.y[k]!).toFixed(1)}`).join(" ")}
          stroke={TRACE_COLORS[i % TRACE_COLORS.length]}
          fill="none"
          strokeWidth={1.4}
        />
      ))}
    </svg>
  );
}

export function StemPlot({
  x,
  y,
  xUnit,
  yUnit,
  marks = [],
}: {
  x: number[];
  y: number[];
  xUnit: string;
  yUnit: string;
  marks?: number[];
}) {
  const xr: [number, number] = [0, Math.max(...x, 1)];
  const yr: [number, number] = [0, Math.max(...y, 1e-30) * 1.08];
  const { sx, sy, axes } = frame(xr, yr, xUnit, yUnit, "frequência", "amplitude (pico)");
  const markSet = new Set(marks.map((m) => Math.round(m)));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Espectro">
      {axes}
      {x.map((f, k) =>
        y[k]! > yr[1] * 1e-4 ? (
          <line
            key={k}
            x1={sx(f)}
            x2={sx(f)}
            y1={sy(0)}
            y2={sy(y[k]!)}
            stroke={markSet.has(Math.round(f)) ? TRACE_COLORS[1] : TRACE_COLORS[0]}
            strokeWidth={1.5}
          />
        ) : null,
      )}
    </svg>
  );
}

export function Histogram({
  edges,
  counts,
  unit,
  nominal,
  label,
}: {
  edges: number[];
  counts: number[];
  unit: string;
  nominal: number | null;
  label: string;
}) {
  const xr: [number, number] = [edges[0] ?? 0, edges[edges.length - 1] ?? 1];
  const yr: [number, number] = [0, Math.max(...counts, 1) * 1.1];
  const { sx, sy, axes } = frame(xr, yr, unit, "", label, "execuções");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Histograma">
      {axes}
      {counts.map((n, k) => (
        <rect
          key={k}
          x={sx(edges[k]!) + 1}
          y={sy(n)}
          width={Math.max(sx(edges[k + 1]!) - sx(edges[k]!) - 2, 1)}
          height={sy(0) - sy(n)}
          fill={TRACE_COLORS[0]}
          opacity={0.75}
        />
      ))}
      {nominal != null && (
        <line
          x1={sx(nominal)}
          x2={sx(nominal)}
          y1={M.t}
          y2={H - M.b}
          stroke={TRACE_COLORS[1]}
          strokeDasharray="6 4"
          strokeWidth={1.5}
        />
      )}
    </svg>
  );
}
