/**
 * Oscilloscope view: several traces on one or two vertical axes (one per unit), zoom by
 * dragging (double click resets), and two measurement cursors (click: A, Shift+click: B).
 */
import { useEffect, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { formatEng } from "../format";

export const TRACE_COLORS = [
  "#2a7de1",
  "#e5533d",
  "#2fa36b",
  "#9b59d0",
  "#d99a00",
  "#1fa3b5",
  "#c2417e",
  "#6b7a8f",
];

export interface ScopeTrace {
  name: string;
  unit: string;
  x: number[];
  y: (number | null)[];
  color?: string;
  width?: number;
}

export interface Cursors {
  a: number | null;
  b: number | null;
}

interface Props {
  traces: ScopeTrace[];
  xUnit: string;
  xLabel: string;
  xLog?: boolean;
  height?: number;
  cursors: Cursors;
  onCursor: (which: "a" | "b", x: number) => void;
  onZoom?: (range: [number, number] | null) => void;
}

function isDecade(v: number): boolean {
  const e = Math.log10(v);
  return Math.abs(e - Math.round(e)) < 1e-6;
}

/** Align traces with different x grids (adaptive transient steps) on one shared x. */
export function align(traces: ScopeTrace[]): uPlot.AlignedData {
  const first = traces[0]!;
  const sameX = traces.every((t) => t.x === first.x);
  if (sameX) return [first.x, ...traces.map((t) => t.y)] as uPlot.AlignedData;
  return uPlot.join(traces.map((t) => [t.x, t.y] as uPlot.AlignedData));
}

export function Scope({
  traces,
  xUnit,
  xLabel,
  xLog = false,
  height = 380,
  cursors,
  onCursor,
  onZoom,
}: Props) {
  const el = useRef<HTMLDivElement>(null);
  const plotRef = useRef<uPlot | null>(null);
  const cursorRef = useRef(cursors);
  cursorRef.current = cursors;
  const cb = useRef({ onCursor, onZoom });
  cb.current = { onCursor, onZoom };

  useEffect(() => {
    const host = el.current;
    if (!host || traces.length === 0) return;
    const units = [...new Set(traces.map((t) => t.unit || "1"))].slice(0, 2);
    const drawCursors = (u: uPlot) => {
      const ctx = u.ctx;
      const { top, height: h } = u.bbox;
      for (const [k, color] of [
        ["a", "#e5533d"],
        ["b", "#2fa36b"],
      ] as const) {
        const v = cursorRef.current[k];
        if (v == null) continue;
        const x = u.valToPos(v, "x", true);
        ctx.save();
        ctx.strokeStyle = color;
        ctx.setLineDash([6, 4]);
        ctx.lineWidth = 1.5 * devicePixelRatio;
        ctx.beginPath();
        ctx.moveTo(x, top);
        ctx.lineTo(x, top + h);
        ctx.stroke();
        ctx.fillStyle = color;
        ctx.font = `${12 * devicePixelRatio}px sans-serif`;
        ctx.fillText(k.toUpperCase(), x + 4 * devicePixelRatio, top + 14 * devicePixelRatio);
        ctx.restore();
      }
    };
    const opts: uPlot.Options = {
      width: host.clientWidth,
      height,
      scales: {
        x: { time: false, distr: xLog ? 3 : 1, range: (_u, min, max) => [min, max] },
        ...Object.fromEntries(units.map((u) => [u, {}])),
      },
      axes: [
        {
          label: `${xLabel} (${xUnit})`,
          stroke: "currentColor",
          grid: { stroke: "rgba(128,128,128,0.2)" },
          values: (_u, splits) =>
            splits.map((v) => (v == null || (xLog && !isDecade(v)) ? "" : formatEng(v, xUnit, 3))),
        },
        ...units.map((unit, i) => ({
          scale: unit,
          side: i === 0 ? 3 : 1,
          size: 72,
          stroke: "currentColor",
          grid: { show: i === 0, stroke: "rgba(128,128,128,0.2)" },
          values: (_u: uPlot, splits: number[]) =>
            splits.map((v) => (v == null ? "" : formatEng(v, unit === "1" ? "" : unit, 3))),
        })),
      ],
      series: [
        { label: xLabel, value: (_u, v) => (v == null ? "—" : formatEng(v, xUnit, 4)) },
        ...traces.map((t, i) => ({
          label: t.name,
          scale: units.includes(t.unit || "1") ? t.unit || "1" : units[0],
          stroke: t.color ?? TRACE_COLORS[i % TRACE_COLORS.length],
          width: t.width ?? 1.5,
          spanGaps: true,
          value: (_u: uPlot, v: number | null) => (v == null ? "—" : formatEng(v, t.unit, 4)),
        })),
      ],
      cursor: { drag: { x: true, y: false } },
      // many runs (Monte Carlo, STEP): the per-series legend would bury the plot
      legend: { show: traces.length <= 12 },
      hooks: {
        draw: [drawCursors],
        setScale: [
          (u, k) => {
            if (k !== "x") return;
            const min = u.scales.x?.min;
            const max = u.scales.x?.max;
            if (min != null && max != null) cb.current.onZoom?.([min, max]);
          },
        ],
      },
    };
    const plot = new uPlot(opts, align(traces), host);
    plotRef.current = plot;
    let down: [number, number] | null = null;
    const over = plot.over;
    const md = (e: MouseEvent) => (down = [e.clientX, e.clientY]);
    const mu = (e: MouseEvent) => {
      if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 3) return;
      const x = plot.posToVal(e.offsetX, "x");
      cb.current.onCursor(e.shiftKey ? "b" : "a", x);
    };
    const dbl = () => cb.current.onZoom?.(null);
    over.addEventListener("mousedown", md);
    over.addEventListener("mouseup", mu);
    over.addEventListener("dblclick", dbl);
    const observer = new ResizeObserver(() => plot.setSize({ width: host.clientWidth, height }));
    observer.observe(host);
    return () => {
      observer.disconnect();
      over.removeEventListener("mousedown", md);
      over.removeEventListener("mouseup", mu);
      over.removeEventListener("dblclick", dbl);
      plot.destroy();
      plotRef.current = null;
    };
  }, [traces, xUnit, xLabel, xLog, height]);

  useEffect(() => {
    plotRef.current?.redraw(false);
  }, [cursors.a, cursors.b]);

  return <div ref={el} className="signal-plot scope" />;
}

/** Value of a trace at x (linear interpolation; the trace x must be increasing). */
export function valueAt(t: ScopeTrace, x: number): number | null {
  const xs = t.x;
  if (!xs.length || x < xs[0]! || x > xs[xs.length - 1]!) return null;
  let lo = 0;
  let hi = xs.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (xs[mid]! <= x) lo = mid;
    else hi = mid;
  }
  const y0 = t.y[lo];
  const y1 = t.y[hi];
  if (y0 == null || y1 == null) return y0 ?? y1 ?? null;
  const span = xs[hi]! - xs[lo]!;
  return span ? y0 + ((y1 - y0) * (x - xs[lo]!)) / span : y0;
}
