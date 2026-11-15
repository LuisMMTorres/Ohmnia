import { AxisCalibration, Quantity } from "../../api";

/** Value at a position on a calibrated axis (same formula as the server). */
export function axisValue(cal: AxisCalibration, position: number): number {
  const t = (position - cal.p1) / (cal.p2 - cal.p1);
  if (cal.scale === "log") {
    const a = Math.log10(cal.v1);
    const b = Math.log10(cal.v2);
    return 10 ** (a + t * (b - a));
  }
  return cal.v1 + t * (cal.v2 - cal.v1);
}

const UNIT_TEXT: Record<string, string> = {
  "°C": "degC",
  ºC: "degC",
  µA: "uA",
  µs: "us",
  Ω: "ohm",
  mΩ: "mohm",
};

/** "Tj = 25 °C; VCE = 5 V" → {Tj: 25 degC, VCE: 5 V}. Unparsable parts are returned apart. */
export function parseFamily(text: string): { family: Record<string, Quantity>; rest: string[] } {
  const family: Record<string, Quantity> = {};
  const rest: string[] = [];
  for (const part of text
    .split(/;|\n|,(?=\s*[A-Za-z])/)
    .map((p) => p.trim())
    .filter(Boolean)) {
    const m = part.match(/^([A-Za-z][\w()]*)\s*=\s*([-+]?\d+(?:[.,]\d+)?)\s*(.*)$/);
    if (!m) {
      rest.push(part);
      continue;
    }
    const unit = m[3]!.trim();
    family[m[1]!] = {
      value: Number(m[2]!.replace(",", ".")),
      unit: UNIT_TEXT[unit] ?? (unit || "dimensionless"),
    };
  }
  return { family, rest };
}

/** Colour of the image pixel under a PDF-point position (zoom = pixels per point). */
export function pixelColour(
  img: HTMLImageElement,
  x: number,
  y: number,
  zoom: number,
): [number, number, number] | null {
  const canvas = document.createElement("canvas");
  canvas.width = 1;
  canvas.height = 1;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.drawImage(img, Math.round(x * zoom), Math.round(y * zoom), 1, 1, 0, 0, 1, 1);
  const d = ctx.getImageData(0, 0, 1, 1).data;
  return [d[0]!, d[1]!, d[2]!];
}
