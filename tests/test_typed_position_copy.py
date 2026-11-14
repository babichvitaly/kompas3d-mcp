"""Stateful typed text copy; no COM, product model, numeric setter or field grammar."""

from copy import deepcopy

import pytest

from kompas_mcp.typed_position_copy import assess_saved_typed_copy, copy_position_field_owned


def snapshot():
    return {'properties': {'paragraph_style': 'fixture'}, 'lines': [
        {'properties': {'height': 3.5, 'alignment': 1}, 'items': [
            {'item_type': 0, 'properties': {'text': 'ref ', 'font': 'fixture'}, 'property_field': None},
            {'item_type': 8192, 'properties': {'cached_value': '7', 'font': 'fixture'},
             'property_field': {'key': 'canonical-row', 'prop': 'position', 'type': 'partPropertyByKey'}}]}]}


def plan():
    return {'target_path': '/fixture/working.cdw', 'canonical_row_uuid': 'canonical-row',
            'backup': {'path': '/fixture/owned-ro-backup.cdw', 'sha256': 'a'*64,
                       'owned': True, 'read_only': True, 'canonical_row_uuid': 'canonical-row'},
            'untouched_hashes': {'/fixture/owned-ro-backup.cdw': 'a'*64,
                                 '/fixture/other.cdw': 'b'*64, '/fixture/common.spw': 'c'*64,
                                 '/fixture/source.m3d': 'd'*64}}


class TypedText:
    def __init__(self, value, mode=None):
        self.value = deepcopy(value)
        self.mode = mode
        self.assign_calls = 0

    @property
    def Str(self):
        raise AssertionError('No Str roundtrip permitted by typed copy helper')

    @Str.setter
    def Str(self, value):
        raise AssertionError('No Str setter or numeric/serialized field grammar permitted')

    def Assign(self, other):
        self.assign_calls += 1
        if self.mode == 'assign_false':
            return False
        assert isinstance(other, TypedText)
        self.value = deepcopy(other.value)
        if self.mode == 'flatten':
            self.value['lines'][0]['items'][1] = {'item_type': 0,
                'properties': {'text': '7'}, 'property_field': None}
        if self.mode == 'format_change':
            self.value['lines'][0]['properties']['height'] = 4.
        return True


class Leader:
    def __init__(self, uuid, value, mode=None):
        self.uuid, self.Positions = uuid, TypedText(value, mode)
        self.mode, self.update_calls = mode, 0

    def Update(self):
        self.update_calls += 1
        if self.mode == 'update_error':
            raise RuntimeError('Synthetic native commit error')
        return self.mode != 'update_false'


class Adapter:
    def __init__(self, mode=None):
        self.mode = mode
        self.guards = 0
        self.hash_reads = 0

    def guard_copy_scope(self, p, target, backup):
        self.guards += 1
        if self.mode == 'unowned':
            raise ValueError('Target is not owned')

    def backup_identity(self, leader):
        value = deepcopy(plan()['backup'])
        if self.mode == 'wrong_backup':
            value['sha256'] = 'f'*64
        return value

    def untouched_hashes(self):
        self.hash_reads += 1
        value = deepcopy(plan()['untouched_hashes'])
        if self.mode == 'unrelated_write' and self.hash_reads == 2:
            value['/fixture/common.spw'] = 'f'*64
        return value

    def snapshot_text(self, text):
        return deepcopy(text.value)

    def leader_uuid(self, leader):
        return leader.uuid

    def lookup_native_row(self, leader):
        return {'leader_uuid': leader.uuid, 'matched_row_uuids': ['wrong-row']
                if self.mode == 'wrong_row' else ['canonical-row'], 'included_in_row': True}


def leaders(mode=None):
    return Leader('new-leader', snapshot(), mode), Leader('old-leader', snapshot())


def test_typed_assign_preserves_field_and_all_captured_structure_without_str():
    target, backup = leaders()
    result = copy_position_field_owned(plan(), target, backup, Adapter())
    assert result['status'] == 'typed_copy_verified_in_adapter'
    assert target.Positions.assign_calls == target.update_calls == 1
    assert target.Positions.value == backup.Positions.value == snapshot()
    assert result['native_acceptance'] == 'pending' and not result['saved']


@pytest.mark.parametrize('mode', ['assign_false', 'update_false', 'update_error', 'flatten', 'format_change'])
def test_uncertain_copy_or_structure_loss_has_no_flattening_fallback_or_retry(mode):
    target, backup = leaders(mode)
    result = copy_position_field_owned(plan(), target, backup, Adapter())
    assert result['status'] == 'failed' and result['mutation_possible']
    assert target.Positions.assign_calls == 1 and target.update_calls <= 1
    assert not result['retry_allowed']


@pytest.mark.parametrize('mode', ['unowned', 'wrong_backup', 'wrong_row'])
def test_backup_ownership_and_exact_canonical_row_are_preconditions(mode):
    target, backup = leaders()
    result = copy_position_field_owned(plan(), target, backup, Adapter(mode))
    assert result['status'] == 'failed' and not result['mutation_possible']
    assert target.Positions.assign_calls == target.update_calls == 0


def test_common_write_is_detected_even_when_typed_field_copy_succeeded():
    target, backup = leaders()
    result = copy_position_field_owned(plan(), target, backup, Adapter('unrelated_write'))
    assert result['status'] == 'failed' and result['mutation_possible']
    assert target.Positions.value == backup.Positions.value


def cycles():
    return [{'open_id': str(i), 'read_only': True, 'target_path': plan()['target_path'],
             'target_sha256': 'e'*64, 'typed_text': snapshot(),
             'binding': {'leader_uuid': 'new-leader', 'matched_row_uuids': ['canonical-row'],
                         'included_in_row': True}, 'untouched_hashes': plan()['untouched_hashes']}
            for i in range(2)]


def test_saved_ro_oracle_keeps_pdf_and_dynamic_renumbering_acceptance_separate():
    result = assess_saved_typed_copy(plan(), snapshot(), 'new-leader', 'e'*64, cycles())
    assert result['status'] == 'consistent_offline_evidence'
    assert result['native_acceptance'] == result['pdf_visual_acceptance'] == 'pending'
    assert not result['dynamic_renumbering_verified']


@pytest.mark.parametrize('path,value', [
    ((0, 'read_only'), False), ((1, 'open_id'), '0'), ((1, 'target_sha256'), 'f'*64),
    ((0, 'binding', 'matched_row_uuids'), ['canonical-row', 'other']),
    ((1, 'binding', 'included_in_row'), False),
    ((1, 'typed_text', 'lines', 0, 'items', 1, 'properties', 'cached_value'), '8'),
    ((0, 'typed_text', 'lines', 0, 'items', 1, 'property_field', 'key'), 'another-row'),
    ((1, 'untouched_hashes', '/fixture/source.m3d'), 'f'*64),
])
def test_saved_exact_field_structure_row_lookup_and_unrelated_hashes_are_mandatory(path, value):
    e = cycles()
    parent = e
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    assert assess_saved_typed_copy(plan(), snapshot(), 'new-leader', 'e'*64, e)['status'] == 'rejected'


@pytest.mark.parametrize('mode', ['literal', 'missing_metadata'])
def test_source_must_be_a_real_native_property_field_before_any_assignment(mode):
    target, backup = leaders()
    item = backup.Positions.value['lines'][0]['items'][1]
    if mode == 'literal':
        item.update(item_type=0, property_field=None, properties={'text': '7'})
    else:
        item['property_field'] = None
    result = copy_position_field_owned(plan(), target, backup, Adapter())
    assert result['status'] == 'failed' and not result['mutation_possible']
    assert target.Positions.assign_calls == target.update_calls == 0


@pytest.mark.parametrize('uuid,seal,observations', [
    ('new-leader', 'not-a-sha256', cycles()), ('', 'e'*64, cycles()),
    ('new-leader', 'e'*64, None),
])
def test_malformed_saved_evidence_is_rejected(uuid, seal, observations):
    assert assess_saved_typed_copy(plan(), snapshot(), uuid, seal, observations)['status'] == 'rejected'
