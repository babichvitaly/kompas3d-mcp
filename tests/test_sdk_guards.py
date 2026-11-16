"""Offline synthetic contracts only. Never connects to KOMPAS/COM."""

from types import SimpleNamespace as NS

import pytest

from kompas_mcp import documents, tracked_import, variable_names
from kompas_mcp.backend import Kompas
from kompas_mcp.color_state import color_state
from kompas_mcp.models import SketchSpec
from kompas_mcp.plane_geometry import offset_for_displacement, plane_frame

# Synthetic measured frames with independently specified world-axis expectations.
FRAMES = [
    ([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [0, 0, 1]),
    ([[0, 0, 0], [0, 0, 1], [0, 1, 0]], [-1, 0, 0]),
    ([[0, 0, 0], [1, 0, 0], [0, 0, -1]], [0, 1, 0]),
]


@pytest.mark.parametrize('points,normal', FRAMES, ids=['XY', 'YZ', 'XZ'])
@pytest.mark.parametrize('sign', [-1, 1])
def test_offset_sign_matrix_from_measured_frame(points, normal, sign):
    assert plane_frame(points)['normal'] == normal
    axis = next(i for i, v in enumerate(normal) if v)
    delta = [0, 0, 0]
    delta[axis] = sign * 8
    result = offset_for_displacement(points, delta)
    expected_signed = sign * 8 * normal[axis]
    assert result == {'offset': expected_signed, 'distance': 8,
                      'direction': expected_signed > 0}


def test_offset_uses_rotated_frame_and_rejects_non_normal_displacement():
    points = [[3, 4, 5], [3, 5, 5], [3, 4, 6]]  # normal +X, no plane name
    assert offset_for_displacement(points, [-9, 0, 0])['offset'] == -9
    with pytest.raises(ValueError, match='parallel'):
        offset_for_displacement(points, [9, 1, 0])


@pytest.mark.parametrize('points', [
    [[0, 0, 0], [0, 0, 0], [0, 1, 0]],
    [[0, 0, 0], [2, 0, 0], [0, 1, 0]],
    [[0, 0, 0], [1, 0, 0], [1, 0, 0]],
    [[float('nan'), 0, 0], [1, 0, 0], [0, 1, 0]],
])
def test_bad_frame_fails_closed(points):
    with pytest.raises(ValueError):
        plane_frame(points)


@pytest.mark.parametrize('bad', ['mismatch', 'native_failure', 'degenerate'])
def test_create_sketch_blocks_begin_edit_before_wrong_world_geometry(monkeypatch, bad):
    calls = []
    definition = NS(SetPlane=lambda plane: True, BeginEdit=lambda: calls.append('BeginEdit'))
    entity = NS(GetDefinition=lambda: definition, Create=lambda: True)
    part = NS(GetDefaultEntity=lambda _: object(), NewEntity=lambda _: entity)
    k = NS(invalidate_topology=lambda: None, document=lambda _: NS(GetPart=lambda _: part),
           constants={'o3d_planeXOY': 1, 'o3d_sketch': 2, 'ksAPI7Dual': 3},
           app=NS(TransferInterface=lambda *args: object()))
    def point(x, y):
        if bad == 'native_failure':
            return (False, 0, 0, 0)
        return (True, 0 if bad == 'degenerate' else x, y, 2)
    monkeypatch.setattr(documents, '_cast', lambda *args: NS(GetPoint3D=point))
    spec = SketchSpec(curves=[{'kind': 'circle', 'center': [0, 0], 'radius': 1}],
                      expected_world_points=FRAMES[0][0])
    with pytest.raises((ValueError, RuntimeError)):
        Kompas.sketch(k, 'doc', spec)
    assert calls == []


def test_namespace_repeated_operations_casefold_and_existing_user_variable():
    names = {'Hole_D0', 'HOLE_2_X1', 'Unrelated_X1'}
    assert variable_names.reserve_prefix('Hole', names) == 'Hole_3'
    names.add('Hole_3_D0')
    assert variable_names.reserve_prefix('Hole', names) == 'Hole_4'
    assert variable_names.reserve_prefix('Fresh', names) == 'Fresh'


def test_native_inventory_refresh_and_no_silent_reuse(monkeypatch):
    from kompas_mcp import parameters
    calls = []
    names = []
    collection = NS(refresh=lambda: calls.append('refresh') or True,
                    GetCount=lambda: len(names), GetByIndex=lambda i: NS(name=names[i]),
                    GetByName=lambda *args: None)
    part = NS(GetFeature=lambda: NS(VariableCollection=collection))
    k = NS(document=lambda _: NS(GetPart=lambda _: part))
    # Exercise the real parameters._collection refresh contract.
    assert parameters._collection(k, 'doc', None) is collection
    variable_names.ensure_unused(k, 'doc', 'Hole_D0')
    names.append('HOLE_D0')  # a preceding native operation committed it
    with pytest.raises(ValueError, match='refusing reuse'):
        variable_names.ensure_unused(k, 'doc', 'Hole_D0')
    assert len(calls) == 3


@pytest.mark.parametrize('scope,flag,state', [
    ('root', -1, 'root_undefined'), ('root', None, 'root_undefined'),
    ('occurrence', 0, 'defined'), ('occurrence', 1, 'defined'),
    ('occurrence', -1, 'unknown'),
])
def test_color_raw_state_preserved_without_false_appearance_acceptance(scope, flag, state):
    result = color_state(NS(Color=0x3278AB, UseColor=flag), scope, 0x3278AB)
    assert result['use_color_raw'] == flag
    assert result['use_color_state'] == state
    assert result['color_matches'] is True
    assert result['appearance_verified'] is False


def import_fixture(tmp_path, monkeypatch, mode='part'):
    source = tmp_path / 'sample.step'
    source.write_text('synthetic STEP placeholder; never passed to CAD')
    owned = tmp_path / 'owned'
    owned.mkdir()
    extension = '.a3d' if mode == 'assembly' else '.m3d'
    target = owned / ('result' + extension)
    prior = NS(Reference=1, PathName=str(tmp_path / 'user.m3d'), DocumentType=10, Changed=False, ReadOnly=True)
    doc = NS(Reference=2, PathName=str(source.with_suffix(extension)),
             DocumentType=20 if mode == 'assembly' else 10, ReadOnly=False, Changed=True)
    rows, saves = [prior], []
    def open_doc(*args):
        if mode == 'reuse':
            return prior
        rows.append(doc)
        if mode == 'extra':
            rows.append(NS(Reference=3, PathName='', DocumentType=10, Changed=True, ReadOnly=False))
        if mode == 'changed_prior':
            prior.PathName = 'unexpected'
        if mode == 'prior_changed_flag':
            prior.Changed = True
        if mode == 'prior_readonly_flag':
            prior.ReadOnly = False
        if mode == 'wrong_path':
            doc.PathName = str(tmp_path / 'other.m3d')
        if mode == 'source_changed':
            source.write_text('changed')
        if mode == 'wrong_kind':
            doc.DocumentType = 99
        if mode == 'converted_readonly':
            doc.ReadOnly = True
        if mode == 'invalid_reference':
            doc.Reference = 0
        return doc
    def save(path):
        saves.append(path)
        if mode != 'save_noop':
            target.write_text('synthetic native output')
            doc.PathName, doc.Changed = path, False
            if mode == 'save_changed_prior':
                prior.PathName = 'changed during save'
            if mode == 'save_kind_change':
                doc.DocumentType = 20
            if mode == 'save_readonly_change':
                doc.ReadOnly = True
    doc.SaveAs = save
    collection = NS(Count=0, Item=lambda i: rows[i], Open=open_doc)
    class Collection:
        @property
        def Count(self):
            return len(rows)
        Item = staticmethod(collection.Item)
        Open = staticmethod(open_doc)
    k = NS(connect=lambda: None, app=NS(ksGetApplication7=lambda: NS(Documents=Collection())),
           constants={'ksDocumentPart': 10, 'ksDocumentAssembly': 20}, owned_documents=set())
    monkeypatch.setattr(tracked_import, '_info', lambda *args: {'kind': mode})
    return k, source, owned, target, saves


@pytest.mark.parametrize('kind', ['part', 'assembly'])
def test_tracked_import_actual_native_extension_and_verified_save(tmp_path, monkeypatch, kind):
    k, source, owned, target, saves = import_fixture(tmp_path, monkeypatch, kind)
    result = tracked_import.import_step(k, str(source), str(owned), str(target))
    assert saves == [str(target)]
    assert k.owned_documents == {'2'}
    assert result['save_evidence']['write_evidence'] == 'created'
    assert not result['geometry_verified'] and not result['reopen_verified']
    assert result['changed_after_import'] is True
    assert result['created_reference'] == '2' and len(result['import_call_id']) == 32
    assert result['converted_path'] == str(source.with_suffix(target.suffix))
    assert result['inventory_after_open']['2'][2] is True
    assert result['inventory_after_save']['2'][2] is False


@pytest.mark.parametrize('mode', ['reuse', 'extra', 'changed_prior', 'wrong_path',
                                 'source_changed', 'save_noop', 'save_changed_prior',
                                 'prior_changed_flag', 'prior_readonly_flag', 'wrong_kind',
                                 'converted_readonly', 'save_kind_change', 'save_readonly_change',
                                 'invalid_reference'])
def test_uncertain_import_never_adopts_or_closes_unknown_documents(tmp_path, monkeypatch, mode):
    k, source, owned, target, saves = import_fixture(tmp_path, monkeypatch, mode)
    with pytest.raises(RuntimeError):
        tracked_import.import_step(k, str(source), str(owned), str(target))
    assert k.owned_documents == set()
    assert saves == ([str(target)] if mode in {'save_noop', 'save_changed_prior', 'save_kind_change', 'save_readonly_change'} else [])


def test_import_existing_target_and_outside_root_rejected_before_connection(tmp_path, monkeypatch):
    k, source, owned, target, saves = import_fixture(tmp_path, monkeypatch)
    k.connect = lambda: pytest.fail('must reject before COM')
    target.write_text('preserve')
    with pytest.raises(FileExistsError):
        tracked_import.import_step(k, str(source), str(owned), str(target))
    with pytest.raises(ValueError):
        tracked_import.import_step(k, str(source), str(owned), str(tmp_path / 'outside.m3d'))
    assert target.read_text() == 'preserve'
    assert not saves


def test_native_lookup_blocks_variable_omitted_by_enumeration(monkeypatch):
    from kompas_mcp import parameters

    collection = NS(GetCount=lambda: 0, GetByName=lambda *args: NS(name="Hidden_D0"))
    monkeypatch.setattr(parameters, '_collection', lambda *args: collection)
    with pytest.raises(ValueError, match='refusing reuse'):
        variable_names.ensure_unused(None, 'doc', 'Hidden_D0')


def test_ordinary_native_open_does_not_adopt_step_conversion(tmp_path):
    source = tmp_path / 'fixture.step'
    source.write_text('synthetic')
    k = NS(connect=lambda: pytest.fail('Ordinary open must reject STEP before connect'))
    with pytest.raises(ValueError, match='native KOMPAS'):
        documents.open_document(k, str(source))


def test_import_call_tokens_are_distinct_and_paths_remain_call_specific(tmp_path, monkeypatch):
    receipts = []
    for name in ['call-one', 'call-two']:
        folder = tmp_path / name
        folder.mkdir()
        k, source, owned, target, _ = import_fixture(folder, monkeypatch)
        receipt = tracked_import.import_step(k, str(source), str(owned), str(target))
        assert receipt['import_source'] == str(source)
        assert receipt['saved_path'] == str(target)
        receipts.append(receipt)
    assert receipts[0]['import_call_id'] != receipts[1]['import_call_id']
    assert receipts[0]['import_source'] != receipts[1]['import_source']
