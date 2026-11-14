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
  if (moduleId === "DM-RET3") {
    if (key === "alpha_nom") return spec.controlled === true;
    return true;
  }
  return true;
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
