"""Generated-interface regression: IFeature7 need not expose Reference."""

from types import SimpleNamespace as NS

import pytest

from kompas_mcp import documents
from kompas_mcp.model_identity import model_reference


class FeatureInterface:
    __slots__ = ('deleted',)

    def __init__(self):
        self.deleted = False

    def __getattr__(self, name):
        # No dynamic Dispatch fallback, including Reference.
        raise AttributeError(f'IFeature7 has no generated member: {name}')

    def Delete(self):
        self.deleted = True
        return True


@pytest.mark.parametrize('expected', [417, 999])
def test_identity_check_casts_before_delete_without_feature_reference(monkeypatch, expected):
    feature = FeatureInterface()
    with pytest.raises(AttributeError, match='Reference'):
        _ = feature.Reference
    part_interface = NS(Reference=417)  # IPart7 may independently expose Reference.
    assert part_interface.Reference == 417
    casts = []

    def cast(k, obj, interface):
        assert obj is feature
        casts.append(interface)
        assert interface == 'IModelObject'
        return NS(Reference=417)

    monkeypatch.setattr(documents, '_cast', cast)
    if expected == 417:
        assert model_reference(None, feature, expected) == 417
        assert feature.Delete()
    else:
        with pytest.raises(ValueError, match='mutation blocked'):
            model_reference(None, feature, expected)
        assert not feature.deleted
    assert casts == ['IModelObject']


def test_cast_failure_blocks_mutation_without_fallback(monkeypatch):
    feature = FeatureInterface()

    def cast(*args):
        raise RuntimeError('synthetic QueryInterface failure')

    monkeypatch.setattr(documents, '_cast', cast)
    with pytest.raises(RuntimeError, match='QueryInterface'):
        model_reference(None, feature, 417)
    assert not feature.deleted


@pytest.mark.parametrize('native,expected', [('417', 417), (True, 417), (417, True)])
def test_reference_precondition_rejects_implicit_coercion(monkeypatch, native, expected):
    monkeypatch.setattr(documents, '_cast', lambda *args: NS(Reference=native))
    with pytest.raises(TypeError, match='integer'):
        model_reference(None, FeatureInterface(), expected)
