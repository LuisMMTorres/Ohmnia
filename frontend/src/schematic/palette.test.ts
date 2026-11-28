import { describe, expect, it } from "vitest";
import { sortPalette } from "./palette";

describe("sortPalette", () => {
  it("puts the potentiometer and the trimpot right after the resistor", () => {
    const kinds = ["resistor", "capacitor", "inductor", "transformer", "potentiometer", "trimpot"];
    expect(sortPalette(kinds.map((kind) => ({ kind }))).map((s) => s.kind)).toEqual([
      "resistor",
      "potentiometer",
      "trimpot",
      "capacitor",
      "inductor",
      "transformer",
    ]);
  });
});
