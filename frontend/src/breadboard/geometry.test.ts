import { describe, expect, it } from "vitest";
import { nearestHole, parseHole, placeLegs, shift, strip, holeXY } from "./geometry";
import type { BoardSpec, PackageSpec } from "./types";
import { netAtHole } from "./connections";
import { emptyBreadboard } from "./types";
import { connectScope, disconnectScope, removeScope, syncScopeProbes } from "./scopeConnections";
import { emptySchematic } from "../schematic/types";

const RAIL_ROWS = Array.from({ length: 10 }, (_, g) =>
  [2, 3, 4, 5, 6].map((r) => r + 6 * g),
).flat();
const board: BoardSpec = {
  id: "830",
  label: "",
  rows: 63,
  upper: "abcde",
  lower: "fghij",
  rails: ["tp", "tn", "bn", "bp"],
  rail_rows: RAIL_ROWS,
  split_after: 30,
  y: {
    tp: 0,
    tn: 1,
    a: 3,
    b: 4,
    c: 5,
    d: 6,
    e: 7,
    f: 10,
    g: 11,
    h: 12,
    i: 13,
    j: 14,
    bn: 16,
    bp: 17,
  },
  rail_polarity: { tp: "+", tn: "-", bn: "-", bp: "+" },
};
const pkg = (
  style: PackageSpec["style"],
  pins: string[],
  offsets: [number, number][],
): PackageSpec => ({
  id: style,
  label: style,
  style,
  pins,
  pitch: 1,
  span: 4,
  min_span: 3,
  body: "",
  note: "",
  offsets,
});

describe("breadboard geometry (same rules as the backend)", () => {
  it("connects the scope miniature to physical conductors and follows jumper changes", () => {
    const resolved = {
      parts: [],
      nets: { "R1:1": "out", "R1:2": "0" },
      net_labels: {},
      warnings: [],
    };
    const assembly = {
      ...emptyBreadboard(),
      parts: [{ ref: "R1", package: "axial-r", legs: { "1": "a1", "2": "a5" } }],
      wires: [{ id: "w", a: "b1", b: "2:b1", color: "verde" as const }],
    };
    const start = { ...emptySchematic(), bench_scope_channels: 2 as const, breadboard: assembly };
    const half = connectScope(start, board, resolved, 1, "positive", "2:e1");
    expect(half.probes).toHaveLength(0);
    const complete = connectScope(half, board, resolved, 1, "negative", "e5");
    expect(complete.probes[0]).toMatchObject({
      name: "OSC_CH1",
      kind: "vdiff",
      target: { net: "out" },
      reference: { net: "0" },
    });
    const moved = syncScopeProbes(
      {
        ...complete,
        breadboard: { ...assembly, wires: [{ id: "w", a: "b5", b: "2:b1", color: "verde" }] },
      },
      board,
      resolved,
    );
    expect(moved.probes[0]?.target?.net).toBe("0");
    expect(disconnectScope(complete, 1).probes).toHaveLength(0);
    expect(removeScope(complete).bench_scope_connections).toEqual({});
    expect(() => connectScope(start, board, resolved, 1, "positive", "2:a50")).toThrow();
  });
  it("keeps the two boards and vertical rails electrically separate", () => {
    expect(strip(board, "2:a12")).toBe(strip(board, "2:e12"));
    expect(strip(board, "a12")).not.toBe(strip(board, "2:a12"));
    expect(strip(board, "tp2")).not.toBe(strip(board, "2:tp2"));
    expect(strip(board, "vp1")).toBe(strip(board, "vp40"));
    expect(strip(board, "vp1")).not.toBe(strip(board, "vn1"));
    for (const h of ["2:c20", "vp15", "vn40"])
      expect(nearestHole(board, ...holeXY(board, h))).toBe(h);
    expect(shift(board, "2:a5", 1, 1)).toBe("2:b6");
    expect(parseHole(board, "2:vp1")).toBeNull();
  });
  it("follows cross-board jumpers for probes and rejects an ambiguous short", () => {
    const assembly = {
      ...emptyBreadboard(),
      parts: [{ ref: "R1", package: "axial-r", legs: { "1": "a1", "2": "a5" } }],
      wires: [{ id: "w1", a: "b1", b: "2:b1", color: "verde" as const }],
    };
    const resolved = {
      parts: [],
      nets: { "R1:1": "out", "R1:2": "0" },
      net_labels: {},
      warnings: [],
    };
    expect(netAtHole(board, assembly, resolved, "2:e1")).toBe("out");
    expect(() => netAtHole(board, assembly, resolved, "2:a2")).toThrow();
    assembly.wires.push({ id: "w2", a: "c1", b: "b5", color: "verde" });
    expect(() => netAtHole(board, assembly, resolved, "2:e1")).toThrow(/diferentes/);
  });
  it("joins a-e and f-j of a row, and whole rails", () => {
    expect(strip(board, "a12")).toBe(strip(board, "e12"));
    expect(strip(board, "e12")).not.toBe(strip(board, "f12"));
    expect(strip(board, "tn2")).toBe(strip(board, "tn60"));
    expect(strip(board, "tn2", true)).not.toBe(strip(board, "tn60", true));
  });

  it("rejects holes that do not exist", () => {
    expect(parseHole(board, "tn7")).toBeNull(); // gap between rail groups
    expect(parseHole(board, "k3")).toBeNull();
    expect(parseHole(board, "a64")).toBeNull();
  });

  it("finds the hole under the pointer", () => {
    const [x, y] = holeXY(board, "c20");
    expect(nearestHole(board, x + 3, y - 2)).toBe("c20");
  });

  it("places a DIP across the channel with pin 1 in column f", () => {
    const dip = pkg(
      "dip",
      ["1", "2", "3", "4", "5", "6", "7", "8"],
      [
        [0, 0],
        [1, 0],
        [2, 0],
        [3, 0],
        [3, -1],
        [2, -1],
        [1, -1],
        [0, -1],
      ],
    );
    const legs = placeLegs(board, dip, "f10", "h")!;
    expect(legs["1"]).toBe("f10");
    expect(legs["4"]).toBe("f13");
    expect(legs["5"]).toBe("e13");
    expect(legs["8"]).toBe("e10");
    expect(placeLegs(board, dip, "e10", "h")).toBeNull();
  });

  it("turns an inline part vertical and refuses to fall off the board", () => {
    const to92 = pkg(
      "inline",
      ["1", "2", "3"],
      [
        [0, 0],
        [1, 0],
        [2, 0],
      ],
    );
    expect(placeLegs(board, to92, "a5", "v")).toEqual({ "1": "a5", "2": "b5", "3": "c5" });
    expect(placeLegs(board, to92, "a62", "h")).toBeNull();
    expect(shift(board, "j5", 0, 1)).toBe("bn5");
  });
});
