"""One-time, verifiable migration of terrain-v3 checksum sidecars to newline-canonical SHA-256.

Background: terrain-v3 artifacts were written on Windows in text mode (CRLF) and their
``.sha256`` sidecars recorded the CRLF bytes. The repository snapshot stores the same JSON
with LF line endings, so the raw-byte check reported every artifact as stale and the API
demoted all real sites to ``unavailable``.

This script rewrites a sidecar ONLY when the recorded checksum equals the SHA-256 of the
current file converted back to CRLF. That proves the JSON content is byte-for-byte identical
apart from line endings. Any other mismatch is reported and left untouched.

Usage (from ``backend/``)::

    python -m app.scripts.migrate_text_checksums            # dry run
    python -m app.scripts.migrate_text_checksums --apply
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json

from app.services.geospatial_service import GEO_DATA, canonical_text_sha256


def plan() -> list[dict]:
    rows = []
    for artifact in sorted((GEO_DATA / "processed").glob("*.terrain-v3.json")):
        sidecar = artifact.with_suffix(".sha256")
        recorded = sidecar.read_text(encoding="ascii").strip() if sidecar.exists() else None
        lf_bytes = artifact.read_bytes().replace(b"\r\n", b"\n")
        canonical = sha256(lf_bytes).hexdigest()
        crlf = sha256(lf_bytes.replace(b"\n", b"\r\n")).hexdigest()
        if recorded == canonical:
            status = "already_canonical"
        elif recorded == crlf:
            status = "verified_newline_only_difference"
        else:
            status = "content_mismatch_not_migrated"
        rows.append({"artifact": artifact.name, "recorded": recorded, "canonical": canonical, "status": status})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="rewrite verified sidecars")
    args = parser.parse_args()
    rows = plan()
    for row in rows:
        if args.apply and row["status"] == "verified_newline_only_difference":
            (GEO_DATA / "processed" / row["artifact"]).with_suffix(".sha256").write_text(row["canonical"], encoding="ascii", newline="\n")
            row["status"] = "migrated"
            assert canonical_text_sha256(GEO_DATA / "processed" / row["artifact"]) == row["canonical"]
    print(json.dumps(rows, indent=2))
    if any(row["status"] == "content_mismatch_not_migrated" for row in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
