import { AxisScale } from "../api";
import { formatSci } from "../format";

export interface Series {
  points: [number, number][];
  label: string;
  kind?: "points" | "line";
  className?: string;
}

interface Props {
  series: Series[];
  xScale: AxisScale;
  yScale: AxisScale;
  xLabel: string;
  yLabel: string;
  width?: number;
  height?: number;
}

const M = { l: 58, r: 12, t: 10, b: 36 };

function axis(values: number[], scale: AxisScale): [number, number] {
  const v = scale === "log" ? values.filter((x) => x > 0).map(Math.log10) : values;
  let lo = Math.min(...v);
  let hi = Math.max(...v);
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return [0, 1];
  if (lo === hi) {
    lo -= 1;
    hi += 1;
  }
  const pad = (hi - lo) * 0.05;
  return [lo - pad, hi + pad];
}

function ticks(lo: number, hi: number, scale: AxisScale): number[] {
  if (scale === "log") {
    const out = [];
    for (let e = Math.ceil(lo); e <= Math.floor(hi); e++) out.push(e);
    return out;
  }
  const step = 10 ** Math.floor(Math.log10((hi - lo) / 4));
  const n = Math.ceil((hi - lo) / step / 5) * step;
  const out = [];
  for (let v = Math.ceil(lo / n) * n; v <= hi; v += n) out.push(Number(v.toPrecision(10)));
  return out;
}

/** Small XY plot with linear or logarithmic axes (datasheet curves, fit residuals). */
export function CurvePlot({
  series,
  xScale,
  yScale,
  xLabel,
  yLabel,
  width = 420,
  height = 260,
}: Props) {
  const all = series.flatMap((s) => s.points);
  if (all.length === 0) return null;
  const [x0, x1] = axis(
    all.map((p) => p[0]),
    xScale,
  );
  const [y0, y1] = axis(
    all.map((p) => p[1]),
    yScale,
  );
  const tx = (v: number) => (xScale === "log" ? Math.log10(v) : v);
  const ty = (v: number) => (yScale === "log" ? Math.log10(v) : v);
  const px = (v: number) => M.l + ((tx(v) - x0) / (x1 - x0)) * (width - M.l - M.r);
  const py = (v: number) => height - M.b - ((ty(v) - y0) / (y1 - y0)) * (height - M.t - M.b);
  const label = (t: number, scale: AxisScale) => formatSci(scale === "log" ? 10 ** t : t, 3);
  const ok = (p: [number, number]) =>
    (xScale === "lin" || p[0] > 0) && (yScale === "lin" || p[1] > 0);
  return (
    <svg
      className="curve-plot"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`${yLabel} × ${xLabel}`}
    >
      <rect
        x={M.l}
        y={M.t}
        width={width - M.l - M.r}
        height={height - M.t - M.b}
        className="frame"
      />
      {ticks(x0, x1, xScale).map((t) => {
        const x = M.l + ((t - x0) / (x1 - x0)) * (width - M.l - M.r);
        return (
          <g key={`x${t}`}>
            <line x1={x} x2={x} y1={M.t} y2={height - M.b} className="grid" />
            <text x={x} y={height - M.b + 14} className="tick" textAnchor="middle">
              {label(t, xScale)}
            </text>
          </g>
        );
      })}
      {ticks(y0, y1, yScale).map((t) => {
        const y = height - M.b - ((t - y0) / (y1 - y0)) * (height - M.t - M.b);
        return (
          <g key={`y${t}`}>
            <line x1={M.l} x2={width - M.r} y1={y} y2={y} className="grid" />
            <text x={M.l - 4} y={y + 4} className="tick" textAnchor="end">
              {label(t, yScale)}
            </text>
          </g>
        );
      })}
      <text x={(M.l + width - M.r) / 2} y={height - 4} className="axis-label" textAnchor="middle">
        {xLabel}
      </text>
      <text
        x={12}
        y={(M.t + height - M.b) / 2}
        className="axis-label"
        textAnchor="middle"
        transform={`rotate(-90 12 ${(M.t + height - M.b) / 2})`}
      >
        {yLabel}
      </text>
      {series.map((s, k) => {
        const pts = s.points.filter(ok);
        return s.kind === "line" ? (
          <polyline
            key={k}
            className={s.className ?? `series s${k}`}
            points={pts.map((p) => `${px(p[0])},${py(p[1])}`).join(" ")}
          >
            <title>{s.label}</title>
          </polyline>
        ) : (
          <g key={k} className={s.className ?? `series s${k}`}>
            <title>{s.label}</title>
            {pts.map((p, i) => (
              <circle key={i} cx={px(p[0])} cy={py(p[1])} r={2.6} />
            ))}
          </g>
        );
      })}
    </svg>
  );
}
