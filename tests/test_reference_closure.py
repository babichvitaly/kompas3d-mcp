"""Pure synthetic paths and placements; no product geometry or CAD access."""

from copy import deepcopy

import pytest

from kompas_mcp.reference_closure import (
    assess_ram_reference_aliases,
    assess_saved_reference_closure,
)

MATRIX = [1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.]


def fixture():
    plan = {'owned_root': '/new-run', 'source_parent': '/baseline/parent.a3d',
            'parent_copy': '/new-run/parent.a3d', 'bytecopy_sha256': 'a'*64,
            'immutable_sources': {'/baseline/parent.a3d': 'a'*64,
                                 '/old-run/sub/case.a3d': 'b'*64,
                                 '/old-run/components/panel.m3d': 'c'*64},
            'semantics_sha256': 'e'*64, 'direct_rebind_slots': [[0], [1]],
            'links': [
                {'slot': [0], 'destination': '/new-run/sub/case.a3d', 'sha256': 'b'*64,
                 'matrix': MATRIX, 'ram_aliases': [{'path': '/old-run/sub/case.a3d', 'sha256': 'b'*64}]},
                {'slot': [0, 0], 'destination': '/new-run/components/panel.m3d', 'sha256': 'c'*64,
                 'matrix': MATRIX, 'ram_aliases': [{'path': '/old-run/components/panel.m3d', 'sha256': 'c'*64}]},
                {'slot': [1], 'destination': '/new-run/components/plug.m3d', 'sha256': 'd'*64,
                 'matrix': MATRIX, 'ram_aliases': []}]}
    ram = {'parent_path': plan['parent_copy'], 'parent_sha256': 'a'*64, 'complete_scan': True,
           'semantics_sha256': 'e'*64, 'immutable_source_hashes': deepcopy(plan['immutable_sources']),
           'links': [
               {'slot': [0], 'parent_path': plan['parent_copy'], 'parent_sha256': 'a'*64,
                'raw_reference': '../old-run/sub/case.a3d', 'resolved_path': '/old-run/sub/case.a3d',
                'sha256': 'b'*64, 'matrix': MATRIX},
               {'slot': [0, 0], 'parent_path': '/old-run/sub/case.a3d', 'parent_sha256': 'b'*64,
                'raw_reference': '../components/panel.m3d', 'resolved_path': '/old-run/components/panel.m3d',
                'sha256': 'c'*64, 'matrix': MATRIX},
               {'slot': [1], 'parent_path': plan['parent_copy'], 'parent_sha256': 'a'*64,
                'raw_reference': 'components/plug.m3d', 'resolved_path': '/new-run/components/plug.m3d',
                'sha256': 'd'*64, 'matrix': MATRIX}]}
    saved_graph = deepcopy(ram)
    saved_graph['parent_sha256'] = 'f'*64
    for i, link in enumerate(saved_graph['links']):
        link['resolved_path'] = plan['links'][i]['destination']
        if len(link['slot']) == 1:
            link['parent_sha256'] = 'f'*64
    saved_graph['links'][0]['raw_reference'] = 'sub/case.a3d'
    saved_graph['links'][1]['parent_path'] = '/new-run/sub/case.a3d'
    saved = {'ram_before_rebind': deepcopy(ram), 'save_confirmed': True, 'closed_after_save': True,
             'direct_rebind_slots': [[0], [1]], 'sealed_parent_sha256': 'f'*64,
             'cycles': [{'open_id': f'fresh-open-{i}', 'read_only': True,
                         'snapshot': deepcopy(saved_graph)} for i in range(2)]}
    return deepcopy(plan), deepcopy(ram), saved


def test_ram_same_bytes_alias_is_accepted_only_as_transient_nonpersisted_state():
    plan, ram, _ = fixture()
    result = assess_ram_reference_aliases(plan, ram)
    assert result['status'] == 'consistent_offline_evidence'
    assert result['ram_alias_slots'] == [[0], [0, 0]]
    assert not result['persisted_closure_verified'] and result['native_acceptance'] == 'pending'


def test_direct_rebind_then_save_close_fresh_ro_updates_nested_contexts():
    plan, _, saved = fixture()
    result = assess_saved_reference_closure(plan, saved)
    assert result['status'] == 'consistent_offline_evidence'
    assert result['persisted_paths_consistent_in_saved_evidence']
    assert result['native_acceptance'] == 'pending' and not result['package_portability_verified']


@pytest.mark.parametrize('path,value', [
    (('links', 0, 'resolved_path'), '/unknown/case.a3d'),
    (('links', 0, 'sha256'), 'f'*64),
    (('links', 1, 'parent_sha256'), 'f'*64),
    (('parent_sha256',), 'f'*64), (('complete_scan',), False),
    (('links', 0, 'matrix'), [0.]*16),
    (('immutable_source_hashes', '/old-run/components/panel.m3d'), 'f'*64),
])
def test_ram_alias_acceptance_requires_exact_inventory_hash_provenance_and_pose(path, value):
    plan, ram, _ = fixture()
    target = ram
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert assess_ram_reference_aliases(plan, ram)['status'] == 'rejected'


@pytest.mark.parametrize('path,value', [
    (('cycles', 0, 'snapshot', 'links', 0, 'raw_reference'), '../old-run/sub/case.a3d'),
    (('cycles', 0, 'snapshot', 'links', 0, 'resolved_path'), '/old-run/sub/case.a3d'),
    (('cycles', 1, 'snapshot', 'links', 1, 'parent_path'), '/old-run/sub/case.a3d'),
    (('cycles', 1, 'snapshot', 'links', 1, 'matrix'), [0.]*16),
    (('closed_after_save',), False), (('save_confirmed',), False),
    (('cycles', 0, 'read_only'), False), (('cycles', 1, 'open_id'), 'fresh-open-0'),
    (('direct_rebind_slots',), [[0, 0]]),
    (('cycles', 1, 'snapshot', 'parent_sha256'), 'a'*64),
])
def test_saved_ro_never_inherits_ram_alias_permission(path, value):
    plan, _, saved = fixture()
    target = saved
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert assess_saved_reference_closure(plan, saved)['status'] == 'rejected'


def test_complete_scan_claim_cannot_hide_a_missing_nested_link():
    plan, _, saved = fixture()
    saved['cycles'][1]['snapshot']['links'].pop(1)
    assert assess_saved_reference_closure(plan, saved)['status'] == 'rejected'


def test_alias_sha_equality_must_be_independently_pinned_not_just_claimed():
    plan, ram, _ = fixture()
    plan['links'][0]['ram_aliases'][0]['sha256'] = 'f'*64
    assert assess_ram_reference_aliases(plan, ram)['status'] == 'rejected'


def test_windows_relative_references_and_case_normalization_in_saved_evidence():
    plan, _, saved = fixture()
    def convert(value):
        if isinstance(value, dict):
            return {convert(k): convert(v) for k, v in value.items()}
        if isinstance(value, list):
            return [convert(v) for v in value]
        if isinstance(value, str) and value.startswith('/'):
            return 'C:' + value.replace('/', '\\')
        return value
    plan, saved = convert(plan), convert(saved)
    saved['cycles'][1]['snapshot']['links'][0]['resolved_path'] = r'c:\NEW-RUN\sub\case.a3d'
    assert assess_saved_reference_closure(plan, saved)['status'] == 'consistent_offline_evidence'
