import { useEffect, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { formatEng } from "../format";

export interface Trace {
  name: string;
  unit: string;
  values: (number | null)[];
  /** Draw markers only (e.g. datasheet points), no line. */
  points?: boolean;
}

interface Props {
  x: number[];
  xUnit: string;
  xLabel: string;
  xLog?: boolean;
  yLog?: boolean;
  traces: Trace[];
  height?: number;
}

// Categorical palette with good contrast on light and dark backgrounds.
function isDecade(v: number): boolean {
  const e = Math.log10(v);
  return Math.abs(e - Math.round(e)) < 1e-6;
}

const COLORS = ["#2a7de1", "#e5533d", "#2fa36b", "#9b59d0", "#d99a00", "#1fa3b5", "#c2417e"];

export function SignalPlot({
  x,
  xUnit,
  xLabel,
  xLog = false,
  yLog = false,
  traces,
  height = 360,
}: Props) {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = container.current;
    if (!el || traces.length === 0) return;
    const units = [...new Set(traces.map((t) => t.unit))];
    const opts: uPlot.Options = {
      width: el.clientWidth,
      height,
      scales: {
        ...Object.fromEntries(
          [...new Set(traces.map((t) => t.unit || "1"))].map((u) => [u, { distr: yLog ? 3 : 1 }]),
        ),
        x: {
          time: false,
          distr: xLog ? 3 : 1,
          // Exact data range: uPlot would otherwise round a log axis out to whole decades.
          range: (_u, min, max) => [min, max],
        },
      },
      axes: [
        {
          label: `${xLabel} (${xUnit})`,
          stroke: "currentColor",
          grid: { stroke: "rgba(128,128,128,0.2)" },
          // On log axes, label only whole decades (uPlot passes null for unlabelled ticks).
          values: (_u, splits) =>
            splits.map((v) => (v == null || (xLog && !isDecade(v)) ? "" : formatEng(v, xUnit, 3))),
        },
        ...units.map((unit, i) => ({
          scale: unit || "1",
          side: i === 0 ? 3 : 1,
          size: 70,
          stroke: "currentColor",
          grid: { show: i === 0, stroke: "rgba(128,128,128,0.2)" },
          values: (_u: uPlot, splits: number[]) =>
            splits.map((v) => (v == null || (yLog && !isDecade(v)) ? "" : formatEng(v, unit, 3))),
        })),
      ],
      series: [
        { label: xLabel, value: (_u, v) => (v == null ? "—" : formatEng(v, xUnit, 4)) },
        ...traces.map((t, i) => ({
          label: t.name,
          scale: t.unit || "1",
          stroke: COLORS[i % COLORS.length],
          width: t.points ? 0 : 1.5,
          ...(t.points
            ? {
                paths: () => null,
                points: { show: true, size: 9, fill: COLORS[i % COLORS.length] },
              }
            : {}),
          value: (_u: uPlot, v: number | null) => (v == null ? "—" : formatEng(v, t.unit, 4)),
        })),
      ],
      cursor: { drag: { x: true, y: false } },
    };
    const data = [x, ...traces.map((t) => t.values)] as uPlot.AlignedData;
    const plot = new uPlot(opts, data, el);
    const observer = new ResizeObserver(() => plot.setSize({ width: el.clientWidth, height }));
    observer.observe(el);
    return () => {
      observer.disconnect();
      plot.destroy();
    };
  }, [x, xUnit, xLabel, xLog, yLog, traces, height]);

  return <div ref={container} className="signal-plot" />;
}
