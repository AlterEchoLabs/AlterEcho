const LABELS: Record<string, string> = {
  scalar_distance: "Scalar distance",
  distribution_distance: "Distribution distance",
  feature_similarity: "Feature similarity",
  family_score: "Family score",
  observed_index: "Observed index",
  evidence_coverage: "Evidence coverage",
};

const LATEX: Record<string, string> = {
  scalar_distance: String.raw`d_k = |x_{E,k} - x_{P,k}|`,
  distribution_distance: String.raw`d_k = W_1(F_{E,k}, F_{P,k}) = \int_0^1 |F^{-1}_{E,k}(u) - F^{-1}_{P,k}(u)|\,du`,
  feature_similarity: String.raw`s_k = \exp\left(-\ln 2\left(\frac{d_k}{\tau_k}\right)^2\right)`,
  family_score: String.raw`S_g = \sum_{k\in g} a_{k|g}s_k`,
  observed_index: String.raw`I = 100\frac{\sum_g w_g I_g S_g}{\sum_g w_g I_g}`,
  evidence_coverage: String.raw`C = \sum_g w_g I_g`,
};

const DISPLAY: Record<string, string> = {
  scalar_distance: "dₖ = |xₑ,ₖ − xₚ,ₖ|",
  distribution_distance: "dₖ = W₁(Fₑ,ₖ, Fₚ,ₖ) = ∫₀¹ |F⁻¹ₑ,ₖ(u) − F⁻¹ₚ,ₖ(u)| du",
  feature_similarity: "sₖ = exp(−ln 2 · (dₖ / τₖ)²)",
  family_score: "Sg = Σₖ∈g aₖ|g sₖ",
  observed_index: "I = 100 · (Σg wg Ig Sg) / (Σg wg Ig)",
  evidence_coverage: "C = Σg wg Ig",
};

export default function FormulaList({ formulas }: { formulas: Record<string, string> }) {
  return (
    <ul className="formula-list">
      {Object.entries(formulas).map(([name, source]) => {
        const latex = LATEX[name] ?? source;
        return (
          <li key={name}>
            <span className="muted">{LABELS[name] ?? name.replaceAll("_", " ")}</span>
            <div className="formula-block">
              <span className="formula-display" aria-label={source}>{DISPLAY[name] ?? source}</span>
              <details className="formula-source">
                <summary>LaTeX source</summary>
                <code>{String.raw`\(${latex}\)`}</code>
              </details>
            </div>
            <span className="sr-only">{source}</span>
          </li>
        );
      })}
    </ul>
  );
}
