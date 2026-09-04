
from warrant.adapters.linear import _parse_dto
from warrant.adapters.linear_fixture import STUB_LINEAR_ISSUE


def test_dto_parses_fixture():
    dto = _parse_dto(STUB_LINEAR_ISSUE, source_label="linear-stub")
    assert dto.id == "stub-uuid-0000-0000-0000-000000000001"
    assert dto.identifier == "ENG-001"
    assert dto.title == "[SIMULATED] Fix memory leak in agent runner"
    assert dto.priority == 2
    assert dto.priority_label == "high"
    assert dto.team.key == "ENG"
    assert dto.state.name == "In Progress"
    assert dto.assignee is not None
    assert dto.assignee.name == "Alice"
    assert len(dto.labels) == 1
    assert dto.labels[0].name == "bug"


def test_priority_label_mapping():
    base = dict(STUB_LINEAR_ISSUE)
    
    base["priority"] = 0
    assert _parse_dto(base, "l").priority_label == "none"
    
    base["priority"] = 1
    assert _parse_dto(base, "l").priority_label == "urgent"
    
    base["priority"] = 2
    assert _parse_dto(base, "l").priority_label == "high"
    
    base["priority"] = 3
    assert _parse_dto(base, "l").priority_label == "medium"
    
    base["priority"] = 4
    assert _parse_dto(base, "l").priority_label == "low"


def test_to_warrant_fields():
    dto = _parse_dto(STUB_LINEAR_ISSUE, source_label="linear-stub")
    fields = dto.to_warrant_fields("Normalised body text.")
    
    assert fields == {
        "external_key": "ENG-001",
        "title": "[SIMULATED] Fix memory leak in agent runner",
        "body_normalised": "Normalised body text.",
        "team": "Engineering",
        "labels": ["bug"],
        "priority": "high",
        "updated_at": "2024-09-01T12:00:00+00:00",
        "path_hints": [],
    }
    
    # Must not contain linear-specific raw fields
    assert "description" not in fields
    assert "url" not in fields
    assert "id" not in fields


def test_to_adapter_metadata():
    dto = _parse_dto(STUB_LINEAR_ISSUE, source_label="linear-stub")
    meta = dto.to_adapter_metadata()
    
    assert meta["external_id"] == "stub-uuid-0000-0000-0000-000000000001"
    assert meta["url"] == "https://linear.app/example-org/issue/ENG-001"
    assert meta["state"] == "In Progress"
    assert meta["assignee"] == "Alice"
    assert meta["team_key"] == "ENG"
    assert meta["external_created_at"] == "2024-08-28T09:00:00+00:00"
    
    # Raw description MUST NOT be stored, only SHA-256
    assert "description" not in meta
    assert len(meta["description_sha256"]) == 64


def test_adapter_metadata_no_assignee():
    base = dict(STUB_LINEAR_ISSUE)
    base["assignee"] = None
    dto = _parse_dto(base, "l")
    
    meta = dto.to_adapter_metadata()
    assert meta["assignee"] is None


def test_fingerprint_stability():
    dto = _parse_dto(STUB_LINEAR_ISSUE, source_label="linear-stub")
    fp1 = dto.content_fingerprint("Norm")
    fp2 = dto.content_fingerprint("Norm")
    assert fp1 == fp2
    
    # Different body -> different fingerprint
    fp3 = dto.content_fingerprint("Changed")
    assert fp1 != fp3
