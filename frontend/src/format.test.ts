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
    [45.25, "deg", "45,3 °"],
    [1.484e10, "1/cm**3", "1,48·10¹⁰ cm⁻³"],
    [1e15, "1/cm**3", "10¹⁵ cm⁻³"],
  ])("%s %s → %s", (value, unit, expected) => {
    expect(formatEng(value, unit)).toBe(expected);
  });
});

describe("formatEng with prefixed units", () => {
  it("re-chooses the prefix of an already prefixed unit", () => {
    expect(formatEng(15000, "uF")).toBe("15 mF");
    expect(formatEng(0.5, "mH")).toBe("500 µH");
    expect(formatEng(35.2, "A*V")).toBe("35,2 VA");
    expect(formatEng(30, "deg")).toBe("30 °");
  });
});
