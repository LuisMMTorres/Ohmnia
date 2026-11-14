import katex from "katex";
import "katex/dist/katex.min.css";
import { useMemo } from "react";

export function Equation({ latex, block = false }: { latex: string; block?: boolean }) {
  const html = useMemo(
    () => katex.renderToString(latex, { displayMode: block, throwOnError: false }),
    [latex, block],
  );
  return <span className="equation" dangerouslySetInnerHTML={{ __html: html }} />;
}
