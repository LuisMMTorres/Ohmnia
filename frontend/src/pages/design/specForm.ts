/** Spec form generated from the module's JSON schema (pure helpers, tested in specForm.test.ts). */
import type { JsonSchema, Quantity } from "../../api";

export type Field =
  | { key: string; kind: "quantity"; unit: string; min?: number; max?: number }
  | { key: string; kind: "number"; min?: number; max?: number }
  | { key: string; kind: "enum"; options: (string | number)[] }
  | { key: string; kind: "bool" };

function resolve(schema: JsonSchema, root: JsonSchema): JsonSchema {
  if (schema.$ref) {
    const name = schema.$ref.split("/").pop() ?? "";
    return { ...(root.$defs?.[name] ?? {}), ...schema, $ref: undefined };
  }
  return schema;
}

export function isQuantity(v: unknown): v is Quantity {
  return (
    typeof v === "object" &&
    v !== null &&
    typeof (v as Quantity).value === "number" &&
    typeof (v as Quantity).unit === "string"
  );
}

/** One field per property, in schema order; the unit of a quantity comes from its default. */
export function fieldsFromSchema(schema: JsonSchema, defaults: Record<string, unknown>): Field[] {
  const fields: Field[] = [];
  for (const [key, raw] of Object.entries(schema.properties ?? {})) {
    const prop = resolve(raw, schema);
    const def = defaults[key];
    if (prop.enum) {
      fields.push({ key, kind: "enum", options: prop.enum });
    } else if (prop.anyOf?.every((s) => s.const !== undefined)) {
      fields.push({
        key,
        kind: "enum",
        options: prop.anyOf.map((s) => s.const as string | number),
      });
    } else if (isQuantity(def)) {
      fields.push({ key, kind: "quantity", unit: def.unit });
    } else if (prop.type === "boolean" || typeof def === "boolean") {
      fields.push({ key, kind: "bool" });
    } else if (prop.type === "number" || prop.type === "integer" || typeof def === "number") {
      fields.push({
        key,
        kind: "number",
        min: prop.minimum ?? prop.exclusiveMinimum,
        max: prop.maximum ?? prop.exclusiveMaximum,
      });
    }
  }
  return fields;
}

/** Slider span for the "limites" panel: the schema bounds, else ¼× to 4× the default. */
export function sliderRange(field: Field, def: number): [number, number] {
  const lo = "min" in field && field.min !== undefined ? field.min : def > 0 ? def / 4 : 0;
  let hi = "max" in field && field.max !== undefined ? field.max : def > 0 ? def * 4 : 10;
  if (hi <= lo) hi = lo + 1;
  return [lo, hi];
}

/** Reasonable slider step: about 200 steps over the span, rounded to 1, 2 or 5 × 10ⁿ. */
export function sliderStep(lo: number, hi: number): number {
  const raw = (hi - lo) / 200;
  const exp = Math.floor(Math.log10(raw));
  const m = raw / 10 ** exp;
  const nice = m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10;
  return nice * 10 ** exp;
}

/** Fields that only make sense for some topologies are hidden when they do not apply. */
export function visible(moduleId: string, key: string, spec: Record<string, unknown>): boolean {
  if (moduleId === "DM-RET1") {
    if (key === "L_factor") return spec.filter === "LC";
    if (key === "ripple_pct" || key === "cap_series") return spec.filter !== "nenhum";
    return true;
  }
  if (moduleId === "DM-RETC1") {
    if (key === "freewheel") return spec.topology === "meia_onda";
    return true;
  }
  if (moduleId === "DM-ZEN") {
    if (key === "VBE" || key === "beta_ideal" || key === "Rth_cs")
      return spec.variant === "transistor";
    return true;
  }
  if (moduleId === "DM-LIN") {
    if (key === "res_series") return spec.kind === "ajustavel";
    if (key === "vo_window_pct") return spec.kind !== "ajustavel";
    return true;
  }
  if (moduleId === "DM-BIAS") {
    const cfg = spec.config as string | undefined;
    const fet = cfg === "mos_divisor" || cfg === "jfet_auto" || cfg === "jfet_divisor";
    if (key === "R_gate") return fet;
    if (key === "divider_k") return cfg === "divisor" || !cfg;
    if (key === "VBE" || key === "beta_ideal") return !fet;
    if (key === "kE") return cfg !== "fixa" && cfg !== "jfet_auto";
    return true;
  }
  if (moduleId === "DM-SSA") {
    const c = spec.config as string | undefined;
    if (key === "Av") return c === "EC" || c === "FC" || c === "FCJ" || !c;
    if (key === "VBE" || key === "beta_ideal") return c !== "FC" && c !== "FCJ";
    return true;
  }
  if (moduleId === "DM-PA") {
    if (key === "IQ") return spec.cls === "AB" || !spec.cls;
    if (key === "darlington") return spec.cls !== "A";
    return true;
  }
  if (moduleId === "DM-CHAVE") {
    const bjt = spec.device !== "mosfet";
    if (key === "overdrive" || key === "VBE" || key === "beta_ideal") return bjt;
    return true;
  }
  if (moduleId === "DM-FORMA") {
    const k = (spec.kind as string | undefined) ?? "ceifador_paralelo";
    if (key === "stages" || key === "ripple_pct" || key === "cap_series")
      return k === "multiplicador";
    if (key === "VB") return k !== "multiplicador";
    if (key === "R") return k === "ceifador_paralelo" || k === "ceifador_duplo";
    if (key === "C") return k === "grampeador";
    return true;
  }
  if (moduleId === "DM-RET3") {
    if (key === "alpha_nom") return spec.controlled === true;
    return true;
  }
  return visiblePhase5(moduleId, key, spec);
}

function visiblePhase5(moduleId: string, key: string, spec: Record<string, unknown>): boolean {
  if (moduleId === "DM-OPA") {
    const c = (spec.config as string | undefined) ?? "inversor";
    if (key === "Av")
      return c !== "seguidor" && c !== "transimpedancia" && c !== "transcondutancia";
    if (key === "Rt" || key === "Iin") return c === "transimpedancia";
    if (key === "Gm" || key === "R_load_fb") return c === "transcondutancia";
    if (key === "Vin") return c !== "transimpedancia";
    return true;
  }
  if (moduleId === "DM-FIL") {
    const k = (spec.kind as string | undefined) ?? "passa_baixas";
    const a = (spec.approx as string | undefined) ?? "butterworth";
    const lc = spec.realization === "passivo_lc";
    if (key === "B") return k === "passa_faixa" || k === "rejeita_faixa";
    if (key === "ripple_db") return a === "chebyshev" || a === "eliptico";
    if (key === "R0") return lc;
    if (key === "R_base") return spec.realization === "variaveis_estado";
    if (key === "C_base" || key === "VCC" || key === "res_series") return !lc;
    return true;
  }
  if (moduleId === "DM-OPNL") {
    const c = (spec.config as string | undefined) ?? "schmitt_inversor";
    if (key === "device" || key === "Vref") return c === "comparador";
    if (key === "Rp") return c === "comparador" && spec.device === "comparador";
    if (key === "Vc" || key === "VH") return c.startsWith("schmitt");
    if (key === "G") return c.startsWith("retificador") || c === "limitador";
    if (key === "Vlim") return c === "limitador";
    if (key === "Vin_dc" || key === "VBE") return c === "logaritmico";
    if (key === "Vm" || key === "f") return c !== "logaritmico";
    return true;
  }
  if (moduleId === "DM-OSC") {
    const c = (spec.config as string | undefined) ?? "wien";
    const tbj = c === "multivibrador_tbj";
    if (key === "duty") return c === "ne555_astavel";
    if (key === "t_w") return c === "ne555_monoestavel";
    if (key === "f") return c !== "ne555_monoestavel";
    if (key === "gain_margin") return c === "wien" || c === "deslocamento_fase";
    if (key === "beta") return c === "astavel_ampop";
    if (key === "R_base") return c === "wien" || c === "astavel_ampop";
    if (key === "VCC") return !tbj;
    if (key === "VCC_tbj" || key === "RC_tbj" || key === "VBE" || key === "VCEsat") return tbj;
    return true;
  }
  if (moduleId === "DM-INST") {
    const c = (spec.config as string | undefined) ?? "voltimetro";
    const tx = c === "transmissor_4_20";
    if (key === "V_max") return c === "voltimetro" || c === "potencia";
    if (key === "R_in") return c === "voltimetro";
    if (key === "I_max" || key === "V_sh") return c === "amperimetro" || c === "potencia";
    if (key === "Vs_min" || key === "Vs_max") return tx || c === "condicionamento";
    if (key === "V_ref" || key === "R_sense") return tx;
    if (key === "R_loop") return tx || c === "receptor_4_20";
    if (key === "V_exc" || key === "R0" || key === "x_max") return c === "ponte_wheatstone";
    if (key === "V_fs") return !tx;
    return true;
  }
  return true;
}

const SECONDS: Record<string, number> = { s: 1, ms: 1e-3, us: 1e-6, µs: 1e-6, ns: 1e-9 };

/** Span of the analytic traces in seconds: trace_period, else one period of spec.f. */
export function tracePeriod(
  period: { value: number; unit: string } | null | undefined,
  f: { value: number; unit: string } | undefined,
): number {
  if (period && SECONDS[period.unit] !== undefined) return period.value * SECONDS[period.unit]!;
  const hz = f ? f.value * ({ Hz: 1, kHz: 1e3, MHz: 1e6 }[f.unit] ?? 1) : 60;
  return 1 / hz;
}

/** Simulated |H| resampled on the analytic frequency grid (interpolated in log f). */
export function resampleLog(fSim: number[], values: number[], fOut: number[]): number[] {
  return resample(
    fSim.map((v) => Math.log10(v)),
    values,
    fOut.map((v) => Math.log10(v)),
  );
}

/** Simulated trace resampled on the analytic time grid (both span one period from 0). */
export function resample(tSim: number[], values: number[], tOut: number[]): number[] {
  const out: number[] = [];
  let j = 0;
  for (const t of tOut) {
    while (j < tSim.length - 2 && tSim[j + 1]! < t) j++;
    const t0 = tSim[j]!;
    const t1 = tSim[j + 1] ?? t0;
    const v0 = values[j]!;
    const v1 = values[j + 1] ?? v0;
    out.push(t1 === t0 ? v0 : v0 + ((v1 - v0) * (t - t0)) / (t1 - t0));
  }
  return out;
}
