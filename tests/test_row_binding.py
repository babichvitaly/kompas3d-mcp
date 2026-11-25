"""Stateful synthetic adapter: mutation invalidates cached occurrence wrappers."""

from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from kompas_mcp.row_binding import bind_row_geometry_owned

KEY = {'path': [2, 1], 'source': '/synthetic/part.m3d', 'source_sha256': 'a'*64,
       'matrix': [1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.]}


class SyntheticAdapter:
    def __init__(self, mode=None):
        self.mode = mode
        self.generation = 0
        self.calls = []
        self.cached = NS(generation=0, reference='cached-other-occurrence')
        self.row = NS(uuid='row-synthetic')
        self.included = None

    def guard_owned_document(self):
        if self.mode == 'unowned' or (self.mode == 'lost_owner' and self.generation > 0):
            raise ValueError('Document ownership lost')

    def mutate_boundary(self, kind):
        self.calls.append('boundary')
        self.generation += 1
        return self.row

    def resolve_occurrence(self, key):
        self.calls.append('lookup')
        assert key.model_dump(mode='json') == KEY
        if self.mode in {'stale', 'stale_readable'}:
            return self.cached
        return NS(generation=self.generation, reference=f'fresh-{self.generation}')

    def occurrence_key(self, obj):
        value = deepcopy(KEY)
        if self.mode == 'wrong_source':
            value['source'] = '/synthetic/other.m3d'
        return value

    def occurrence_reference(self, obj):
        if obj.generation != self.generation and self.mode != 'stale_readable':
            raise ValueError('Stale interface reference getter')
        return obj.reference

    def row_uuid(self, row):
        return row.uuid

    def include_geometry(self, row, obj):
        self.calls.append('include')
        self.included = obj
        return True

    def update_row(self, row):
        self.calls.append('update')
        self.generation += 1
        if self.mode == 'native_error':
            raise RuntimeError('Synthetic native failure after mutation')
        if self.mode == 'wrong_uuid':
            row.uuid = 'different-row'
        return self.mode != 'false_update'

    def geometry_references(self, row):
        self.calls.append('geometry_read')
        if self.mode == 'wrong_binding':
            return ['another-occurrence']
        if self.mode == 'extra_binding':
            return [f'fresh-{self.generation}', 'extra']
        return [f'fresh-{self.generation}']


@pytest.mark.parametrize('boundary', ['row_add', 'description_add', 'tuning_update'])
@pytest.mark.parametrize('mode', [None, 'false_update'])
def test_executor_refetches_after_each_mutation_and_checks_exact_binding(boundary, mode):
    adapter = SyntheticAdapter(mode)
    result = bind_row_geometry_owned(KEY, boundary, adapter)
    assert result['status'] == 'binding_verified_in_adapter'
    assert result['reference_after_boundary'] == 'fresh-1'
    assert result['reference_after_update'] == 'fresh-2'
    assert adapter.calls == ['boundary', 'lookup', 'include', 'update', 'lookup', 'geometry_read']
    assert result['native_acceptance'] == 'pending' and not result['retry_allowed']


@pytest.mark.parametrize('mode', ['stale', 'stale_readable', 'wrong_source', 'wrong_binding', 'extra_binding',
                                 'wrong_uuid', 'native_error', 'lost_owner'])
def test_partial_failure_is_retained_without_retry_or_fallback(mode):
    adapter = SyntheticAdapter(mode)
    result = bind_row_geometry_owned(KEY, 'row_add', adapter)
    assert result['status'] == 'failed' and result['mutation_possible']
    assert result['failed_phase'] and not result['retry_allowed']
    assert adapter.calls.count('boundary') == 1
    assert adapter.calls.count('include') <= 1 and adapter.calls.count('update') <= 1


def test_owned_document_gate_precedes_boundary():
    adapter = SyntheticAdapter('unowned')
    result = bind_row_geometry_owned(KEY, 'row_add', adapter)
    assert result['status'] == 'failed' and not result['mutation_possible']
    assert adapter.calls == []


def test_incomplete_adapter_rejected_before_mutation():
    result = bind_row_geometry_owned(KEY, 'row_add', NS())
    assert result['status'] == 'failed' and result['failed_phase'] == 'preflight'
    assert not result['mutation_possible']


def test_extra_parent_membership_does_not_report_loss_of_the_target_reference():
    result = bind_row_geometry_owned(KEY, 'row_add', SyntheticAdapter('extra_binding'))
    assert result['status'] == 'failed'
    assert result['geometry_references'] == ['fresh-2', 'extra']
    diagnostic = result['geometry_mismatch']
    assert diagnostic['classification'] == 'extra_membership'
    assert diagnostic['expected_reference_present'] and diagnostic['actual_member_count'] == 2
    assert diagnostic['additional_references'] == ['extra']
    assert not diagnostic['semantic_link_loss_established']


def test_unobserved_runtime_reference_does_not_establish_semantic_link_loss():
    result = bind_row_geometry_owned(KEY, 'row_add', SyntheticAdapter('wrong_binding'))
    assert result['status'] == 'failed'
    diagnostic = result['geometry_mismatch']
    assert diagnostic['classification'] == 'expected_reference_not_observed'
    assert not diagnostic['expected_reference_present']
    assert not diagnostic['semantic_link_loss_established']
