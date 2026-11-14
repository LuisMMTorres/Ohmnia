import { describe, expect, it } from "vitest";
import type { JsonSchema } from "../../api";
import { fieldsFromSchema, resample, sliderRange, sliderStep, visible } from "./specForm";

const SCHEMA: JsonSchema = {
  $defs: { QuantityModel: { type: "object" } },
  properties: {
    topology: { enum: ["meia_onda", "ponte"], type: "string" },
    pulses: { enum: [3, 6, 12], type: "integer" },
    Vo: { $ref: "#/$defs/QuantityModel" },
    ripple_pct: { type: "number", exclusiveMinimum: 0, maximum: 50 },
    controlled: { type: "boolean" },
  },
};
const DEFAULTS = {
  topology: "ponte",
  pulses: 6,
  Vo: { value: 12, unit: "V" },
  ripple_pct: 5,
  controlled: true,
};

describe("fieldsFromSchema", () => {
  it("maps each property to a field kind, in schema order", () => {
    const f = fieldsFromSchema(SCHEMA, DEFAULTS);
    expect(f.map((x) => [x.key, x.kind])).toEqual([
      ["topology", "enum"],
      ["pulses", "enum"],
      ["Vo", "quantity"],
      ["ripple_pct", "number"],
      ["controlled", "bool"],
    ]);
    expect(f[2]).toMatchObject({ unit: "V" });
    expect(f[3]).toMatchObject({ min: 0, max: 50 });
  });
});

describe("sliders", () => {
  it("uses schema bounds, else a quarter to four times the default", () => {
    expect(sliderRange({ key: "r", kind: "number", min: 0, max: 50 }, 5)).toEqual([0, 50]);
    expect(sliderRange({ key: "Vo", kind: "quantity", unit: "V" }, 12)).toEqual([3, 48]);
  });
  it("rounds the step to 1, 2 or 5 × 10ⁿ", () => {
    expect(sliderStep(0, 50)).toBeCloseTo(0.2);
    expect(sliderStep(3, 48)).toBeCloseTo(0.2);
    expect(sliderStep(0, 1000)).toBeCloseTo(5);
  });
});

describe("visible", () => {
  it("hides fields that do not apply to the chosen topology", () => {
    expect(visible("DM-RET1", "L_factor", { filter: "C" })).toBe(false);
    expect(visible("DM-RET1", "L_factor", { filter: "LC" })).toBe(true);
    expect(visible("DM-RETC1", "freewheel", { topology: "ponte" })).toBe(false);
    expect(visible("DM-RET3", "alpha_nom", { controlled: false })).toBe(false);
  });
});

describe("resample", () => {
  it("interpolates linearly onto the output grid", () => {
    expect(resample([0, 1, 2], [0, 10, 20], [0, 0.5, 1.5, 2])).toEqual([0, 5, 15, 20]);
  });
});
