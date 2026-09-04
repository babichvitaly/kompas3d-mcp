import math

import pytest
from pydantic import ValidationError

from kompas_mcp.backend import Kompas, output_path
from kompas_mcp.models import ExtrusionSpec, SketchSpec


@pytest.mark.parametrize("radius", [0, -1, math.inf, math.nan])
def test_invalid_dimensions_rejected_before_com(radius):
    with pytest.raises(ValidationError):
        SketchSpec(curves=[{"kind": "circle", "radius": radius}])


def test_closed_polyline_has_no_degenerate_closing_edge():
    with pytest.raises(ValidationError):
        SketchSpec(curves=[{"kind": "polyline", "points": [[0, 0], [1, 0], [0, 0]]}])
    axis = SketchSpec(
        curves=[
            {"kind": "polyline", "points": [[0, 0], [0, 10]], "closed": False, "construction": True}
        ]
    )
    assert axis.curves[0].construction


def test_unknown_fields_and_negative_depth_are_not_silently_ignored():
    with pytest.raises(ValidationError):
        ExtrusionSpec(sketch_id="x", depth=-5)
    with pytest.raises(ValidationError):
        SketchSpec(curves=[{"kind": "circle", "radius": 2, "diameter": 10}])


def test_entity_cannot_cross_documents():
    backend = Kompas()
    entity = object()
    token = backend.remember("first", entity)
    assert backend.entity("first", token) is entity
    with pytest.raises(ValueError):
        backend.entity("second", token)


def test_save_rejects_existing_files_and_relative_paths(tmp_path):
    target = tmp_path / "part.m3d"
    target.write_bytes(b"existing model")
    with pytest.raises(FileExistsError):
        output_path(str(target), {".m3d"})
    assert target.read_bytes() == b"existing model"
    assert output_path(str(target), {".m3d"}, True) == target
    with pytest.raises(ValueError):
        output_path("part.m3d", {".m3d"})
