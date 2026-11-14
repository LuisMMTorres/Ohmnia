import { formatEng } from "../format";

export interface BenchMarker {
  label: string;
  v: { value: number; unit: string };
  i: { value: number; unit: string };
}

export interface BenchScale {
  /** Vertical range for the plot: fitted to the model curves. */
  range: [number, number];
  /** Datasheet points drawn on the plot. */
  inside: BenchMarker[];
  /** Datasheet points left out because they would squash the curves; listed under the plot. */
  outside: string[];
}

/** How far above the curves a datasheet point may sit and still stretch the axis to include it. */
const STRETCH = 1.5;

/**
 * Vertical scale that keeps the device characteristic readable: it follows the model curves,
 * and a datasheet point far outside them is listed instead of compressing the plot.
 */
export function fitScale(
  curves: (number | null)[][],
  markers: BenchMarker[],
  xMax: number,
  log: boolean,
): BenchScale {
  const values = curves.flat().filter((v): v is number => v != null && Number.isFinite(v));
  const positive = values.filter((v) => v > 0);
  const top = values.length ? Math.max(...values) : 1;
  const inside: BenchMarker[] = [];
  const outside: string[] = [];
  let hi = top > 0 ? top : 1;
  let lo: number;
  if (log) {
    lo = positive.length ? Math.max(Math.min(...positive), hi * 1e-12) : hi * 1e-9;
  } else {
    lo = Math.min(0, ...values);
  }
  for (const m of markers) {
    const y = m.i.value;
    const text = `${m.label}: ${formatEng(m.v.value, m.v.unit, 3)}, ${formatEng(y, m.i.unit, 3)}`;
    if (m.v.value > xMax || y > top * STRETCH || (log && y < lo)) {
      outside.push(text);
    } else {
      inside.push(m);
      hi = Math.max(hi, y);
    }
  }
  if (log) return { range: [lo, hi * 2], inside, outside };
  const span = hi - lo || 1;
  return { range: [lo === 0 ? 0 : lo - 0.05 * span, hi + 0.08 * span], inside, outside };
}
