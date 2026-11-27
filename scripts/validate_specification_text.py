"""Opt-in synthetic API5 existing-row text acceptance, one exclusive STA worker.

Uses only a new synthetic root; no engineering inputs or source replacement.
Receipts, transport config and native artifacts remain private. Failed mutations
are not repeated, auto-ended, saved or automatically cleaned up.
"""

import argparse
import inspect
import json
import math
import runpy
import time
import traceback
from copy import deepcopy
from pathlib import Path

from native_owned_session import NativeOwnedSession, file_tree, need, sha
from validate_specification_reference import (
    build_fixture,
    description,
    identify_rows,
    native_files,
    occurrence,
    property_values,
    snapshot,
    strict_bool,
)


def context(session, owner):
    doc, desc = session.doc(owner), description(session, owner)
    return {'owner': str(doc.PathName), 'reference': str(doc.Reference),
            'kind': int(doc.DocumentType), 'description_index': 0,
            'layout': str(desc.LayoutName), 'style': int(desc.StyleID),
            'source': str(desc.SpecificationDocumentName)}


def semantic_capture(session, owner, targets):
    """Check runtime singleton membership FIRST; then detach reopen-stable evidence."""
    raw = snapshot(session, owner)
    need(identify_rows(raw, list(targets.values())) == targets, 'Exact UUID/singleton membership drift')
    ignored = {'raw_class', 'raw_reference', 'part_reference', 'model_reference',
               'api_reference', 'roundtrip_reference'}

    def stable(part):
        refs = [part[k] for k in ['raw_reference', 'part_reference', 'model_reference',
                                 'api_reference', 'roundtrip_reference']]
        need(part['valid'] and len(set(refs)) == 1, 'Typed/native reference identity mismatch')
        return {k: deepcopy(v) for k, v in part.items() if k not in ignored}

    rows = {}
    for row in raw['rows']:
        need(row['uuid'] not in rows, 'Duplicate model-SP UUID')
        texts = {str(c['type']): c['text'] for c in row['columns']}
        need(len(texts) == len(row['columns']), 'Ambiguous duplicate column types')
        rows[row['uuid']] = {**{k: deepcopy(v) for k, v in row.items()
                               if k not in {'uuid', 'columns', 'geometry'}},
                             'columns': texts, 'geometry': [stable(p) for p in row['geometry']]}
    return {'context': context(session, owner), 'rows': rows,
            'top_tree': [stable(p) for p in raw['top_tree']],
            'main_tree': [stable(p) for p in raw['main_tree']],
            'delegate': raw['delegate'], 'edit_object_reference': raw['edit_object_reference'],
            'properties': {uid: property_values(session, owner, path) for uid, path in targets.items()}}


class TextAdapter:
    def __init__(self, session, owner, targets):
        self.session, self.owner, self.targets = session, owner, targets
        doc, api = session.doc(owner), session.k.api
        self.sp = api.ksSpecification(api.ksDocument3D(
            session.k.app.ksGetDocumentByReference(doc.Reference)).GetSpecification())
        self.param = api.ksSpcDescrParam(session.k.app.GetParamStruct(
            session.k.constants['ko_SpcDescrParam']))
        need(self.param.Init() is True, 'Native description param Init failed')

    def guard_owned_context(self, expected):
        self.session.guard()
        doc = self.session.doc(self.owner)
        need(not doc.ReadOnly and context(self.session, self.owner) == expected,
             'Exact owned writable owner/description drift')
        returned = list(self.sp.ksGetSpcDescription(expected['description_index'], self.param))
        need(len(returned) == 2 and type(returned[0]) is int and returned[0] == 1
             and returned[1] is True, 'API5 description did not return long1/stateTrue')
        need(str(self.param.layoutName) == expected['layout']
             and int(self.param.styleId) == expected['style']
             and str(self.param.spcName) == expected['source'], 'API5 description mismatch')

    def capture_state(self):
        return semantic_capture(self.session, self.owner, self.targets)

    def row_object(self, uuid):
        rows = description(self.session, self.owner).BaseObjects
        found = [row for i in range(rows.Count)
                 if str((row := rows.Item(i)).UniqueMetaObjectKey) == uuid]
        need(len(found) == 1, 'Existing exact UUID not unique')
        return found[0]

    def row_number(self, uuid):
        return float(self.row_object(uuid).UniqueNumber)

    def pointer_for_number(self, number):
        return self.sp.ksGetSpcObject(number)

    def number_for_pointer(self, pointer):
        return self.sp.ksGetSpcObjectNumber(pointer)

    def get_column_text(self, *args):
        return self.sp.ksGetSpcObjectColumnText(*args)

    def edit(self, pointer):
        return self.sp.ksSpcObjectEdit(pointer)

    def set_column_text(self, *args):
        return self.sp.ksSetSpcObjectColumnText(*args)

    def end(self):
        return self.sp.ksSpcObjectEnd()


def compare_reopened(expected, actual):
    # Native document references are process/runtime-local. Geometry was already
    # checked against the fresh occurrence before constructing this snapshot.
    previous, current = deepcopy(expected), deepcopy(actual)
    previous['context'].pop('reference')
    current['context'].pop('reference')
    need(previous == current, 'Saved UUID/observed full payload/Geometry/properties/poses drift')


def run(session, config, report, event):
    from kompas_mcp import documents

    author = runpy.run_path(config['text_helper'])['author_existing_row_text_owned']
    report['helper_sha256'] = sha(config['text_helper'])
    folder = session.root/'text'
    owner, control_source, paths = build_fixture(session, folder, event)
    # One additional independent row remains completely unedited.
    session.call(documents.insert_component, session.k, owner['document']['handle'],
                 str(control_source), linked=True)
    control = occurrence(session, owner, [1])
    control.CreateSpcObjects, control.RevealComposition, control.Fixed = True, False, True
    strict_bool(control.Update(), 'own synthetic control row setup')
    owner_path = Path(session.doc(owner).PathName)
    session.save(owner, owner_path)
    session.close(owner)
    owner = session.open(owner_path, read_only=True)
    baseline_raw = snapshot(session, owner)
    selected_paths = paths if config['target_case'] == 'duplicate' else [[1]]
    targets = identify_rows(baseline_raw, selected_paths)
    need(len(baseline_raw['rows']) == 3 and len(targets) == len(selected_paths),
         'Expected declared target rows plus untouched controls')
    report['baseline_ro'] = semantic_capture(session, owner, targets)
    session.close(owner)
    owner = session.open(owner_path)
    session.doc(owner).Active = True
    desc = description(session, owner)
    desc.Active = True
    adapter = TextAdapter(session, owner, targets)
    before = semantic_capture(session, owner, targets)
    compare_reopened(report['baseline_ro'], before)
    if config['target_case'] == 'duplicate':
        need(sorted(row['is_first'] for uid, row in before['rows'].items() if uid in targets)
             == [False, True], 'Fixture did not expose first/subsequent duplicate rows')
    else:
        need(all(before['rows'][uid]['is_first'] for uid in targets),
             'Unique target is not first in its own print group')
    report['target_case'] = config['target_case']
    report.update(before=before, target_uuids=targets, baseline_files=native_files(folder),
                  installed_signatures={name: str(inspect.signature(getattr(
                      session.k.api.ksSpecification, name))) for name in [
                          'ksGetSpcDescription', 'ksGetSpcObject', 'ksGetSpcObjectNumber',
                          'ksGetSpcObjectColumnText', 'ksSpcObjectEdit',
                          'ksSetSpcObjectColumnText', 'ksSpcObjectEnd']})
    event('baseline_RO_and_exact_context_ready')
    report['all_files_before_edit'] = file_tree([folder])
    expected = deepcopy(before)
    for uuid in targets:
        changes = [{'column': c, 'execution': 1, 'block': 0,
                    'before': expected['rows'][uuid]['columns'][str(c)], 'after': text}
                   for c, text in [(4, 'SYNTH-TEXT-EDIT'), (5, 'Synthetic explicit edited text')]]
        report.setdefault('edits', []).append(author(
            {'row_uuid': uuid, 'expected_context': before['context'], 'cells': changes}, adapter))
        event('existing_row_edit_observed', status=report['edits'][-1]['status'])
        need(report['edits'][-1]['status'] == 'text_verified_in_adapter',
             'API5 text helper rejected native RAM; reconcile, do not save/replay')
        for cell in changes:
            expected['rows'][uuid]['columns'][str(cell['column'])] = cell['after']
    report['after'] = semantic_capture(session, owner, targets)
    need(report['after'] == expected, 'Cumulative text plan mismatch')
    need(native_files(folder) == report['baseline_files'], 'Unexpected disk write before Save')
    report['saved'] = session.save(owner, owner_path)
    report['saved_files'] = native_files(folder)
    report['all_files_after_save'] = file_tree([folder])
    changed = [p for p, h in report['baseline_files'].items() if report['saved_files'].get(p) != h]
    report['changed_files'] = changed
    need(set(report['saved_files']) == set(report['baseline_files']) and changed == [str(owner_path)],
         'Unexpected dependency writeback; keep receipt, do not hide side effects')
    session.close(owner)
    for cycle in range(2):
        owner = session.open(owner_path, read_only=True)
        state = semantic_capture(session, owner, targets)
        report.setdefault('saved_ro', []).append(state)
        compare_reopened(expected, state)
        volume = session.call(session.k.measure, owner['document_id'])['volume_mm3']
        need(math.isclose(volume, 2640., abs_tol=1e-5), 'Saved synthetic geometry volume drift')
        report.setdefault('saved_ro_volumes', []).append(volume)
        if cycle == 0:
            preview = Path(config['receipts'])/'synthetic-saved-preview.png'
            report['preview'] = session.call(session.k.preview, owner['document_id'], str(preview))
        session.close(owner)
        need(native_files(folder) == report['saved_files'], 'Read-only cycle changed disk files')
        event('independent_saved_RO_verified', cycle=cycle+1)
    report.update(acceptance='synthetic_API5_existing_row_text_two_RO',
                  production_stale_text_reproduced=False, properties_resync_proven=False)


def main(run_case=run):
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
    need(config.get('target_case') in {'duplicate', 'unique'}, 'Explicit synthetic target case required')
    output = Path(config['receipts'])/'text.json'
    need(not output.exists(), 'Existing receipt; reconcile, do not replay')
    report = {'phase': 'starting', 'events': [], 'saved': False, 'runner_sha256': sha(__file__)}
    started, session = time.monotonic(), None

    def flush():
        report['elapsed_seconds'] = time.monotonic()-started
        temporary = output.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(output)

    def event(stage, **data):
        report['events'].append({'stage': stage, **data})
        flush()
        print(stage, flush=True)

    flush()
    try:
        session = NativeOwnedSession(config)
        report.update(application=session.identity, baseline=list(session.baseline.values()))
        need(not session.root.exists(), 'New GUID/root required')
        session.root.mkdir()
        event('fresh_session_ready')
        run_case(session, config, report, event)
        report['phase'] = 'complete'
    except Exception:  # noqa: BLE001 - retain partial evidence, never replay mutation
        report.update(phase='failed', error=traceback.format_exc())
    finally:
        if session is not None:
            report['owned_remaining'] = [{'reference': ref, **{
                k: v for k, v in item.items() if k != 'result'}} for ref, item in session.owned.items()]
            try:
                report['final_guard'] = session.guard()
                report['preservation'] = session.verify_files()
            except Exception:  # noqa: BLE001 - ownership uncertainty prohibits automatic cleanup
                report['preservation_error'] = traceback.format_exc()
            session.release()
        flush()
        terminal = Path(config['receipts'])/'text-terminal.json'
        need(not terminal.exists(), 'Existing terminal receipt')
        terminal.write_text(json.dumps({'phase': report['phase'], 'report': str(output),
            'verification': {'artifacts': 'not_verified', 'physical_acceptance': 'pending'}},
            indent=2), encoding='utf-8')
    return int(report['phase'] == 'failed')


if __name__ == '__main__':
    raise SystemExit(main())
