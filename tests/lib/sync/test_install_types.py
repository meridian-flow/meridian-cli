import pytest

from meridian.lib.sync.install_types import ItemRef, format_item_id, parse_item_id, validate_source_name


def test_item_ref_roundtrip_from_item_id() -> None:
    item = ItemRef.from_item_id("agent:dev-orchestrator")

    assert item.kind == "agent"
    assert item.name == "dev-orchestrator"
    assert item.item_id == "agent:dev-orchestrator"


def test_parse_item_id_rejects_invalid_shape() -> None:
    with pytest.raises(ValueError, match="expected canonical 'agent:name' or 'skill:name'"):
        parse_item_id("dev-orchestrator")


def test_format_item_id_normalizes_name() -> None:
    assert format_item_id("skill", " dev-workflow ") == "skill:dev-workflow"


def test_validate_source_name_rejects_spaces() -> None:
    with pytest.raises(ValueError, match="alphanumeric characters, hyphens, or underscores"):
        validate_source_name("bad source")
