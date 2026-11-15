import { describe, expect, it } from "vitest";
import { axisValue, parseFamily } from "./digitizer";

describe("axisValue", () => {
  it("interpolates linear and logarithmic axes", () => {
    expect(axisValue({ p1: 100, v1: 0, p2: 400, v2: 1.2, scale: "lin" }, 250)).toBeCloseTo(0.6);
    expect(axisValue({ p1: 400, v1: 1e-3, p2: 100, v2: 10, scale: "log" }, 250)).toBeCloseTo(0.1);
  });
});

describe("parseFamily", () => {
  it("reads test conditions with units", () => {
    const { family, rest } = parseFamily("Tj = 25,5 °C; VCE=5 V, nota");
    expect(family.Tj).toEqual({ value: 25.5, unit: "degC" });
    expect(family.VCE).toEqual({ value: 5, unit: "V" });
    expect(rest).toEqual(["nota"]);
  });
});
