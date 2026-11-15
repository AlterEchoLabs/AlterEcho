"use client";

import katex from "katex";
import { useEffect, useRef, useState } from "react";

/** A formula rendered by KaTeX: HTML for sight, MathML for screen readers. Sources are AlterEcho's own method strings.
 *  A display formula wider than its column scrolls sideways; it then becomes keyboard-focusable so it can be scrolled without a mouse. */
export default function TeX({ tex, block = true, className = "" }: { tex: string; block?: boolean; className?: string }) {
  const html = katex.renderToString(tex, { displayMode: block, throwOnError: false, output: "htmlAndMathml", strict: "ignore", trust: false });
  const ref = useRef<HTMLDivElement | null>(null);
  const [scrolls, setScrolls] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || !block || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => setScrolls(el.scrollWidth > el.clientWidth + 1));
    observer.observe(el);
    return () => observer.disconnect();
  }, [html, block]);
  if (!block) return <span className={`tex-inline ${className}`} dangerouslySetInnerHTML={{ __html: html }} />;
  return (
    <div ref={ref} className={`tex-block ${className}`} tabIndex={scrolls ? 0 : undefined} role={scrolls ? "region" : undefined}
      aria-label={scrolls ? "Formula, scroll sideways to read it all" : undefined} dangerouslySetInnerHTML={{ __html: html }} />
  );
}
