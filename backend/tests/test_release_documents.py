"""Generated guide and registry remain tied to the scientific source files."""
import json
from zipfile import ZipFile
from app.models.provenance import SourceRegistry
from app.services.geospatial_service import BACKEND_ROOT


def test_registry_schema_and_record_fields():
    payload = json.loads((BACKEND_ROOT / "data/manifests/acquisition-v1/source-registry.json").read_text(encoding="utf-8"))
    registry = SourceRegistry.model_validate(payload)
    assert len(registry.sites) == 14
    for record in registry.records:
        if record.artifact:
            assert record.sha256 and record.byte_size > 0
    schema = json.loads((BACKEND_ROOT / "app/data/source-registry.schema.json").read_text(encoding="utf-8"))
    assert schema == SourceRegistry.model_json_schema()


def test_master_guide_numbers_and_all_sections_match_generated_blocks():
    docs = BACKEND_ROOT.parent / "docs"
    blocks = json.loads((docs / "system-guide-content.json").read_text(encoding="utf-8"))
    assert len([b for b in blocks if b["type"] == "h1"]) == 40
    paper = json.loads((docs / "paper/paper-data.json").read_text(encoding="utf-8"))
    text = (docs / "ALTERECHO_SYSTEM_AND_RESEARCH_GUIDE.md").read_text(encoding="utf-8")
    assert str(paper["example"]["observed_index_full"]) in text
    for feature in paper["example"]["features"].values():
        assert str(feature["d"]) in text and str(feature["tau"]) in text


def test_editable_guide_has_native_equations():
    path = BACKEND_ROOT.parent / "docs/ALTERECHO_SYSTEM_AND_RESEARCH_GUIDE.docx"
    with ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode()
    assert xml.count("<m:oMath>") == 12
    assert "<m:f>" in xml and "<m:sSub>" in xml and "<m:sSup>" in xml
    assert "40 References" in xml
