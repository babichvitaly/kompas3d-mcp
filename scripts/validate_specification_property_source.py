"""Refresh an independently established saved synthetic stale-text fixture.

Private config pins the failed text-only receipt and its unchanged disk baseline.
The rejected RAM must already be discarded; no adoption or mutation replay occurs.
No whole-SP row edit, Geometry assignment or document rebuild is used here.
"""

import argparse
import json
import math
import runpy
import shutil
import time
import traceback
from pathlib import Path

from native_owned_session import NativeOwnedSession, need, sha
from validate_specification_reference import native_files, occurrence, property_values, strict_bool
from validate_specification_text import TextAdapter, context, semantic_capture


def run(session, config, report, event):
    import pythoncom
    from win32com.client import VARIANT

    receipt = Path(config['stale_input_receipt'])
    need(sha(receipt) == config['stale_input_sha256'], 'Stale fixture receipt changed')
    prior = json.loads(receipt.read_text(encoding='utf-8-sig'))
    need(prior['phase'] == 'failed' and prior['saved'] is False
         and len(prior['stale_saved_ro']) == 2
         and prior['text_refresh']['edit_may_be_open'] is False
         and not prior.get('preservation_error'), 'Require reconciled rejected text-only receipt')
    need(not session.owned, 'No adopted RAM in this independent property-source candidate')
    expected_files = prior['files_after_source_edit']
    for path in expected_files:
        session.inside(path)
    owner_path = session.inside(prior['before_refresh']['context']['owner'])
    folder = owner_path.parent
    need(native_files(folder) == expected_files, 'Saved stale baseline or source files changed')
    copy = Path(config['receipts'])/'stale-native-copy'
    need(not copy.exists(), 'Do not overwrite baseline artifact evidence')
    shutil.copytree(folder, copy)
    need({str(Path(p).relative_to(folder)): h for p, h in expected_files.items()} ==
         {str(Path(p).relative_to(copy)): h for p, h in native_files(copy).items()},
         'Stale baseline copy mismatch')
    oracle = runpy.run_path(config['refresh_oracle'])
    plan_stale, verify = oracle['current_property_text_plan'], oracle['verify_property_refresh']
    bindings, selected = prior['all_bindings'], prior['selected_uuids']
    need(len(selected) == 1, 'This candidate refreshes one unique row with duplicate controls')
    uuid = selected[0]
    source_path = session.inside(prior['before_refresh']['rows'][uuid]['geometry'][0]['source'])
    source = session.open(source_path, read_only=True)
    current_source = property_values(session, source, [])
    session.close(source)
    owner = session.open(owner_path)
    session.doc(owner).Active = True
    before = semantic_capture(session, owner, bindings)
    verify(prior['before_refresh'], before)
    for c in ['4', '5']:
        need(before['properties'][uuid][c] == {'value': current_source[c]['value'], 'from_source': True},
             'Owner property is not independently current and inherited')
    planned = plan_stale(before, selected, normalize_display_metadata=True)
    expected = planned['expected_after']
    report.update(stale_input_sha256=config['stale_input_sha256'], before_refresh=before,
                  actual_source_properties=current_source, refresh_oracle=planned,
                  native_files_before=expected_files, source_sha256=sha(source_path),
                  cache_normalization='Only selected Name/Marking display fields; IDs/source/poses frozen')
    event('stale_current_inherited_properties_before_property_write_proven')
    adapter = TextAdapter(session, owner, bindings)
    ctx = context(session, owner)
    keeper = session.cast(occurrence(session, owner, bindings[uuid]), 'IPropertyKeeper')
    manager = session.cast(session.app, 'IPropertyMng')
    cells = planned['plans'][0]['cells']
    need([c['column'] for c in cells] == [5], 'This accepted-case candidate selects stale name only')
    prop = manager.GetProperty(session.doc(owner), 5.)
    need(prop is not None and float(prop.Id) == 5., 'Wrong source property identity')

    def set_value(value, label):
        adapter.guard_owned_context(ctx)
        returned = keeper.SetPropertyValue(prop, value, False)  # third argument is BaseUnit
        record = {'operation': label, 'return': returned, 'BaseUnit': False}
        report.setdefault('property_calls', []).append(record)
        event(label+'_return_observed')
        strict_bool(returned, 'SetPropertyValue '+label)
        record['after'] = semantic_capture(session, owner, bindings)
        event(label+'_readback_observed')
        return record['after']

    after = set_value(VARIANT(pythoncom.VT_EMPTY, None), 'empty_on_inherited_property')
    # The tested path needs one reset on an already inherited property. Do not
    # ship the unexecuted local-value/second-reset alternative from the research harness.
    verify(expected, after)
    report['refresh_route'] = 'SetPropertyValue_VT_EMPTY_on_already_inherited_property'
    report['after_refresh'] = after
    verify(expected, after)
    need(native_files(folder) == expected_files, 'Unexpected native disk writes before result Save')
    report['saved'] = session.save(owner, owner_path)
    saved_files = native_files(folder)
    report['native_files_after'] = saved_files
    report['writeback_files'] = [p for p, h in expected_files.items() if saved_files.get(p) != h]
    need(saved_files.keys() == expected_files.keys() and report['writeback_files'] == [str(owner_path)],
         'Unexpected result dependency writeback')
    session.close(owner)
    for cycle in range(2):
        owner = session.open(owner_path, read_only=True)
        state = semantic_capture(session, owner, bindings)
        report.setdefault('saved_ro', []).append(state)
        verify(expected, state)
        volume = session.call(session.k.measure, owner['document_id'])['volume_mm3']
        need(math.isclose(volume, 2640., abs_tol=1e-5), 'Saved geometry volume mismatch')
        report.setdefault('saved_ro_volumes', []).append(volume)
        session.close(owner)
        need(native_files(folder) == saved_files and sha(source_path) == report['source_sha256'],
             'Saved read-only cycle changed sources/files')
        event('property_source_refresh_saved_RO_verified', cycle=cycle+1)
    copy = Path(config['receipts'])/'refreshed-native-copy'
    need(not copy.exists(), 'Do not overwrite refreshed artifact evidence')
    shutil.copytree(folder, copy)
    need({str(Path(p).relative_to(folder)): h for p, h in saved_files.items()} ==
         {str(Path(p).relative_to(copy)): h for p, h in native_files(copy).items()}, 'Result copy mismatch')
    report.update(acceptance='stale_name_current_properties_source_refresh_two_RO',
                  stale_fixture_reproduced=True, full_observed_refresh_preservation=True,
                  geometry_or_row_creation_during_refresh=False, whole_row_Edit_End_calls=0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
    output = Path(config['receipts'])/'text.json'
    need(not output.exists(), 'Existing receipt; reconcile, do not replay')
    report = {'phase': 'starting', 'saved': False, 'events': [], 'runner_sha256': sha(__file__)}
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
        run(session, config, report, event)
        report['phase'] = 'complete'
    except Exception:  # noqa: BLE001 - keep partial RAM evidence; never silently retry or save
        report.update(phase='failed', error=traceback.format_exc())
    finally:
        if session is not None:
            report['owned_remaining'] = [{'reference': ref, **{
                k: v for k, v in entry.items() if k != 'result'}} for ref, entry in session.owned.items()]
            try:
                report['final_guard'] = session.guard()
                report['preservation'] = session.verify_files()
            except Exception:  # noqa: BLE001 - uncertain ownership forbids automatic cleanup
                report['preservation_error'] = traceback.format_exc()
            session.release()
        flush()
        terminal = Path(config['receipts'])/'text-terminal.json'
        need(not terminal.exists(), 'Existing terminal receipt')
        terminal.write_text(json.dumps({'phase': report['phase'], 'report': str(output)}, indent=2),
                            encoding='utf-8')
    return int(report['phase'] == 'failed')


if __name__ == '__main__':
    raise SystemExit(main())
