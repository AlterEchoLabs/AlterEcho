import TeX from "./TeX";

/** Formulas exactly as executed by the backend (analogue.v1.json → formulas_tex), each with a one-line meaning. */
const META: Record<string, { label: string; meaning: string }> = {
  slope: { label: "Slope", meaning: "Steepness between neighbouring 60 m cells, in degrees." },
  relative_elevation: { label: "Relative elevation", meaning: "Height above or below the window’s own median, so Earth and Mars datums never meet." },
  distribution_distance: { label: "Distance between two windows", meaning: "Wasserstein-1: the area between the two cumulative distributions, in the feature’s units (500 quantiles)." },
  feature_similarity: { label: "Similarity of one feature", meaning: "1 when identical, 0.5 when the difference equals the tolerance τ, 0.0625 at twice τ." },
  tolerance: { label: "Tolerance τ", meaning: "The typical difference between two ordinary Earth landscapes (median over 3,828 pairs)." },
  resolution_floor: { label: "Resolution floor δ", meaning: "What moving the reference 2 km and swapping the Earth elevation model change on their own." },
  family_score: { label: "Terrain score", meaning: "Slope and relative elevation weighted ½ each; relief and roughness are shown but not counted twice." },
  observed_index: { label: "Terrain similarity index", meaning: "The score on 0–100. Missing evidence is left out of both sums, never counted as zero." },
  evidence_coverage: { label: "Evidence coverage", meaning: "Share of the planned evidence that is measured and comparable." },
  standing: { label: "Comparison with ordinary land", meaning: "How many of the 88 ordinary Earth windows score lower than the candidate against the same reference." },
};

export const FORMULA_ORDER = ["slope", "relative_elevation", "distribution_distance", "feature_similarity", "tolerance", "resolution_floor", "family_score", "observed_index", "evidence_coverage", "standing"];

export default function FormulaList({ tex, only }: { tex: Record<string, string>; only?: string[] }) {
  const keys = (only ?? FORMULA_ORDER).filter((k) => tex[k]);
  return (
    <ol className="formula-list tex-formulas">
      {keys.map((k) => (
        <li key={k}>
          <div className="formula-head"><strong>{META[k]?.label ?? k.replaceAll("_", " ")}</strong><span className="muted">{META[k]?.meaning}</span></div>
          <TeX tex={tex[k]} />
        </li>
      ))}
    </ol>
  );
}
