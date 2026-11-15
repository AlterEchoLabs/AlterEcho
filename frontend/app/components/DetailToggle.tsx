"use client";

import { useDetailMode } from "../../lib/detail";

/** Simple shows the answer and why; Detailed opens every calculation, range and table by default. */
export default function DetailToggle() {
  const [mode, setMode] = useDetailMode();
  return (
    <div className="detail-toggle" role="radiogroup" aria-label="Level of detail" data-testid="detail-toggle">
      <button type="button" role="radio" aria-checked={mode === "simple"} onClick={() => setMode("simple")}>Simple</button>
      <button type="button" role="radio" aria-checked={mode === "detailed"} onClick={() => setMode("detailed")}>Detailed</button>
    </div>
  );
}
