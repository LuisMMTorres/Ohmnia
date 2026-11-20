/** Parts damaged in the last simulation: ratings exceeded, grouped by part. */
import type { DamageOut } from "../api";
import type { Glow } from "./symbols";

export interface PartDamage {
  ref: string;
  causes: string[];
  advice: string[];
  sources: string[];
  /** Some rating used is still "a verificar" in the catalogue. */
  unreviewed: boolean;
}

/**
 * One entry per damaged part, in the order of the schematic. LEDs and lamps that the brightness
 * calculation already marks as burnt join the list with their own text.
 */
export function damageByRef(
  damage: DamageOut[],
  glows: Record<string, Glow>,
  glowCause: (ref: string) => string | null,
  order: string[],
): PartDamage[] {
  const out = new Map<string, PartDamage>();
  const entry = (ref: string) => {
    let e = out.get(ref);
    if (!e) {
      e = { ref, causes: [], advice: [], sources: [], unreviewed: false };
      out.set(ref, e);
    }
    return e;
  };
  for (const d of damage) {
    const e = entry(d.ref);
    if (!e.causes.includes(d.cause)) e.causes.push(d.cause);
    if (d.advice && !e.advice.includes(d.advice)) e.advice.push(d.advice);
    if (d.source && !e.sources.includes(d.source)) e.sources.push(d.source);
    e.unreviewed ||= !d.reviewed;
  }
  for (const [ref, g] of Object.entries(glows)) {
    if (!g.burnt) continue;
    const text = glowCause(ref);
    const e = entry(ref);
    if (text && !e.causes.includes(text)) e.causes.push(text);
    const tip =
      "Coloque um resistor em série que limite a corrente (R = (V − VF)/IF) ou use uma fonte de " +
      "tensão menor.";
    if (!e.advice.includes(tip)) e.advice.push(tip);
  }
  const pos = (r: string) => {
    const i = order.indexOf(r);
    return i < 0 ? order.length : i;
  };
  return [...out.values()].sort((a, b) => pos(a.ref) - pos(b.ref));
}
