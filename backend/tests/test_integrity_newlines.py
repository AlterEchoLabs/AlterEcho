"""Regression: text-artifact checksums must survive CRLF/LF conversion (Phase 6 baseline fix)."""
from hashlib import sha256

from app.services.geospatial_service import canonical_text_sha256
from app.services.integrity_service import validate_catalog_integrity


def test_canonical_checksum_ignores_line_endings_but_not_content(tmp_path):
    lf, crlf, changed = tmp_path / "lf.json", tmp_path / "crlf.json", tmp_path / "changed.json"
    lf.write_bytes(b'{\n  "a": 1\n}')
    crlf.write_bytes(b'{\r\n  "a": 1\r\n}')
    changed.write_bytes(b'{\n  "a": 2\n}')
    assert canonical_text_sha256(lf) == canonical_text_sha256(crlf) == sha256(b'{\n  "a": 1\n}').hexdigest()
    assert canonical_text_sha256(changed) != canonical_text_sha256(lf)


def test_committed_catalog_passes_integrity():
    assert validate_catalog_integrity() == {}
