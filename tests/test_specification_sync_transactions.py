"""Offline contracts for explicit native sync-flag experiments, not CAD acceptance."""

import importlib
from pathlib import Path

import pytest


class Adapter:
    def __init__(self, mode):
        self.session, self.owner, self.sp = None, None, self
        self.mode, self.sync, self.calls = mode, True, []

    def guard_owned_context(self, context):
        assert context == {'synthetic': True}

    def row_number(self, uuid):
        return 123456789123.5

    def pointer_for_number(self, number):
        return 42

    def number_for_pointer(self, pointer):
        return 123456789123.5

    def ksGetSpcPropertyFill(self, pointer):
        return self.sync

    def ksSetSpcPropertyFill(self, pointer, value):
        self.calls.append('set')
        if self.mode == 'set_false':
            return False
        if self.mode != 'ignored':
            self.sync = bool(value)
        return True

    def edit(self, pointer):
        self.calls.append('edit')
        return 1

    def end(self):
        self.calls.append('end')
        return False if self.mode == 'bad_end' else 42

    def row_object(self, uuid):
        return self

    @property
    def SyncronizeWithProperties(self):
        return self.sync


@pytest.fixture
def experiment(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]/'scripts'))
    module = importlib.import_module('validate_specification_stale_text')
    monkeypatch.setattr(module, 'context', lambda *_: {'synthetic': True})
    return module


@pytest.mark.parametrize('route', ['direct', 'edit_set_end'])
def test_true_set_return_without_native_effect_is_rejected(experiment, route):
    adapter, report = Adapter('ignored'), {}
    with pytest.raises(RuntimeError, match='Sync readback mismatch'):
        experiment.set_sync(adapter, ['synthetic-row'], False, report, lambda *_: None, 'test', route)
    assert report['test'][0]['Set_return'] is True
    assert report['test'][0]['after'] is True
    assert adapter.calls.count('set') == 1


def test_false_set_does_not_auto_end_or_retry(experiment):
    adapter, report = Adapter('set_false'), {}
    with pytest.raises(RuntimeError, match='returned False'):
        experiment.set_sync(adapter, ['synthetic-row'], False, report, lambda *_: None,
                            'test', 'edit_set_end')
    assert adapter.calls == ['edit', 'set']
    assert report['test'][0]['edit_may_be_open']


def test_end_boolean_is_not_a_native_pointer(experiment):
    adapter, report = Adapter('bad_end'), {}
    with pytest.raises(RuntimeError, match='positive native pointer'):
        experiment.set_sync(adapter, ['synthetic-row'], False, report, lambda *_: None,
                            'test', 'edit_set_end')
    assert report['test'][0]['edit_may_be_open']


def test_flag_readback_and_numeric_end_both_required(experiment):
    adapter, report = Adapter('applied'), {}
    experiment.set_sync(adapter, ['synthetic-row'], False, report, lambda *_: None,
                        'test', 'edit_set_end')
    assert report['test'][0]['after'] is report['test'][0]['API7_after'] is False
    assert not report['test'][0]['edit_may_be_open']
