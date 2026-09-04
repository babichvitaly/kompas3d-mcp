from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from kompas_mcp import bridge
from kompas_mcp.advanced_models import ApiBatch, FeatureSettings
from kompas_mcp.backend import Kompas
from kompas_mcp.features import configure


@pytest.mark.parametrize(
    "steps",
    [
        [{"id": "a", "target": {"ref": "later"}, "member": "Update"}],
        [
            {"id": "a", "target": {"handle": "x"}, "member": "Update"},
            {"id": "a", "target": {"handle": "x"}, "member": "Update"},
        ],
    ],
)
def test_batch_rejects_forward_references_and_duplicate_ids(steps):
    with pytest.raises(ValidationError):
        ApiBatch(steps=steps)


def test_batch_resolves_returned_handles_and_stops_on_false(monkeypatch):
    backend = Kompas()
    root = SimpleNamespace(_oleobj_=object())
    child = SimpleNamespace(_oleobj_=object())
    handle = backend.pack(root)["handle"]
    calls = []

    def invoke(k, obj, member, action, arguments, value):
        calls.append((obj, member))
        if member == "Child":
            return child
        assert obj is child
        return False

    monkeypatch.setattr(bridge, "invoke", invoke)
    plan = ApiBatch(
        steps=[
            {"id": "child", "target": {"handle": handle}, "member": "Child"},
            {"id": "failure", "target": {"ref": "child"}, "member": "Create", "expect": "truthy"},
            {"id": "never", "target": {"ref": "child"}, "member": "Update"},
        ]
    )
    result = bridge.batch(backend, plan)
    assert not result["completed"]
    assert result["failed_step"] == "failure"
    assert result["results"]["failure"] is False
    assert [member for _, member in calls] == ["Child", "Create"]
    assert "never" not in result["results"]


def test_feature_foreign_reference_rejected_before_properties_change(monkeypatch):
    backend = Kompas()
    foreign = backend.remember("other", object())
    definition = SimpleNamespace(radius=1)
    monkeypatch.setattr(bridge, "describe_type", lambda cls: {"writable": ["radius", "support"]})
    with pytest.raises(ValueError, match="does not belong"):
        configure(
            backend,
            "target",
            definition,
            FeatureSettings(properties={"radius": 3, "support": {"entity_id": foreign}}),
        )
    assert definition.radius == 1
