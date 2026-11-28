// Order of the symbols inside a group of the component library.

/** The potentiometer and the trimpot right after the resistor; the op-amp before the 555. */
const PALETTE_FIRST = ["resistor", "potentiometer", "trimpot", "opamp", "timer555"];

export function sortPalette<T extends { kind: string }>(symbols: T[]): T[] {
  const rank = (k: string) => {
    const i = PALETTE_FIRST.indexOf(k);
    return i < 0 ? PALETTE_FIRST.length : i;
  };
  return symbols
    .map((s, i) => ({ s, i }))
    .sort((a, b) => rank(a.s.kind) - rank(b.s.kind) || a.i - b.i)
    .map(({ s }) => s);
}
