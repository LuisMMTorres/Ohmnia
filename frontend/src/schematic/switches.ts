/**
 * Manual switches operated by clicking on them (push-buttons and manual contacts).
 *
 * The state lives in the "state" parameter, the same one the netlist reads: a constant
 * ("1" pressed / closed, "0" released / open) or a time profile in time/value pairs. A click
 * replaces it with the opposite constant, so the next simulation sees the new position for the
 * whole run.
 */
import type { Component, SymbolDef } from "./types";

/** Kinds whose "state" parameter is the position of a hand-operated contact. */
export const MANUAL_SWITCH_KINDS = new Set([
  "tact_switch",
  "tact_switch4",
  "push_nc",
  "switch_manual",
]);

/** Default of the "state" parameter in the library (used when the component leaves it blank). */
export function stateDefault(sym: SymbolDef | undefined): string {
  return sym?.params.find((p) => p.name === "state")?.default ?? "0";
}

export type SwitchPosition = "pressed" | "released" | "profile";

/** Position drawn for the switch: a constant state, or a profile that changes with time. */
export function switchPosition(c: Component, fallback = "0"): SwitchPosition | null {
  if (!MANUAL_SWITCH_KINDS.has(c.kind)) return null;
  const raw = (c.params.state ?? "").trim() || fallback;
  const nums = raw.replace(/,/g, " ").split(/\s+/).filter(Boolean).map(Number);
  if (nums.length !== 1 || !Number.isFinite(nums[0])) return "profile";
  return nums[0]! > 0.5 ? "pressed" : "released";
}

/** The switch after one click: pressed ↔ released (a time profile becomes pressed). */
export function toggleSwitch(c: Component, fallback = "0"): Component {
  const next = switchPosition(c, fallback) === "pressed" ? "0" : "1";
  return { ...c, params: { ...c.params, state: next } };
}

/** Short status for the tooltip and the properties panel. */
export function switchText(c: Component, fallback = "0"): string {
  const pos = switchPosition(c, fallback);
  const contact = (closed: boolean) => (closed ? "contato fechado" : "contato aberto");
  const nc = c.kind === "push_nc";
  if (pos === "profile") return "segue o perfil no tempo do parâmetro Estado; clique para apertar";
  const pressed = pos === "pressed";
  const verb =
    c.kind === "switch_manual" ? (pressed ? "fechada" : "aberta") : pressed ? "apertado" : "solto";
  return `${verb} (${contact(nc ? !pressed : pressed)}); clique para ${pressed ? "soltar" : "apertar"}`;
}
