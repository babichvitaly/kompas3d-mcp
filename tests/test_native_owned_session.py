"""Offline ownership failure paths for the experimental native acceptance harness."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1]/'scripts'/'native_owned_session.py'
spec = importlib.util.spec_from_file_location('sdk_native_session_for_tests', SCRIPT)
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


class Doc:
    def __init__(self, reference, path, read_only, visible):
        self.Reference, self.PathName = reference, str(path)
        self.DocumentType, self.ReadOnly = 1, read_only
        self.Changed, self.Visible = False, visible
        self.saves, self.save_return = 0, None

    def SaveAs(self, path):
        self.saves += 1
        Path(path).write_bytes(b'synthetic native document')
        self.PathName, self.Changed = str(path), False
        return self.save_return


def fixture(tmp_path, monkeypatch):
    root = tmp_path/'run'
    root.mkdir()
    foreign = tmp_path/'protected.cdw'
    foreign.write_bytes(b'immutable original')
    protected, own = Doc('foreign', foreign, True, True), Doc('own', root/'own.cdw', False, False)
    docs = [protected, own]
    identity = {'pid': 1, 'hwnd': 2, 'process_creation_time_100ns': 3}

    def inventory(app):
        return docs, [{'reference': d.Reference, 'path': d.PathName, 'kind': d.DocumentType,
                       'read_only': d.ReadOnly, 'changed': d.Changed, 'visible': d.Visible}
                      for d in docs]

    monkeypatch.setattr(native, 'inventory', inventory)
    monkeypatch.setattr(native, 'process_identity', lambda app: identity)
    session = object.__new__(native.NativeOwnedSession)
    session.app, session.root, session.identity = object(), root, dict(identity)
    session.baseline = {'foreign': inventory(None)[1][0]}
    result = {'document': {'handle': 'own-token'}}
    session.owned = {'own': {'path': own.PathName, 'kind': 1, 'read_only': False, 'result': result}}
    session.k = SimpleNamespace(handles={'own-token': own, 'foreign-token': protected})
    closed = []

    def close(k, handle, discard_changes):
        closed.append((handle, discard_changes))
        docs.remove(k.handles[handle])

    session.documents = SimpleNamespace(close_document=close)
    return session, result, protected, own, docs, identity, closed


@pytest.mark.parametrize('attribute,value', [
    ('PathName', '/another/protected.cdw'), ('DocumentType', 5), ('ReadOnly', False),
    ('Changed', True), ('Visible', False), ('Reference', 'new-reference'),
])
def test_any_preexisting_document_drift_blocks_further_native_action(tmp_path, monkeypatch,
                                                                  attribute, value):
    session, _, protected, _, _, _, _ = fixture(tmp_path, monkeypatch)
    setattr(protected, attribute, value)
    with pytest.raises(RuntimeError, match='protected document changed'):
        session.guard()


def test_extra_or_missing_documents_and_process_replacement_are_not_adopted(tmp_path, monkeypatch):
    session, _, protected, _, docs, identity, _ = fixture(tmp_path, monkeypatch)
    docs.append(Doc('unexpected', tmp_path/'unexpected.cdw', True, True))
    with pytest.raises(RuntimeError, match='Unexpected native documents'):
        session.guard()
    docs.pop()
    docs.remove(protected)
    with pytest.raises(RuntimeError, match='protected document changed'):
        session.guard()
    docs.insert(0, protected)
    identity['process_creation_time_100ns'] += 1
    with pytest.raises(RuntimeError, match='process identity changed'):
        session.guard()


def test_owned_mutation_is_allowed_but_owned_path_or_ro_drift_is_not(tmp_path, monkeypatch):
    session, _, _, own, _, _, _ = fixture(tmp_path, monkeypatch)
    own.Changed = True
    session.guard()
    own.ReadOnly = True
    with pytest.raises(RuntimeError, match='Owned document identity drift'):
        session.guard()


def test_foreign_handles_cannot_be_saved_closed_or_adopted(tmp_path, monkeypatch):
    session, _, protected, _, _, _, closed = fixture(tmp_path, monkeypatch)
    foreign = {'document': {'handle': 'foreign-token'}}
    for action in [lambda: session.save(foreign, session.root/'foreign.cdw'),
                   lambda: session.close(foreign), lambda: session.track(foreign)]:
        with pytest.raises(RuntimeError):
            action()
    assert protected.saves == 0 and closed == []
    assert Path(protected.PathName).read_bytes() == b'immutable original'


def test_output_root_itself_parent_and_symlink_escape_are_rejected(tmp_path, monkeypatch):
    session, _, _, _, _, _, _ = fixture(tmp_path, monkeypatch)
    outside = tmp_path/'outside'
    outside.mkdir()
    (session.root/'link').symlink_to(outside, target_is_directory=True)
    for path in [session.root, tmp_path/'escaped.cdw', session.root/'link'/'escaped.cdw']:
        with pytest.raises(RuntimeError, match='outside isolated synthetic root'):
            session.inside(path)
    assert session.inside(session.root/'nested'/'valid.cdw') == session.root/'nested'/'valid.cdw'


def test_void_save_requires_owned_file_path_and_clean_native_readback(tmp_path, monkeypatch):
    session, result, protected, own, _, _, _ = fixture(tmp_path, monkeypatch)
    target = session.root/'saved.cdw'
    receipt = session.save(result, target)
    assert receipt['SaveAs_return'] is None and receipt['sha256'] == native.sha(target)
    assert own.saves == 1 and not own.Changed
    assert Path(protected.PathName).read_bytes() == b'immutable original'


def test_existing_other_file_inside_owned_root_cannot_be_overwritten(tmp_path, monkeypatch):
    session, result, _, own, _, _, _ = fixture(tmp_path, monkeypatch)
    other = session.root/'another-artifact.cdw'
    other.write_bytes(b'previous useful work')
    with pytest.raises(RuntimeError, match='different existing file'):
        session.save(result, other)
    assert own.saves == 0 and other.read_bytes() == b'previous useful work'


def test_unexpected_boolean_save_result_is_partial_failure_never_automatic_retry(tmp_path, monkeypatch):
    session, result, _, own, _, _, closed = fixture(tmp_path, monkeypatch)
    own.save_return = True
    with pytest.raises(RuntimeError, match='Unexpected Automation SaveAs contract'):
        session.save(result, session.root/'partial.cdw')
    assert own.saves == 1 and closed == []
    assert (session.root/'partial.cdw').is_file()  # call may already have written the artifact


def test_closure_discards_only_the_explicitly_owned_document(tmp_path, monkeypatch):
    session, result, protected, own, _, _, closed = fixture(tmp_path, monkeypatch)
    own.Changed = True
    session.close(result)
    assert closed == [('own-token', True)] and session.owned == {}
    session.guard()
    assert Path(protected.PathName).read_bytes() == b'immutable original'


def test_protected_file_inventory_detects_content_and_membership_changes(tmp_path):
    root = tmp_path/'sources'
    root.mkdir()
    (root/'source.m3d').write_bytes(b'initial')
    initial = native.file_tree([root])
    (root/'source.m3d').write_bytes(b'changed')
    assert native.file_tree([root]) != initial
    (root/'source.m3d').write_bytes(b'initial')
    (root/'extra.cdw').write_bytes(b'new')
    assert native.file_tree([root]) != initial


@pytest.mark.parametrize('relation', ['same', 'inside', 'ancestor'])
def test_new_output_tree_cannot_overlap_protected_or_installed_trees(tmp_path, relation):
    protected = tmp_path/'protected'
    root = protected if relation == 'same' else protected/'new-run' if relation == 'inside' else tmp_path
    with pytest.raises(RuntimeError, match='must be disjoint'):
        native.require_disjoint_root(root, [protected])
    native.require_disjoint_root(tmp_path/'separate-new-run', [protected])


def test_dirty_foreign_document_can_only_be_pinned_with_exact_fresh_identity(tmp_path, monkeypatch):
    session, _, protected, _, _, identity, _ = fixture(tmp_path, monkeypatch)
    protected.ReadOnly, protected.Changed = False, True
    rows = native.inventory(None)[1][:1]
    with pytest.raises(RuntimeError, match='clean saved RO'):
        native.validate_protected_handover({}, identity, rows, rows)
    config = {'protected_document_policy': 'preserve_exact_state',
              'expected_application': dict(identity)}
    native.validate_protected_handover(config, identity, rows, rows)
    with pytest.raises(RuntimeError, match='fresh process identity'):
        native.validate_protected_handover({**config, 'expected_application': {}}, identity, rows, rows)
    with pytest.raises(RuntimeError, match='differ from fresh handover'):
        native.validate_protected_handover(config, identity, rows, [{**rows[0], 'reference': 'stale'}])
    session.baseline = {rows[0]['reference']: dict(rows[0])}
    session.guard()
    protected.Changed = False  # even saving the foreign dirty document violates protection
    with pytest.raises(RuntimeError, match='protected document changed'):
        session.guard()
