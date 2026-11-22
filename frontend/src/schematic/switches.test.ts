import { describe, expect, it } from "vitest";
import { switchPosition, switchText, toggleSwitch } from "./switches";
import type { Component } from "./types";

const comp = (kind: string, state?: string): Component => ({
  id: "c1",
  kind,
  ref: "SW1",
  x: 0,
  y: 0,
  rot: 0,
  mirror: false,
  params: state === undefined ? {} : { state },
  part_id: null,
});

describe("push-buttons operated by a click", () => {
  it("reads constant states and time profiles", () => {
    expect(switchPosition(comp("tact_switch"))).toBe("released");
    expect(switchPosition(comp("tact_switch", "1"))).toBe("pressed");
    expect(switchPosition(comp("push_nc", " 0 "))).toBe("released");
    expect(switchPosition(comp("tact_switch", "0 0 0.001 0 0.00101 1"))).toBe("profile");
    expect(switchPosition(comp("resistor", "1"))).toBeNull();
  });

  it("toggles between released and pressed; a profile becomes pressed", () => {
    const pressed = toggleSwitch(comp("tact_switch"));
    expect(pressed.params.state).toBe("1");
    expect(toggleSwitch(pressed).params.state).toBe("0");
    expect(toggleSwitch(comp("switch_manual", "0 0 1 0 1.001 1")).params.state).toBe("1");
  });

  it("describes the contact (an NC button opens when pressed)", () => {
    expect(switchText(comp("tact_switch", "1"))).toContain("contato fechado");
    expect(switchText(comp("push_nc", "1"))).toContain("contato aberto");
    expect(switchText(comp("switch_manual", "0"))).toMatch(/^aberta/);
  });
});
