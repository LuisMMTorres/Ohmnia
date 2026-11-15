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

const UNIT_SYMBOLS: Record<string, string> = {
  ohm: "Ω",
  degC: "°C",
  degree_Celsius: "°C",
  uA: "µA",
  us: "µs",
  uF: "µF",
  "K/W": "K/W",
  "A**2*s": "A²s",
  "A/us": "A/µs",
  percent: "%",
  dimensionless: "",
  kohm: "kΩ",
  uS: "µS",
  "A/V**2": "A/V²",
  "percent/K": "%/K",
  "W/K": "W/K",
  "1/cm**3": "cm⁻³",
  "1/cm**3/K**1.5": "cm⁻³·K⁻³ᐟ²",
  "cm**2": "cm²",
  "cm**2/s": "cm²/s",
  um: "µm",
  deg: "°",
  mohm: "mΩ",
  "A*V": "VA",
  "V*A": "VA",
};

const SUPERSCRIPT: Record<string, string> = {
  "-": "⁻",
  "0": "⁰",
  "1": "¹",
  "2": "²",
  "3": "³",
  "4": "⁴",
  "5": "⁵",
  "6": "⁶",
  "7": "⁷",
  "8": "⁸",
  "9": "⁹",
};

/** "1,48·10¹⁰": scientific notation for quantities without an SI prefix (concentrations). */
export function formatSci(value: number, digits = 3): string {
  const exp = Math.floor(Math.log10(Math.abs(value)));
  const mantissa = Number((value / 10 ** exp).toPrecision(digits));
  const sup = [...String(exp)].map((c) => SUPERSCRIPT[c] ?? c).join("");
  if (Math.abs(mantissa) === 1) return `${mantissa < 0 ? "−" : ""}10${sup}`;
  return `${String(mantissa).replace(".", ",")}·10${sup}`;
}

export function unitSymbol(unit: string): string {
  return UNIT_SYMBOLS[unit] ?? unit;
}

/** Datasheet value as written (no prefix rescaling): "1,1 V", "5 µA", "150 °C". */
export function formatRaw(value: number | null, unit: string): string {
  if (value == null) return "—";
  const sym = unitSymbol(unit);
  return `${Number(value.toPrecision(6))}`.replace(".", ",") + (sym ? ` ${sym}` : "");
}

const PREFIX_FACTOR: Record<string, number> = {
  p: 1e-12,
  n: 1e-9,
  µ: 1e-6,
  m: 1e-3,
  k: 1e3,
  M: 1e6,
};

export function formatEng(value: number, unit: string, digits = 3): string {
  let sym = unitSymbol(unit);
  // Densities such as V/√Hz take the prefix on the numerator (nV/√Hz).
  const slash = sym.indexOf("/");
  if (slash > 0 && PREFIXABLE.has(sym.slice(0, slash)))
    return formatEng(value, sym.slice(0, slash), digits) + sym.slice(slash);
  // A prefixed unit ("µF", "mH", "kΩ") is brought to its base so the prefix is chosen again.
  const factor = PREFIX_FACTOR[sym.charAt(0)];
  if (factor !== undefined && PREFIXABLE.has(sym.slice(1))) {
    value *= factor;
    sym = sym.slice(1);
  }
  const suffix = sym ? ` ${sym}` : "";
  if (!Number.isFinite(value)) return `${value}${suffix}`;
  if (value === 0 || !PREFIXABLE.has(sym)) {
    const mag = Math.abs(value);
    if (value !== 0 && (mag >= 1e5 || mag < 1e-3)) return formatSci(value, digits) + suffix;
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
