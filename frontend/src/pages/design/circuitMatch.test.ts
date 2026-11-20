import { describe, expect, it } from "vitest";
import type { CircuitElement } from "../../api";
import { matchElement, probeText, sameProbe } from "./circuitMatch";

function el(name: string, nodes: string[], extra: Partial<CircuitElement> = {}): CircuitElement {
  return {
    name,
    letter: name[0]!.toUpperCase(),
    nodes,
    pins: nodes.map((_, i) => `terminal ${i + 1}`),
    value: "",
    edit: "none",
    sense: false,
    role: null,
    original: null,
    ...extra,
  };
}

const ELS = [
  el("VS", ["a", "b"]),
  el("VSD1", ["a", "d1"], { sense: true }),
  el("XD1", ["d1", "p"]),
  el("XD2", ["b", "p"]),
  el("C1", ["p", "0"]),
  el("RL", ["p", "0"]),
  el("Q1", ["c", "b", "e"], { pins: ["coletor", "base", "emissor"] }),
];

describe("matchElement", () => {
  it("finds the element a label of the drawing names", () => {
    expect(matchElement("C1", ELS)?.name).toBe("C1");
    expect(matchElement("D2", ELS)?.name).toBe("XD2");
    expect(matchElement("R", ELS)?.name).toBe("RL"); // the only resistor
    expect(matchElement("12 Ω", ELS)).toBeNull();
    expect(matchElement("VSD1", ELS)).toBeNull(); // current-sense source, not a part
  });
});

describe("probeText", () => {
  it("describes each kind of probe", () => {
    expect(probeText({ kind: "v", a: "p" }, ELS)).toContain("nó p");
    expect(probeText({ kind: "vdiff", a: "a", b: "b" }, ELS)).toContain("a − b");
    expect(probeText({ kind: "i", a: "Q1", pin: 1 }, ELS)).toBe("Corrente em Q1 (base)");
    expect(probeText({ kind: "p", a: "RL" }, ELS)).toBe("Potência em RL");
  });
  it("compares probes", () => {
    expect(sameProbe({ kind: "i", a: "RL" }, { kind: "i", a: "RL", pin: 0 })).toBe(true);
    expect(sameProbe({ kind: "i", a: "RL" }, { kind: "p", a: "RL" })).toBe(false);
  });
});
