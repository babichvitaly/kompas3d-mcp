"""Several synthetic circular Local cuts; one protected pre/post snapshot."""

from copy import deepcopy

import pytest

from kompas_mcp.marker_cleanup_batch import cleanup_local_marker_batch


def frame(key):
    return {'view_key': key, 'reference': 'ref-'+key, 'source': '/synthetic/source.m3d',
            'source_sha256': 'a'*64, 'matrix': [1., 0., 0., 0., 0., 1., 0., 0.,
                                                0., 0., 1., 0., 0., 0., 0., 1.],
            'scale': 1., 'x': 30., 'y': 40., 'angle': 0., 'local': True,
            'base_cut_reference': 'base-'+key, 'paper_crop_center': [0., 0.], 'paper_crop_radius': 10.}


def marker(key, name, centre, base=None):
    x, y = centre
    return {'reference': key+'/'+name, 'owner_view_key': key, 'drawing_type': 42,
            'valid': True, 'temp': False, 'associated': False, 'bounds': [x-1., y-1., x+1., y+1.],
            'base': base, 'properties': {'layer': 0, 'style': 1, 'angle': 0.}}


class Adapter:
    def __init__(self, keys=('cut-one', 'cut-two'), mode=None):
        self.frames = {k: frame(k) for k in keys}
        self.rows = {}
        for key in keys:
            values = [marker(key, 'inside', (0., 0.)),
                      marker(key, 'valid-base', (20., 20.), {'reference': 'real-base', 'drawing_type': 2, 'valid': True}),
                      marker(key, 'orphan', (30., 30.), {'reference': 'dead-base', 'drawing_type': 2, 'valid': False})]
            self.rows.update({m['reference']: m for m in values})
        self.collection = {ref: m['owner_view_key'] for ref, m in self.rows.items()}
        self.mode, self.snapshots, self.deleted, self.guards = mode, 0, [], 0

    def guard_owned_scope(self, keys):
        assert set(keys) == set(self.frames)
        self.guards += 1
        if self.mode == 'ownership_loss' and self.deleted:
            raise ValueError('Lost owned scope')

    def protected_snapshot(self):
        self.snapshots += 1
        fingerprint = 'b'*64
        if self.mode == 'protected_changed' and self.deleted:
            fingerprint = 'c'*64
        return {'fingerprint': fingerprint, 'references': ['protected-axis', 'protected-material'],
                'frames': deepcopy(self.frames)}

    def list_markers(self, key, limit):
        return [deepcopy(m) for ref, m in self.rows.items() if self.collection[ref] == key]

    def read_cut_frame(self, key):
        value = deepcopy(self.frames[key])
        if self.mode == 'pose_drift':
            value['x'] += 1
        return value

    def read_marker(self, ref):
        value = deepcopy(self.rows[ref])
        if self.mode == 'stale_whitelist':
            value['properties']['layer'] = 2
        return value

    def delete_marker(self, ref):
        self.deleted.append(ref)
        if self.mode == 'native_error':
            raise RuntimeError('Unknown Delete outcome')
        del self.rows[ref]
        if self.mode == 'lost_retained':
            self.rows.pop(ref.rsplit('/', 1)[0]+'/inside', None)
        return True

    def marker_valid(self, ref):
        return ref in self.rows


def run(adapter):
    return cleanup_local_marker_batch(adapter, list(adapter.frames.values()), 42, 2)


@pytest.mark.parametrize('count', [1, 2, 7])
def test_shared_pre_post_snapshot_for_all_cuts_and_exact_retained_markers(count):
    adapter = Adapter(tuple(f'synthetic-cut-{i}' for i in range(count)))
    result = run(adapter)
    assert result['status'] == 'marker_batch_verified_in_adapter'
    assert adapter.snapshots == result['snapshot_reads'] == 2
    assert len(result['deleted']) == count and len(adapter.rows) == 2*count
    assert result['native_acceptance'] == 'pending' and not result['retry_allowed']


@pytest.mark.parametrize('mutation', ['unknown_base', 'associated_orphan', 'foreign_owner',
                                     'protected_alias', 'duplicate_alias'])
def test_classify_entire_whitelist_before_any_deletion(mutation):
    adapter = Adapter()
    value = adapter.rows['cut-two/orphan']
    if mutation == 'unknown_base':
        value['base'] = None
    elif mutation == 'associated_orphan':
        value['associated'] = True
    elif mutation == 'foreign_owner':
        value['owner_view_key'] = 'foreign-view'
    elif mutation == 'protected_alias':
        value['reference'] = 'protected-axis'
    elif mutation == 'duplicate_alias':
        value['reference'] = 'cut-one/orphan'
    result = run(adapter)
    assert result['status'] == 'failed' and not result['mutation_possible']
    assert not adapter.deleted and adapter.snapshots == 1


@pytest.mark.parametrize('mode', ['pose_drift', 'stale_whitelist', 'protected_changed',
                                 'native_error', 'ownership_loss', 'lost_retained'])
def test_fresh_pose_reference_and_exit_protection_reject_uncertain_mutation_without_retry(mode):
    adapter = Adapter(mode=mode)
    result = run(adapter)
    assert result['status'] == 'failed'
    assert len(result['attempted_deletions']) == len(set(result['attempted_deletions']))
    assert not result['retry_allowed']
    if mode in {'pose_drift', 'stale_whitelist'}:
        assert not adapter.deleted
    if mode == 'ownership_loss':
        assert len(adapter.deleted) == 1 and adapter.snapshots == 1
        assert 'exit_check_error' in result
    if mode == 'native_error':
        assert len(adapter.deleted) == 1 and result['mutation_possible']


def test_no_project_specific_identifiers_or_paths_are_required():
    adapter = Adapter(('arbitrary-section-alpha', 'arbitrary-section-beta'))
    assert run(adapter)['status'] == 'marker_batch_verified_in_adapter'
