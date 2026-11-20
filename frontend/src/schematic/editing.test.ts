import { describe, expect, it } from "vitest";
import { autoWire, copyItems, itemsInBox, moveItems, pasteClip } from "./editing";
import { emptySchematic, type Component, type SymbolDef } from "./types";

const two = (kind: string): SymbolDef => ({
  kind,
  label: kind,
  group: "g",
  prefix: kind === "resistor" ? "R" : "D",
  pins: [
    { name: "1", dx: -2, dy: 0 },
    { name: "2", dx: 2, dy: 0 },
  ],
  params: [],
  catalogue: [],
  tolerance: null,
  description: "",
});
const lib = { resistor: two("resistor"), led: two("led") };
const comp = (id: string, kind: string, ref: string, x: number, y: number): Component => ({
  id,
  kind,
  ref,
  x,
  y,
  rot: 0,
  mirror: false,
  params: {},
  part_id: null,
});

describe("autoWire", () => {
  it("joins facing open pins on the same row", () => {
    const sch = {
      ...emptySchematic(),
      components: [comp("a", "resistor", "R1", 0, 0), comp("b", "led", "D1", 6, 0)],
    };
    const w = autoWire(sch, lib);
    expect(w).toHaveLength(1);
    expect(w[0]!.points).toEqual([
      [2, 0],
      [4, 0],
    ]);
  });
  it("does not wire through a component body", () => {
    // R2 sits between R1 and D1 on the same row, its pins already used by nothing:
    // R1.2 (2,0) faces R2.1 (4,0); R1.1 cannot reach D1 across R1 itself
    const sch = {
      ...emptySchematic(),
      components: [
        comp("a", "resistor", "R1", 0, 0),
        comp("c", "resistor", "R2", 6, 0),
        comp("b", "led", "D1", 12, 0),
      ],
    };
    const w = autoWire(sch, lib);
    for (const x of w) expect(Math.abs(x.points[1]![0] - x.points[0]![0])).toBe(2);
  });
  it("ends an open pin on a wire crossing its row", () => {
    const sch = {
      ...emptySchematic(),
      components: [comp("a", "resistor", "R1", 6, 0)],
      wires: [
        {
          id: "w",
          points: [
            [0, -3],
            [0, 3],
          ] as [number, number][],
        },
      ],
    };
    const w = autoWire(sch, lib);
    expect(w.map((x) => x.points)).toContainEqual([
      [4, 0],
      [0, 0],
    ]);
  });
});

describe("group edit", () => {
  const sch = {
    ...emptySchematic(),
    components: [comp("a", "resistor", "R1", 0, 0), comp("b", "led", "D1", 10, 0)],
    wires: [
      {
        id: "w",
        points: [
          [2, 0],
          [8, 0],
        ] as [number, number][],
      },
    ],
  };
  it("box selects what is fully inside", () => {
    const g = itemsInBox(sch, lib, [-3, -2], [3, 2]);
    expect(g.components).toEqual(["a"]);
    expect(g.wires).toEqual([]);
  });
  it("moving a group drags the attached wire end", () => {
    const out = moveItems(sch, lib, { components: ["a"], wires: [], labels: [] }, 0, 2);
    expect(out.components[0]!.y).toBe(2);
    expect(out.wires[0]!.points[0]).toEqual([2, 2]);
    expect(out.wires[0]!.points.at(-1)).toEqual([8, 0]);
  });
  it("paste gives new designators", () => {
    const clip = copyItems(sch, { components: ["a", "b"], wires: ["w"], labels: [] });
    const { sch: out, group } = pasteClip(sch, clip, [0, 10]);
    expect(out.components.map((c) => c.ref)).toEqual(["R1", "D1", "R2", "D2"]);
    expect(group.wires).toHaveLength(1);
    expect(out.wires[1]!.points[0]).toEqual([2, 10]);
  });
});
