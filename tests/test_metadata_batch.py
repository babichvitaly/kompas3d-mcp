"""Synthetic call-count and safety contracts, no native timing claims."""

from copy import deepcopy

import pytest

from kompas_mcp import metadata_batch
from kompas_mcp.metadata_batch import run_metadata_batch

GUARD = {'owned_reference': 'owned-ref', 'owned_path': '/fixture/owned.cdw', 'owned': True,
         'owned_read_only': False, 'source_reference': 'source-ref',
         'source_path': '/fixture/source.m3d', 'source_read_only': True, 'source_changed': False}
STATE = {'number': 1, 'view_type': 7, 'source': '/fixture/source.m3d', 'source_sha256': 'a'*64,
         'matrix': [1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.],
         'scale': 1., 'x': 50., 'y': 60., 'angle': 0., 'bounds': [0., 0., 20., 30.],
         'objects': 12, 'unfold': False, 'geometry_digest': 'b'*64}
HASHES = {'/fixture/source.m3d': 'a'*64}


def rows(prefix, n):
    return [{'uuid': f'{prefix}-{i}', 'section': 2, 'columns': {'label': f'fixture-{i}',
             'count': '1'}, 'sync': True, 'edit_source': False} for i in range(n)]


class Adapter:
    def __init__(self, mode=None, n=127):
        self.mode = mode
        self.metadata = {'source_rows': rows('source', n), 'owned_rows': rows('owned', n),
                         'original_hashes': deepcopy(HASHES)}
        self.full_reads = 0
        self.row_reads = 0
        self.guard_reads = 0
        self.operations = []
        self.view_reads = 0

    def read_guard_state(self):
        self.guard_reads += 1
        guard = deepcopy(GUARD)
        if self.operations and isinstance(self.mode, tuple) and self.mode[0] == 'guard':
            guard[self.mode[1]] = self.mode[2]
        return guard

    def read_metadata(self, limits):
        self.full_reads += 1
        total_rows = self.metadata['source_rows'] + self.metadata['owned_rows']
        # Honor the adapter's pre-enumeration bound.
        if len(total_rows) > limits['max_rows']:
            raise ValueError('Metadata too large before native traversal')
        self.row_reads += len(total_rows)
        value = deepcopy(self.metadata)
        if self.full_reads == 2:
            if self.mode == 'unexpected_exit':
                value['owned_rows'][0]['columns']['label'] = 'surprise'
            elif self.mode == 'source_metadata':
                value['source_rows'][0]['sync'] = False
            elif self.mode == 'source_bytes':
                value['original_hashes']['/fixture/source.m3d'] = 'c'*64
            elif self.mode == 'duplicate_uuid':
                value['owned_rows'][1]['uuid'] = value['owned_rows'][0]['uuid']
        return value

    def execute_step(self, name):
        self.operations.append(name)
        if self.mode == 'native_exception':
            raise RuntimeError('Synthetic exception after partial mutation')
        if self.mode == 'planned_change':
            self.metadata['owned_rows'][0]['section'] = 3

    def read_view_state(self, name):
        self.view_reads += 1
        state = deepcopy(STATE)
        if self.mode == 'pose':
            state['x'] += 1
        if self.mode == 'geometry':
            state['geometry_digest'] = 'c'*64
        return state


def run(adapter, count=6, **kwargs):
    steps = [{'name': f'step-{i}', 'expected_view_state': deepcopy(STATE)} for i in range(count)]
    return run_metadata_batch(adapter, GUARD, HASHES, steps, **kwargs)


@pytest.mark.parametrize('count', [1, 6, 24])
def test_full_metadata_is_read_only_twice_cheap_checks_and_exact_view_reads_remain(count):
    adapter = Adapter()
    result = run(adapter, count)
    assert result['status'] == 'batch_verified_in_adapter'
    assert adapter.full_reads == result['full_metadata_reads'] == 2
    assert adapter.row_reads == 2 * (127+127)
    assert adapter.view_reads == count
    assert adapter.guard_reads >= 3*count + 4
    assert len(adapter.operations) == count
    assert result['native_acceptance'] == 'pending' and not result['retry_allowed']


@pytest.mark.parametrize('mode', ['unexpected_exit', 'source_metadata', 'source_bytes', 'duplicate_uuid'])
def test_unexpected_exit_mutation_and_readonly_source_change_are_rejected(mode):
    adapter = Adapter(mode)
    result = run(adapter)
    assert result['status'] == 'failed' and result['mutation_possible']
    assert adapter.full_reads == 2 and len(adapter.operations) == 6
    assert 'error' in result and not result['retry_allowed']


@pytest.mark.parametrize('key,value', [
    ('owned_reference', 'other'), ('owned_path', '/fixture/other.cdw'), ('owned', False),
    ('owned_read_only', True), ('source_reference', 'other'),
    ('source_path', '/fixture/other.m3d'), ('source_read_only', False), ('source_changed', True),
])
def test_each_fresh_cheap_guard_blocks_next_operation_and_unknown_exit_read(key, value):
    adapter = Adapter(('guard', key, value))
    result = run(adapter)
    assert result['status'] == 'failed' and len(adapter.operations) == 1
    assert adapter.full_reads == 1  # exit ownership guard failed before reading any payload
    assert 'exit_check_error' in result


@pytest.mark.parametrize('mode', ['pose', 'geometry', 'native_exception'])
def test_exact_step_checks_and_best_effort_exit_snapshot_survive_failure(mode):
    adapter = Adapter(mode)
    result = run(adapter)
    assert result['status'] == 'failed' and len(adapter.operations) == 1
    assert adapter.full_reads == 2  # one exit snapshot, no mutation replay
    assert 'after_metadata_digest' in result


def test_explicit_planned_owned_payload_does_not_waive_source_invariants():
    adapter = Adapter('planned_change')
    expected = deepcopy(adapter.metadata['owned_rows'])
    expected[0]['section'] = 3
    assert run(adapter, expected_owned_rows=expected)['status'] == 'batch_verified_in_adapter'
    assert run(Adapter('planned_change'))['status'] == 'failed'


@pytest.mark.parametrize('limits', [{'max_steps': 1}, {'max_rows': 10}, {'max_cells': 1}])
def test_bounds_fail_without_starting_any_mutation(limits):
    adapter = Adapter()
    result = run(adapter, limits=limits)
    assert result['status'] == 'failed' and not adapter.operations
    assert not result['mutation_possible']


def test_cooperative_deadline_does_not_kill_or_repeat_a_callback(monkeypatch):
    clock = [0.]
    monkeypatch.setattr(metadata_batch.time, 'monotonic', lambda: clock[0])
    adapter = Adapter()
    original = adapter.execute_step
    def execute(name):
        original(name)
        clock[0] = 2.
    adapter.execute_step = execute
    result = run(adapter, limits={'max_seconds': 1.})
    assert result['status'] == 'failed' and len(adapter.operations) == 1
    assert adapter.full_reads == 2


@pytest.mark.parametrize('hashes', [{'/fixture/unrelated.m3d': 'a'*64},
    {'/fixture/source.m3d': 'a'*64, '/fixture/owned.cdw': 'b'*64}])
def test_hash_scope_must_pin_actual_source_and_exclude_owned_target(hashes):
    adapter = Adapter()
    result = run_metadata_batch(adapter, GUARD, hashes,
                                [{'name': 'one', 'expected_view_state': STATE}])
    assert result['status'] == 'failed' and not result['mutation_possible']
    assert adapter.guard_reads == adapter.full_reads == 0
