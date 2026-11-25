import { describe, expect, it } from "vitest";
import { meterReadings } from "./meter";

describe("multimeter on adaptive sampling", () => {
  it("shows a constant DC voltage and no AC component", () => {
    expect(meterReadings([0, 0.1, 1], [5, 5, 5])).toEqual({
      duration: 1,
      instant: 5,
      mean: 5,
      rms: 5,
      acRms: 0,
    });
  });
  it("weights intervals instead of counting dense samples near switching edges", () => {
    const out = meterReadings([0, 0.1, 0.2, 1], [0, 0, 10, 10])!;
    expect(out.mean).toBeCloseTo(8.5);
    expect(out.rms).toBeCloseTo(Math.sqrt(85));
    expect(out.acRms).toBeCloseTo(Math.sqrt(85 - 8.5 ** 2));
  });
  it("does not invent a value for disconnected probes", () => {
    expect(meterReadings([], [])).toBeNull();
    expect(meterReadings([0], [])).toBeNull();
  });
});
