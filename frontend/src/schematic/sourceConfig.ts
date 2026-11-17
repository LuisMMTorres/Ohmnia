import type { Component } from "./types";

export type Waveform = "dc" | "sine" | "square" | "triangle";
export interface SourceSettings {
  waveform: Waveform;
  offset: number;
  peakToPeak: number;
  frequency: number;
  duty: number;
}
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
  return {
    waveform:
      (p.bench_waveform as Waveform) ??
      (c.kind.endsWith("dc") ? "dc" : c.kind.endsWith("sin") ? "sine" : "square"),
    offset: spiceNumber(
      p.dc ?? p.offset,
      c.kind.endsWith("pulse") ? (spiceNumber(p.v1) + spiceNumber(p.v2, 5)) / 2 : 0,
    ),
    peakToPeak: spiceNumber(
      p.bench_vpp,
      c.kind.endsWith("sin")
        ? 2 * spiceNumber(p.amplitude, 1)
        : Math.abs(spiceNumber(p.v2, 5) - spiceNumber(p.v1)),
    ),
    frequency: spiceNumber(p.bench_frequency ?? p.freq, 1 / period),
    duty: spiceNumber(p.bench_duty, (100 * spiceNumber(p.width, period / 2)) / period),
  };
}
/** Translate the controls to native SPICE SIN/PULSE parameters, preserving connections. */
export function configureSource(c: Component, s: SourceSettings): Component {
  if (
    ![s.offset, s.peakToPeak, s.frequency, s.duty].every(Number.isFinite) ||
    s.frequency <= 0 ||
    s.peakToPeak < 0 ||
    s.duty <= 0 ||
    s.duty >= 100
  )
    throw new Error(
      "Use frequência positiva, amplitude não negativa e duty cycle entre 0 e 100 %.",
    );
  const prefix = c.kind.startsWith("i") ? "i" : "v";
  const period = 1 / s.frequency;
  const transition = Math.min(period * 1e-4, (period * Math.min(s.duty, 100 - s.duty)) / 400);
  const params: Record<string, string> = {
    ...c.params,
    bench_waveform: s.waveform,
    bench_vpp: String(s.peakToPeak),
    bench_frequency: String(s.frequency),
    bench_duty: String(s.duty),
    ac: c.params.ac ?? "1",
  };
  for (const k of [
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
      amplitude: String(s.peakToPeak / 2),
      freq: String(s.frequency),
    });
  else
    Object.assign(params, {
      v1: String(s.offset - s.peakToPeak / 2),
      v2: String(s.offset + s.peakToPeak / 2),
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
