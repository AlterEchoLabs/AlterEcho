import json

from app.services.integrity_service import validate_catalog_integrity


def main() -> None:
    failures = validate_catalog_integrity()
    if failures:
        print(json.dumps({"status": "failed", "errors": failures}, indent=2))
        raise SystemExit(1)
    print(json.dumps({"status": "passed", "scope": "artifact integrity only", "scientific_validation": "not performed"}, indent=2))


if __name__ == "__main__":
    main()
