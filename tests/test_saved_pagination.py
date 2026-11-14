from copy import deepcopy

import pytest

from kompas_mcp.saved_pagination import stabilize_saved_pagination

PLAN = {'key': 'owned-spec', 'library': {'path': '/fixture/actual.lyt', 'sha256': 'a'*64},
        'descriptor_style': 1, 'first_page_style': 17, 'continuation_style': 18,
        'word_wrap': True, 'rows_digest': 'b'*64}
ORIGINALS = {'readonly-input': 'c'*64}
DEPS = {'owned-drawing': {'bytes_sha256': '0'*64, 'geometry_sha256': 'd'*64,
                        'fields_sha256': 'e'*64, 'frame_sha256': 'f'*64}}


class Adapter:
    def __init__(self, mode=None, header='2'):
        self.mode, self.header = mode, header
        self.saves, self.header_writes, self.confirm = 0, [], False
        self.unsaved_api7_pages = 2  # never queried by the protocol

    def guard_owned_scope(self, spec, deps, originals):
        assert spec == 'owned-spec' and deps == ('owned-drawing',) and originals == ('readonly-input',)
        if self.mode == 'readonly_loss' and self.saves:
            raise ValueError('Read-only source flag lost')

    def read_original_hashes(self):
        return {'readonly-input': 'a'*64} if self.mode == 'input_write' and self.saves else ORIGINALS.copy()

    def read_owned_dependents(self):
        value = deepcopy(DEPS)
        value['owned-drawing']['bytes_sha256'] = str(self.saves)*64
        if self.mode == 'semantic_change' and self.saves:
            value['owned-drawing']['fields_sha256'] = 'a'*64
        return value

    def save_close_open_specification(self):
        self.saves += 1
        if self.mode == 'save_exception':
            raise RuntimeError('Save may have completed; do not replay')

    def read_saved_specification(self):
        pages = 6 + (self.saves-1 if self.mode == 'oscillating' else 0)
        if self.mode == 'unstable_confirmation' and self.confirm:
            pages += 1
        return {'saved_api5_pages': pages, 'layout_sheets': pages,
                'physical_sheet_numbers': list(range(1, pages+1)), 'page_styles': [17]+[18]*(pages-1),
                'descriptor_style': 1, 'text8': self.header, 'raw_shared_text7': '1',
                'library': PLAN['library'], 'configured_library_path': PLAN['library']['path'],
                'word_wrap': True, 'rows_digest': PLAN['rows_digest']}

    def set_total_field(self, count):
        self.header_writes.append(count)
        self.header = str(count)

    def open_saved_readonly_confirmation(self):
        self.confirm = True


def run(adapter, **kwargs):
    return stabilize_saved_pagination(adapter, PLAN, ORIGINALS, DEPS, **kwargs)


def test_saved_six_pages_replaces_cached_two_and_allows_semantically_unchanged_owned_bytes():
    adapter = Adapter()
    result = run(adapter)
    assert result['status'] == 'saved_pagination_stable_in_adapter'
    assert adapter.saves == 2 and adapter.header_writes == [6]
    assert result['final_saved_pages'] == 6 and result['ready_for_finalization']
    assert result['owned_byte_changes'] == ['owned-drawing']
    assert result['dependent_hashes_after_writeback']['owned-drawing'] == '2'*64
    assert result['native_acceptance'] == 'pending'


def test_already_correct_saved_header_needs_no_extra_write_to_confirm():
    adapter = Adapter(header='6')
    result = run(adapter)
    assert result['ready_for_finalization'] and adapter.saves == 1 and not adapter.header_writes


@pytest.mark.parametrize('mode', ['readonly_loss', 'input_write', 'semantic_change',
                                 'save_exception', 'oscillating', 'unstable_confirmation'])
def test_no_immutable_or_semantic_waiver_and_no_unbounded_save_retry(mode):
    adapter = Adapter(mode)
    result = run(adapter)
    assert result['status'] == 'failed' and not result['ready_for_finalization']
    assert adapter.saves <= 3 and not result['retry_allowed']
    if mode == 'save_exception':
        assert adapter.saves == 1


def test_owned_dependent_cannot_also_be_declared_an_immutable_input():
    adapter = Adapter()
    result = stabilize_saved_pagination(adapter, PLAN,
        {**ORIGINALS, 'owned-drawing': '0'*64}, DEPS)
    assert result['status'] == 'failed' and not adapter.saves
