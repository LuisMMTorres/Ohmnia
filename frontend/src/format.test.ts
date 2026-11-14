import { describe, expect, it } from "vitest";
import { formatEng } from "./format";

describe("formatEng", () => {
  it.each([
    [4700, "ohm", "4,7 kΩ"],
    [1e-7, "F", "100 nF"],
    [12, "V", "12 V"],
    [-0.015, "A", "-15 mA"],
    [999.96, "ohm", "1 kΩ"],
    [0, "V", "0 V"],
    [33e-6, "s", "33 µs"],
    [-3.01, "", "-3,01"],
    [45.25, "deg", "45,3 deg"],
  ])("%s %s → %s", (value, unit, expected) => {
    expect(formatEng(value, unit)).toBe(expected);
  });
});
