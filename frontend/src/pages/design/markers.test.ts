import { describe, expect, it } from "vitest";
import { markerTraces } from "./DesignAnalysis";

describe("markerTraces", () => {
  it("draws mean and RMS lines and the peak point", () => {
    const v = [0, 1, 0, -2];
    const [avg, rms, peak] = markerTraces(v, "V", undefined);
    expect(avg!.values).toEqual([-0.25, -0.25, -0.25, -0.25]);
    expect(rms!.values[0]).toBeCloseTo(Math.sqrt(5 / 4));
    expect(peak!.values).toEqual([null, null, null, -2]);
    expect(peak!.points).toBe(true);
    expect(avg!.dash).toBeDefined();
    expect(rms!.dash).not.toEqual(avg!.dash);
  });
});
