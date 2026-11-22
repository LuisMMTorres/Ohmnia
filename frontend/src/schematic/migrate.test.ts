import { describe, expect, it } from "vitest";
import { upgradeSchematic } from "./migrate";
import type { Component, Schematic } from "./types";

const trafo = (params: Record<string, string>): Component => ({
  id: "t1",
  ref: "T1",
  kind: "transformer",
  x: 0,
  y: 0,
  rot: 0,
  mirror: false,
  part_id: null,
  params,
});
const sch = (c: Component) => ({ components: [c] }) as unknown as Schematic;

describe("saved circuits", () => {
  it("turns the old Ns/Np ratio into Np/Ns", () => {
    const up = upgradeSchematic(sch(trafo({ lp: "100m", n: "0.1" })));
    expect(up.components[0]!.params).toEqual({ lp: "100m", ratio: "10" });
  });
  it("keeps circuits already in Np/Ns and parameter expressions", () => {
    const now = sch(trafo({ ratio: "5" }));
    expect(upgradeSchematic(now)).toBe(now);
    const expr = sch(trafo({ n: "{N}" }));
    expect(upgradeSchematic(expr)).toBe(expr);
  });
});
