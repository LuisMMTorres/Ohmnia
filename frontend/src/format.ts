/** Engineering notation with decimal comma (pt-BR), mirroring backend core/units.format_eng. */

const PREFIXES: Record<number, string> = {
  [-15]: "f",
  [-12]: "p",
  [-9]: "n",
  [-6]: "µ",
  [-3]: "m",
  0: "",
  3: "k",
  6: "M",
  9: "G",
  12: "T",
};

const PREFIXABLE = new Set(["V", "A", "W", "VA", "var", "Ω", "S", "F", "H", "Hz", "s", "J", "C"]);

export function unitSymbol(unit: string): string {
  return unit === "ohm" ? "Ω" : unit;
}

export function formatEng(value: number, unit: string, digits = 3): string {
  const sym = unitSymbol(unit);
  const suffix = sym ? ` ${sym}` : "";
  if (!Number.isFinite(value)) return `${value}${suffix}`;
  if (value === 0 || !PREFIXABLE.has(sym)) {
    return `${Number(value.toPrecision(digits))}`.replace(".", ",") + suffix;
  }
  let exp = Math.floor(Math.log10(Math.abs(value)) / 3) * 3;
  exp = Math.max(-15, Math.min(12, exp));
  let mantissa = value / 10 ** exp;
  if (Math.abs(Number(mantissa.toPrecision(digits))) >= 1000 && exp < 12) {
    exp += 3;
    mantissa = value / 10 ** exp;
  }
  const text = `${Number(mantissa.toPrecision(digits))}`.replace(".", ",");
  return `${text} ${PREFIXES[exp]}${sym}`;
}
