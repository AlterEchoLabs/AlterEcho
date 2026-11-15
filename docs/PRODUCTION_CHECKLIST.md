# Production review checklist

Started 15 November 2026 on clean `main`. Existing scientific artifacts are retained unless validation rejects them. Previous audit results are historical, not evidence that this checkout passes.

- [x] Read the requested audit and inspect active application, manifests and method.
- [x] Attempt baseline application/browser and backend tests: copied Python environments cannot start.
- [x] Restore test tooling in ignored `.venv-local`; allow an explicit browser-test Python interpreter.
- [x] Run baseline browser workflows and inspect screenshots.
- [x] Audit source files, checksums, AOIs, dates, roles and scoring eligibility.
- [x] Add a versioned source registry, schema, provenance export and negative validation tests.
- [x] Correct critical-family gating and any provenance integrity failures.
- [x] Reproduce worked example and discrimination; retain method parameters unless scientifically justified.
- [x] Complete acquisition instructions, system guide, public guide and diagrams.
- [x] Generate and visually inspect DOCX and PDF guides.
- [x] Run release tests, type checking, lint, build, security and browser checks.
- [x] Record exact results and unresolved scientific/data requirements in the handoff.

The completed software/document checks do not imply independent scientific validation. See RELEASE_HANDOFF.md sections 19?20 for explicit product-metadata, scientific and manual-accessibility gaps.
