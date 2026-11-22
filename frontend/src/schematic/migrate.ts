import { spiceNumber } from "./sourceConfig";
import type { Schematic } from "./types";

/** Bring a circuit saved by an older version up to date:
 * - transformer: the turns ratio was Ns/Np in "n"; it is now Np/Ns in "ratio" (= 1/n).
 *   A non-numeric "n" (a {parameter} expression) stays, and the netlist still reads it.
 * Sources saved with the peak-to-peak field are read as RMS by sourceSettings. */
export function upgradeSchematic(s: Schematic): Schematic {
  let changed = false;
  const components = s.components.map((c) => {
    if (c.kind !== "transformer" || c.params.ratio || !c.params.n) return c;
    const n = spiceNumber(c.params.n, NaN);
    if (!Number.isFinite(n) || n <= 0) return c;
    changed = true;
    const params: Record<string, string> = {
      ...c.params,
      ratio: String(Number((1 / n).toPrecision(9))),
    };
    delete params.n;
    return { ...c, params };
  });
  return changed ? { ...s, components } : s;
}
