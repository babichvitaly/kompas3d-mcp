import pytest

from kompas_mcp.assemblies import rigid_matrix, same_placements
from kompas_mcp.audit import IDENTITY


def test_source_replacement_may_change_path_but_never_placement():
    before = [{"index": 0, "source": "old.m3d", "matrix": IDENTITY.copy()}]
    after = [{"index": 0, "source": "new.m3d", "matrix": IDENTITY.copy()}]
    same_placements(before, after)
    after[0]["matrix"][12] = .001
    with pytest.raises(ValueError, match="placement"):
        same_placements(before, after)


def test_placement_check_rejects_missing_component_or_nonfinite_matrix():
    before = [{"index": 0, "matrix": IDENTITY.copy()}]
    with pytest.raises(ValueError, match="count"):
        same_placements(before, [])
    after = [{"index": 0, "matrix": IDENTITY.copy()}]
    after[0]["matrix"][0] = float("nan")
    with pytest.raises(ValueError, match="placement"):
        same_placements(before, after)


def test_rigid_matrix_accepts_rotation_and_translation():
    matrix = [0., -1., 0., 0., 1., 0., 0., 0., 0., 0., 1., 0., 10., -20., 4., 1.]
    assert rigid_matrix(matrix) == matrix


@pytest.mark.parametrize("index,value", [(0, 2.), (4, .1), (0, -1.), (3, 1.),
                                          (15, 0.), (12, float("nan"))])
def test_rigid_matrix_rejects_scale_shear_mirror_projective_and_nonfinite(index, value):
    matrix = IDENTITY.copy()
    matrix[index] = value
    with pytest.raises(ValueError):
        rigid_matrix(matrix)
