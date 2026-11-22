import type { Component } from "./types";

export type Waveform = "dc" | "sine" | "square" | "triangle";
export interface SourceSettings {
  waveform: Waveform;
  offset: number;
  /** RMS value of the alternating part (V or A), the value a true-RMS meter reads in AC. */
  rms: number;
  frequency: number;
  duty: number;
}
/** Peak-to-peak value of a waveform whose alternating part has the given RMS value.
 * Sine: Vpp = 2√2·Vrms. Square with duty D: Vrms = Vpp·√(D(1−D)) (Vpp/2 at 50 %).
 * Triangle or sawtooth of any slope: Vrms = Vpp/(2√3). */
export function peakToPeakFromRms(waveform: Waveform, rms: number, duty = 50): number {
  const d = duty / 100;
  if (waveform === "sine") return 2 * Math.SQRT2 * rms;
  if (waveform === "square") return rms / Math.sqrt(d * (1 - d));
  if (waveform === "triangle") return 2 * Math.sqrt(3) * rms;
  return 0;
}
export function rmsFromPeakToPeak(waveform: Waveform, vpp: number, duty = 50): number {
  const ratio = peakToPeakFromRms(waveform, 1, duty);
  return ratio > 0 ? vpp / ratio : 0;
}
/** Six significant digits: 360 Vpp read back as 127,279 V instead of 127,27922061357856. */
const tidy = (x: number) => Number(x.toPrecision(6));
export function spiceNumber(value: string | undefined, fallback = 0): number {
  if (!value) return fallback;
  const match = /^([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)\s*(meg|[tgkmunpf])?$/i.exec(
    value.trim(),
  );
  if (!match) return fallback;
  const multipliers: Record<string, number> = {
    t: 1e12,
    g: 1e9,
    meg: 1e6,
    k: 1e3,
    m: 1e-3,
    u: 1e-6,
    n: 1e-9,
    p: 1e-12,
    f: 1e-15,
  };
  return Number(match[1]) * (multipliers[match[2]?.toLowerCase() ?? ""] ?? 1);
}
export function sourceSettings(c: Component): SourceSettings {
  const p = c.params;
  const period = spiceNumber(p.period, 1e-3);
  const waveform: Waveform =
    (p.bench_waveform as Waveform) ??
    (c.kind.endsWith("dc") ? "dc" : c.kind.endsWith("sin") ? "sine" : "square");
  const duty = spiceNumber(p.bench_duty, (100 * spiceNumber(p.width, period / 2)) / period);
  // circuits saved before the RMS field keep the peak-to-peak value in bench_vpp
  const vpp = spiceNumber(
    p.bench_vpp,
    c.kind.endsWith("sin")
      ? 2 * spiceNumber(p.amplitude, 1)
      : Math.abs(spiceNumber(p.v2, 5) - spiceNumber(p.v1)),
  );
  return {
    waveform,
    offset: spiceNumber(
      p.dc ?? p.offset,
      c.kind.endsWith("pulse") ? (spiceNumber(p.v1) + spiceNumber(p.v2, 5)) / 2 : 0,
    ),
    rms:
      p.bench_vrms !== undefined
        ? spiceNumber(p.bench_vrms)
        : tidy(rmsFromPeakToPeak(waveform === "dc" ? "sine" : waveform, vpp, duty)),
    frequency: spiceNumber(p.bench_frequency ?? p.freq, 1 / period),
    duty,
  };
}
/** Translate the controls to native SPICE SIN/PULSE parameters, preserving connections. */
export function configureSource(c: Component, s: SourceSettings): Component {
  if (
    ![s.offset, s.rms, s.frequency, s.duty].every(Number.isFinite) ||
    s.frequency <= 0 ||
    s.rms < 0 ||
    s.duty <= 0 ||
    s.duty >= 100
  )
    throw new Error(
      "Use frequência positiva, valor eficaz não negativo e duty cycle entre 0 e 100 %.",
    );
  const peakToPeak = peakToPeakFromRms(s.waveform, s.rms, s.duty);
  const prefix = c.kind.startsWith("i") ? "i" : "v";
  const period = 1 / s.frequency;
  const transition = Math.min(period * 1e-4, (period * Math.min(s.duty, 100 - s.duty)) / 400);
  const params: Record<string, string> = {
    ...c.params,
    bench_waveform: s.waveform,
    bench_vrms: String(s.rms),
    bench_frequency: String(s.frequency),
    bench_duty: String(s.duty),
    ac: c.params.ac ?? "1",
  };
  for (const k of [
    "bench_vpp",
    "dc",
    "offset",
    "amplitude",
    "freq",
    "v1",
    "v2",
    "rise",
    "fall",
    "width",
    "period",
    "delay",
  ])
    delete params[k];
  if (s.waveform === "dc") params.dc = String(s.offset);
  else if (s.waveform === "sine")
    Object.assign(params, {
      offset: String(s.offset),
      amplitude: String(peakToPeak / 2),
      freq: String(s.frequency),
    });
  else
    Object.assign(params, {
      v1: String(s.offset - peakToPeak / 2),
      v2: String(s.offset + peakToPeak / 2),
      period: String(period),
      delay: "0",
      rise: String(s.waveform === "triangle" ? (period * s.duty) / 100 : transition),
      fall: String(s.waveform === "triangle" ? period * (1 - s.duty / 100) : transition),
      width: String(s.waveform === "triangle" ? 0 : (period * s.duty) / 100 - transition),
    });
  return {
    ...c,
    kind: `${prefix}${s.waveform === "dc" ? "dc" : s.waveform === "sine" ? "sin" : "pulse"}`,
    params,
  };
}
