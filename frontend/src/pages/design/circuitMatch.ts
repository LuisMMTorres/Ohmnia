import type { CircuitElement, UserProbe } from "../../api";

/**
 * Element of the simulated circuit that a label of the drawing names: the element itself
 * ("C1"), a subcircuit instance without its X ("D1" → "XD1"), or the only element of a letter
 * ("R" → "RL" when the load is the only resistor).
 */
export function matchElement(label: string, elements: CircuitElement[]): CircuitElement | null {
  const key = label.trim().toLowerCase();
  if (!key || key.length > 8) return null;
  const real = elements.filter((e) => !e.sense);
  const exact = real.find((e) => e.name.toLowerCase() === key);
  if (exact) return exact;
  const sub = real.find((e) => e.letter === "X" && e.name.slice(1).toLowerCase() === key);
  if (sub) return sub;
  if (/^[a-z]$/.test(key)) {
    const same = real.filter((e) => e.letter.toLowerCase() === key);
    if (same.length === 1) return same[0] ?? null;
  }
  return null;
}

/** Short Portuguese description of a probe, as listed under the schematic. */
export function probeText(p: UserProbe, elements: CircuitElement[]): string {
  if (p.kind === "v") return `Tensão no nó ${p.a} (em relação à terra)`;
  if (p.kind === "vdiff") return `Tensão diferencial ${p.a} − ${p.b ?? "?"}`;
  const el = elements.find((e) => e.name === p.a);
  if (p.kind === "p") return `Potência em ${p.a}`;
  const pin = el && el.nodes.length > 2 ? ` (${el.pins[p.pin ?? 0] ?? ""})` : "";
  return `Corrente em ${p.a}${pin}`;
}

export function sameProbe(a: UserProbe, b: UserProbe): boolean {
  return (
    a.kind === b.kind &&
    a.a === b.a &&
    (a.b ?? null) === (b.b ?? null) &&
    (a.pin ?? 0) === (b.pin ?? 0)
  );
}
