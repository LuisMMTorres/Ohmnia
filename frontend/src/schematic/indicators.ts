/** Brightness of LEDs and lamps from the simulated current through them. */
import type { IndicatorOut } from "../api";
import { GLOW_COLORS, type Glow } from "./symbols";

/** Lamp drawn as overloaded above this fraction of the rated power. */
export const LAMP_OVERLOAD = 1.1;

/**
 * Glow of one indicator from its current samples. Only the second half of a transient is used,
 * so the start-up does not count: LED → mean forward current over the current of 100 %
 * brightness (the eye averages PWM); lamp → P = I_rms²·R over the rated power.
 */
export function glowFrom(ind: IndicatorOut, values: number[]): Glow | null {
  if (!values.length) return null;
  const tail = values.length > 4 ? values.slice(Math.floor(values.length / 2)) : values;
  if (ind.kind === "led") {
    if (!ind.i_ref) return null;
    const mean = tail.reduce((a, v) => a + Math.max(v, 0), 0) / tail.length;
    return {
      level: mean / ind.i_ref,
      color: GLOW_COLORS[ind.colour ?? ""] ?? GLOW_COLORS.vermelho!,
      burnt: ind.i_max != null && mean > ind.i_max,
    };
  }
  if (!ind.r || !ind.p_nom) return null;
  const rms2 = tail.reduce((a, v) => a + v * v, 0) / tail.length;
  const level = (rms2 * ind.r) / ind.p_nom;
  return { level, color: GLOW_COLORS.lamp!, burnt: level > LAMP_OVERLOAD };
}

/** Text for the properties panel: current/power and brightness. */
export function glowText(ind: IndicatorOut, g: Glow): string {
  const pct = `${Math.round(g.level * 100)} %`;
  if (ind.kind === "led") {
    const amps = g.level * (ind.i_ref ?? 0);
    const ma = (amps * 1e3).toFixed(1).replace(".", ",");
    const big =
      amps >= 1e3 ? "mais de 1 kA (só a fonte limita)" : `${amps.toFixed(1).replace(".", ",")} A`;
    return g.burnt
      ? `I média ${amps >= 1 ? big : `${ma} mA`}, acima da máxima (${((ind.i_max ?? 0) * 1e3).toFixed(0)} mA): o LED queimaria`
      : `I média ${ma} mA · brilho ${pct} do de referência`;
  }
  const w = (g.level * (ind.p_nom ?? 0)).toFixed(2).replace(".", ",");
  return g.burnt
    ? `P = ${w} W, acima da nominal (${ind.p_nom} W): vida útil reduzida, risco de queima`
    : `P = ${w} W · ${pct} da potência nominal`;
}
