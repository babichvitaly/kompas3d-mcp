"""Stateful synthetic CDW/SPW save propagation, not engineering fixtures."""

import hashlib
import json
from copy import deepcopy

import pytest

from kompas_mcp.publication_finalization import assess_finalized_publication, finalization_order


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def plan():
    return {'common_specification': 'spec-common', 'original_hashes': {'original-model': 'a'*64},
            'specifications': [{'key': 'spec-common',
                'library': {'path': '/synthetic/installed/style.lyt', 'sha256': 'b'*64},
                'descriptor_style': 1, 'first_page_style': 17, 'continuation_style': 18,
                'word_wrap': True, 'rows_digest': 'c'*64}],
            'drawings': [{'key': f'drawing-{i}', 'family': 'fixture', 'logical': i,
                          'family_total': 2, 'mapped_stamp': {'7': str(i), '8': '2', 'name': 'fixture'},
                          'library': {'path': '/synthetic/private/style.lyt', 'sha256': 'b'*64},
                          'preserved_semantics_digest': 'd'*64} for i in [1, 2]]}


class Drawing:
    def __init__(self, p):
        self.plan = p
        self.serial = 0
        self.live = {'sheet_auto_number': True, 'sheet_auto_count': True,
                     'sheet_first_number': 1, 'sheets_count': 1, 'physical_sheets': 1,
                     'stamp': {'7': '1', '8': '1', 'name': 'fixture'}, 'library': p['library'],
                     'preserved_semantics_digest': p['preserved_semantics_digest']}
        self.saved = deepcopy(self.live)

    def propagate_spec_save(self):
        self.serial += 1  # byte rewrite even with no drawing row/property setters

    def serialize(self, disable_auto):
        self.live.update(sheet_auto_number=not disable_auto, sheet_auto_count=not disable_auto,
                         sheet_first_number=self.plan['logical'], sheets_count=self.plan['family_total'])
        self.live['stamp'] = deepcopy(self.plan['mapped_stamp'])  # live getters can look correct
        self.saved = deepcopy(self.live)  # models Stamp.Update followed by Save
        self.serial += 1

    def reopen(self):
        state = deepcopy(self.saved)
        if state['sheet_auto_number']:
            state['stamp']['7'] = '1'  # physical one-page CDW auto-number resets logical page
        return state

    def sha(self):
        return digest([self.saved, self.serial])


class Specification:
    def __init__(self, p, drawings):
        self.plan = p
        self.drawings = drawings
        self.pre_save_pages = 2
        self.saved_pages = 2
        self.text8 = '2'
        self.serial = 0

    def save(self):
        self.saved_pages = 3 if self.plan['word_wrap'] else self.pre_save_pages
        self.serial += 1
        for d in self.drawings:
            d.propagate_spec_save()

    def saved_state(self):
        p = self.plan
        return {'saved_api5_pages': self.saved_pages, 'layout_sheets': self.saved_pages,
                'physical_sheet_numbers': list(range(1, self.saved_pages+1)),
                'page_styles': [p['first_page_style']] + [p['continuation_style']]*(self.saved_pages-1),
                'descriptor_style': p['descriptor_style'], 'text8': self.text8, 'raw_shared_text7': '1',
                'library': deepcopy(p['library']), 'configured_library_path': p['library']['path'],
                'word_wrap': p['word_wrap'], 'rows_digest': p['rows_digest']}

    def sha(self):
        return digest([self.saved_state(), self.serial])


def simulate(disable_auto=True, correct_header=True, late_spw_save=False):
    p = plan()
    drawings = {d['key']: Drawing(d) for d in p['drawings']}
    spec = Specification(p['specifications'][0], list(drawings.values()))
    operations = finalization_order(p)
    e = {'operations': operations, 'saved_spw_probes': {}, 'sealed_hashes': {}, 'cycles': []}
    def hashes():
        return {'spec-common': spec.sha(), **{key: d.sha() for key, d in drawings.items()}}
    for op in operations:
        phase = op['phase']
        if phase == 'finalize_common_format_and_save':
            spec.save()
        elif phase == 'finalize_spw_and_save':
            spec.save()
            if correct_header:
                spec.text8 = str(spec.saved_pages)  # header based on saved, not cached pagination
                spec.save()  # header-only save still propagates attached CDW bytes
        elif phase == 'verify_saved_spw_pagination_header_library':
            e['saved_spw_probes'][op['key']] = spec.saved_state()
        elif phase == 'serialize_final_cdw_and_save':
            drawings[op['key']].serialize(disable_auto)
        elif phase == 'seal_all_owned_files':
            e['sealed_hashes'] = hashes()
        elif phase == 'full_saved_ro_gate':
            if late_spw_save and op['cycle'] == 1:
                spec.text8 = str(spec.saved_pages)
                spec.save()
            e['cycles'].append({'open_id': str(op['cycle']), 'read_only': True, 'hashes': hashes(),
                'original_hashes': deepcopy(p['original_hashes']),
                'specifications': {'spec-common': spec.saved_state()},
                'drawings': {key: d.reopen() for key, d in drawings.items()}})
        elif phase == 'verify_final_hashes':
            e['final_hashes'] = hashes()
    return p, e


def test_correct_order_survives_repagination_shared_text7_and_spec_writeback():
    p, e = simulate()
    assert e['saved_spw_probes']['spec-common']['saved_api5_pages'] == 3
    assert e['saved_spw_probes']['spec-common']['text8'] == '3'
    assert e['saved_spw_probes']['spec-common']['raw_shared_text7'] == '1'
    assert e['saved_spw_probes']['spec-common']['physical_sheet_numbers'] == [1, 2, 3]
    result = assess_finalized_publication(p, e)
    assert result['status'] == 'consistent_offline_evidence'
    assert result['native_acceptance'] == 'pending' and not result['package_portability_verified']


def test_fresh_auto_number_true_resets_manual_live_text7_on_saved_reopen():
    p, e = simulate(disable_auto=False)
    assert e['cycles'][0]['drawings']['drawing-2']['stamp']['7'] == '1'
    assert assess_finalized_publication(p, e)['status'] == 'rejected'


def test_cached_two_pages_cannot_validate_saved_three_pages_and_header_two():
    p, e = simulate(correct_header=False)
    assert e['saved_spw_probes']['spec-common']['saved_api5_pages'] == 3
    assert e['saved_spw_probes']['spec-common']['text8'] == '2'
    assert assess_finalized_publication(p, e)['status'] == 'rejected'


def test_header_only_spw_save_rewrites_attached_drawing_without_row_setters():
    p = plan()
    d = Drawing(p['drawings'][0])
    s = Specification(p['specifications'][0], [d])
    before_sha, before_semantics = d.sha(), deepcopy(d.saved)
    s.text8 = '3'
    s.save()
    assert d.sha() != before_sha and d.saved == before_semantics


def test_late_spw_header_save_cannot_be_hidden_by_unchanged_drawing_semantics():
    p, e = simulate(late_spw_save=True)
    assert e['cycles'][0]['drawings']['drawing-2']['stamp']['7'] == '2'
    assert e['sealed_hashes']['drawing-2'] != e['final_hashes']['drawing-2']
    assert assess_finalized_publication(p, e)['status'] == 'rejected'


@pytest.mark.parametrize('path,value', [
    (('saved_spw_probes', 'spec-common', 'physical_sheet_numbers'), [1, 1, 1]),
    (('saved_spw_probes', 'spec-common', 'descriptor_style'), 17),
    (('saved_spw_probes', 'spec-common', 'page_styles'), [1, 1, 1]),
    (('saved_spw_probes', 'spec-common', 'library', 'path'), '/synthetic/private/style.lyt'),
    (('saved_spw_probes', 'spec-common', 'configured_library_path'), '/synthetic/private/style.lyt'),
    (('cycles', 0, 'drawings', 'drawing-2', 'sheets_count'), 1),
    (('cycles', 1, 'drawings', 'drawing-1', 'preserved_semantics_digest'), 'e'*64),
    (('cycles', 1, 'original_hashes', 'original-model'), 'e'*64),
    (('cycles', 0, 'read_only'), False), (('cycles', 1, 'open_id'), '1'),
])
def test_saved_strict_semantics_library_path_and_hash_gates_remain(path, value):
    p, e = simulate()
    target = e
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert assess_finalized_publication(p, e)['status'] == 'rejected'


def test_spw_write_after_cdw_seal_is_rejected_even_with_fabricated_matching_hashes():
    p, e = simulate()
    e['operations'].append({'phase': 'finalize_spw_and_save', 'key': 'spec-common'})
    assert assess_finalized_publication(p, e)['status'] == 'rejected'


@pytest.mark.parametrize('field,value', [('logical', 1), ('family_total', 3)])
def test_incomplete_or_duplicate_logical_family_plan_fails_before_operations(field, value):
    p = plan()
    p['drawings'][1][field] = value
    with pytest.raises(ValueError):
        finalization_order(p)


def test_operation_settings_require_boolean_false_not_numeric_zero():
    p, e = simulate()
    operation = next(op for op in e['operations'] if op['phase'] == 'serialize_final_cdw_and_save')
    operation['settings']['SheetAutoNumber'] = 0
    assert assess_finalized_publication(p, e)['status'] == 'rejected'
