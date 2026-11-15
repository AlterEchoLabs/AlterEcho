"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { resolveApiUrl, safeExternalUrl } from "../../../lib/api";
import { COMPARE_MODES, type CompareMode, type ReferenceV3 } from "../../../lib/analogue";
import { coords } from "../../../lib/format";

const SHORT: Record<string, string> = {
  "mars-jezero": "Jezero", "mars-gale-aeolis-palus": "Gale", "mars-insight-elysium": "InSight", "mars-gusev-plains": "Gusev",
  "mars-eberswalde-delta": "Eberswalde", "moon-south-pole-shackleton": "Shackleton",
};
export const shortName = (r: { id: string; name: string }) => SHORT[r.id] ?? r.name.split(" (")[0];
const bodyName = (body: string) => (body === "moon" ? "Moon" : "Mars");
const placeOf = (r: ReferenceV3) => (r.body === "moon" ? "Moon · 90° S" : `Mars · ${coords(r.center[1], r.center[0])}`);

/** Step 1: one button showing the chosen reference; the list of six opens below it. Arrow keys move, Enter chooses, Escape closes. */
function ReferencePicker({ references, referenceId, onReference, labelId }: { references: ReferenceV3[]; referenceId: string; onReference: (id: string) => void; labelId: string }) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const button = useRef<HTMLButtonElement | null>(null);
  const pop = useRef<HTMLDivElement | null>(null);
  const current = references.find((r) => r.id === referenceId) ?? null;
  const ordered = [...references.filter((r) => r.body === "mars"), ...references.filter((r) => r.body === "moon")];

  useEffect(() => {
    if (!open) return;
    pop.current?.querySelector<HTMLElement>('[aria-selected="true"]')?.focus();
    const onPointer = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!pop.current?.contains(target) && !button.current?.contains(target)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  const choose = (id: string) => { onReference(id); setOpen(false); button.current?.focus(); };
  const onKey = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const options = [...(pop.current?.querySelectorAll<HTMLElement>('[role="option"]') ?? [])];
    const move = (i: number) => { event.preventDefault(); options[(i + options.length) % options.length]?.focus(); };
    if (event.key === "ArrowDown" || event.key === "ArrowRight") move(index + 1);
    else if (event.key === "ArrowUp" || event.key === "ArrowLeft") move(index - 1);
    else if (event.key === "Home") move(0);
    else if (event.key === "End") move(options.length - 1);
    else if (event.key === "Escape") { event.preventDefault(); setOpen(false); button.current?.focus(); }
    else if (event.key === "Tab") setOpen(false);
  };
  const thumb = (r: ReferenceV3) => resolveApiUrl(r.imagery?.url ?? r.hillshade_url);

  return (
    <div className="ref-picker">
      <button ref={button} type="button" className="picker-button" aria-haspopup="listbox" aria-expanded={open} aria-controls={listId}
        aria-labelledby={`${labelId} ${listId}-value`} onClick={() => setOpen((v) => !v)} data-testid="reference-picker"
        onKeyDown={(e) => { if ((e.key === "ArrowDown" || e.key === "ArrowUp") && !open) { e.preventDefault(); setOpen(true); } }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {current && thumb(current) && <img src={thumb(current)!} alt="" width={34} height={34} className="picker-thumb" />}
        <span className="picker-text" id={`${listId}-value`}>
          <span className="picker-name">{current?.name ?? "Loading references…"}</span>
          {current && <span className="picker-sub">{placeOf(current)}{current.scorable ? "" : " · distances only"}</span>}
        </span>
        <span className="picker-chevron" aria-hidden="true" />
      </button>
      <div ref={pop} className="ref-popover" hidden={!open}>
        <div role="listbox" id={listId} aria-label="Planetary reference" data-testid="reference-cards">
          {(["mars", "moon"] as const).map((body) => {
            const group = ordered.filter((r) => r.body === body);
            if (!group.length) return null;
            return (
              <div role="group" aria-labelledby={`${listId}-${body}`} key={body} className="pop-group">
                <p className="pop-body" id={`${listId}-${body}`}>{bodyName(body)}</p>
                {group.map((r) => {
                  const active = r.id === referenceId;
                  const src = thumb(r);
                  return (
                    <button key={r.id} type="button" role="option" aria-selected={active} tabIndex={active ? 0 : -1} className={`pop-option ${active ? "is-active" : ""}`}
                      onClick={() => choose(r.id)} onKeyDown={(e) => onKey(e, ordered.indexOf(r))} data-testid={`reference-${r.id}`}>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      {src && <img src={src} alt="" width={40} height={40} loading="lazy" />}
                      <span className="pop-text">
                        <span className="pop-name">{r.name}</span>
                        <span className="pop-sub">{r.region} · {r.scorable ? "scored" : "distances only"}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/** Step 2: a three-way switch. Arrow keys move the choice, as in any radio group. */
function ModeSwitch({ mode, onMode, labelId }: { mode: CompareMode; onMode: (mode: CompareMode) => void; labelId: string }) {
  const onKey = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const next = COMPARE_MODES[(index + step + COMPARE_MODES.length) % COMPARE_MODES.length];
    onMode(next.id);
    (event.currentTarget.parentElement?.querySelector(`[data-testid="mode-${next.id}"]`) as HTMLElement | null)?.focus();
  };
  return (
    <div className="mode-switch" role="radiogroup" aria-labelledby={labelId}>
      {COMPARE_MODES.map((m, i) => (
        <button key={m.id} type="button" role="radio" aria-checked={mode === m.id} tabIndex={mode === m.id ? 0 : -1}
          onClick={() => onMode(m.id)} onKeyDown={(e) => onKey(e, i)} data-testid={`mode-${m.id}`}>
          {m.label}
        </button>
      ))}
    </div>
  );
}

/** Secondary facts about the reference window, one click away. */
function ReferenceAbout({ reference, doi }: { reference: ReferenceV3; doi: string | null }) {
  return (
    <details className="ref-about">
      <summary>About this reference window</summary>
      <div className="ref-about-body">
        <p className="reference-facts">{placeOf(reference)} · 10 km window · {reference.dem.product.replaceAll("_", " ")} (20 m), analysed on a 60 m grid</p>
        {reference.context && <p>{reference.context}</p>}
        <p><strong>Placement:</strong> {reference.selection_rationale}</p>
        <dl className="kv small">
          <dt>Elevation product</dt><dd>{reference.dem.item ?? reference.dem.product} · {reference.dem.provider}{doi && <> · <a href={doi} target="_blank" rel="noreferrer noopener">DOI {reference.dem.doi}</a></>}</dd>
          {reference.dem.intersection_error && <><dt>Stereo quality</dt><dd>median intersection error {reference.dem.intersection_error.median_m} m (95th percentile {reference.dem.intersection_error.p95_m} m)</dd></>}
          <dt>Median slope (60 m)</dt><dd className="mono">{reference.slope_median_60m.toFixed(2)}°</dd>
          <dt>Resolution floor</dt><dd className="mono">slope {reference.resolution_floor.slope?.combined.toFixed(2)}° · relative elevation {reference.resolution_floor.relative_elevation?.combined.toFixed(1)} m</dd>
          {reference.imagery && <><dt>Image</dt><dd>{reference.imagery.attribution}</dd></>}
        </dl>
        <ul className="small">{reference.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
      </div>
    </details>
  );
}

const SUBTITLE: Record<CompareMode, string> = {
  terrain: "Measured from real elevation data over 10 km windows, and checked against ordinary Earth land.",
  temperature: "Earth: Aqua MODIS land-surface temperature. Mars: Perseverance’s MEDA ground-temperature record, available for Jezero only. Context only, not scored.",
  fieldwork: "Published analogue research at each Earth site. Context only; it does not change the terrain result.",
};

function title(mode: CompareMode, name: string | null) {
  const ref = name ? <span className="hero-ref">{name}</span> : "Mars or the Moon";
  if (mode === "temperature") return <>Surface temperatures at the Earth sites, beside {ref}</>;
  if (mode === "fieldwork") return <>Where have analogue field tests been documented?</>;
  return <>Which Earth terrain is closest to {ref}?</>;
}

/** The atlas opening: what it does, step 1 (reference) and step 2 (what to compare). Step 3 is the results list. */
export default function ControlBar({ references, referenceId, onReference, mode, onMode }: {
  references: ReferenceV3[]; referenceId: string; onReference: (id: string) => void; mode: CompareMode; onMode: (mode: CompareMode) => void;
}) {
  const reference = references.find((r) => r.id === referenceId) ?? null;
  const doi = reference?.dem.doi ? safeExternalUrl(`https://doi.org/${reference.dem.doi}`) : null;
  const refLabel = useId(), modeLabel = useId();
  return (
    <section className="atlas-hero" aria-label="What to compare">
      <div className="hero-copy">
        <p className="eyebrow">Earth analogue atlas</p>
        <h1 className="hero-title">{title(mode, reference?.name ?? null)}</h1>
        <p className="hero-sub">{SUBTITLE[mode]} <Link href="/method">How it works</Link></p>
        {reference && <ReferenceAbout reference={reference} doi={doi} />}
      </div>
      <div className="hero-controls">
        <div className="control">
          <span className="control-label" id={refLabel}><span className="step" aria-hidden="true">1</span>Planetary reference</span>
          <ReferencePicker references={references} referenceId={referenceId} onReference={onReference} labelId={refLabel} />
        </div>
        <div className="control">
          <span className="control-label" id={modeLabel}><span className="step" aria-hidden="true">2</span>Compare by</span>
          <ModeSwitch mode={mode} onMode={onMode} labelId={modeLabel} />
          <p className="mode-hint" data-testid="mode-hint">{COMPARE_MODES.find((m) => m.id === mode)?.hint}</p>
        </div>
      </div>
      {reference && !reference.scorable && <div className="hero-foot"><p className="notice notice-warn" data-testid="reference-not-scorable">{reference.scorable_reason}</p></div>}
    </section>
  );
}
