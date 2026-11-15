import { ReactNode, useRef, useState } from "react";
import { Bbox, catalog } from "../api";

/** Page image rendered by the server at ZOOM (pixels per PDF point). */
const ZOOM = 2;

export interface Highlight {
  bbox: Bbox;
  label?: string;
  tone?: "active" | "muted";
}

interface Props {
  sha: string;
  page: number;
  highlights?: Highlight[];
  /** PDF-point coordinates of a click (origin top-left, as PyMuPDF). */
  onPick?: (x: number, y: number, event: React.MouseEvent<SVGSVGElement>) => void;
  /** Extra SVG drawn in PDF points over the page (markers, rectangles, traced points). */
  overlay?: ReactNode;
  cursor?: string;
  /** Receives the image element once loaded (the digitiser reads pixel colours from it). */
  onImage?: (img: HTMLImageElement) => void;
}

export function PdfPage({ sha, page, highlights = [], onPick, overlay, cursor, onImage }: Props) {
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const pick = (event: React.MouseEvent<SVGSVGElement>) => {
    if (!onPick || !size || !svgRef.current) return;
    const r = svgRef.current.getBoundingClientRect();
    const x = ((event.clientX - r.left) / r.width) * size.w;
    const y = ((event.clientY - r.top) / r.height) * size.h;
    onPick(x, y, event);
  };

  return (
    <div className="pdf-page">
      <img
        className="page"
        src={catalog.pageUrl(sha, page)}
        alt={`Página ${page} do datasheet`}
        crossOrigin="anonymous"
        onLoad={(e) => {
          const img = e.currentTarget;
          setSize({ w: img.naturalWidth / ZOOM, h: img.naturalHeight / ZOOM });
          onImage?.(img);
        }}
      />
      {size && (
        <svg
          ref={svgRef}
          className="pdf-overlay"
          viewBox={`0 0 ${size.w} ${size.h}`}
          preserveAspectRatio="none"
          style={{ cursor: cursor ?? (onPick ? "crosshair" : "default") }}
          onClick={pick}
          role={onPick ? "button" : undefined}
          aria-label={onPick ? "Clique na figura para marcar um ponto" : undefined}
        >
          {highlights.map((h, i) => (
            <g key={i}>
              <rect
                x={h.bbox[0] - 2}
                y={h.bbox[1] - 2}
                width={h.bbox[2] - h.bbox[0] + 4}
                height={h.bbox[3] - h.bbox[1] + 4}
                className={`hl ${h.tone ?? "active"}`}
              />
              {h.label && (
                <text x={h.bbox[0]} y={h.bbox[1] - 4} className="hl-label">
                  {h.label}
                </text>
              )}
            </g>
          ))}
          {overlay}
        </svg>
      )}
    </div>
  );
}

export { ZOOM as PAGE_ZOOM };
