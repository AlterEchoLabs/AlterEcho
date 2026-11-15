"""Scan tracked text for credential values; reports filenames, never matched secrets."""
import json
from pathlib import Path
import re
import subprocess


def scan(root: Path) -> list[str]:
    names = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root).decode().split("\0")
    patterns = [r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----", r"\bgh[pousr]_[A-Za-z0-9]{30,}",
                r"\bAKIA[0-9A-Z]{16}\b", r"(?im)^\s*(?:EARTHDATA_TOKEN|EARTHDATA_PASSWORD|CDSE_CLIENT_SECRET)\s*=\s*['\"]?[A-Za-z0-9_+/.-]{16,}",
                r"https://[^\s\"']+[?&]sig=[A-Za-z0-9%+/]{20,}"]
    findings = []
    for name in names:
        p = root / name
        if not name or not p.is_file() or p.stat().st_size > 10_000_000:
            continue
        try:
            content = p.read_text(encoding="utf-8")
        except UnicodeError:
            continue
        if any(re.search(pattern, content) for pattern in patterns):
            findings.append(name)
    return findings


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[3]
    findings = scan(root)
    print(json.dumps({"scope": "tracked and nonignored new UTF-8 files <=10 MB; recognizable credential patterns only", "files_with_findings": findings}))
    raise SystemExit(bool(findings))
