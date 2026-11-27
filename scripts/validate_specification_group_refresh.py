"""Opt-in designation and grouped-target VT_EMPTY source refresh experiments.

One exclusive STA worker, new synthetic root, no engineering inputs or installed
changes. Baseline/reopen/group summary and complete final preservation gates are
strict; transient selected-row regrouping is evidence, never final acceptance.
"""

import argparse
import inspect
import json
import math
import runpy
import shutil
import time
import traceback
from copy import deepcopy
from pathlib import Path

from native_owned_session import NativeOwnedSession, need, sha
from validate_specification_reference import (
    build_fixture,
    identify_rows,
    native_files,
    new_assembly,
    occurrence,
    property_values,
    snapshot,
    strict_bool,
    top,
)
from validate_specification_text import TextAdapter, context, semantic_capture


def group_summary(session, owner, bindings):
    """Read native aggregation at exact UUID/numeric mappings, including hidden rows."""
    adapter = TextAdapter(session, owner, bindings)
    state = semantic_capture(session, owner, bindings)
    result = {}
    for uuid, row in state['rows'].items():
        session.guard()
        number = adapter.row_number(uuid)
        pointer = adapter.pointer_for_number(number)
        need(type(pointer) is int and pointer > 0 and adapter.number_for_pointer(pointer) == number,
             'Summary native UUID/numeric mapping mismatch')
        value = adapter.sp.ksGetSpcObjectSummaryCount(pointer, 1, 0)
        need(type(value) in {int, float} and math.isfinite(value), 'Invalid native group quantity')
        result[uuid] = {'draw': row['draw'], 'is_first': row['is_first'],
                        'position': row['columns']['3'], 'raw_quantity': row['columns']['6'],
                        'summary': value, 'geometry_count': len(row['geometry'])}
        session.guard()
    return result


def copy_native(folder, target):
    need(not target.exists(), 'Do not overwrite native artifact evidence')
    shutil.copytree(folder, target)
    relative = lambda root: {str(Path(p).relative_to(root)): h for p, h in native_files(root).items()}
    need(relative(folder) == relative(target), 'Native evidence copy SHA mismatch')


def initialize_positions(session, owner, paths, unique_path, report, event, restore_inheritance=False):
    """Fixture authoring before source changes; never a repair during refresh."""
    bindings = identify_rows(snapshot(session, owner), paths+[unique_path])
    before = semantic_capture(session, owner, bindings)
    expected = deepcopy(before)
    adapter = TextAdapter(session, owner, bindings)
    ctx = context(session, owner)
    report['position_fixture_before'] = before
    for uuid, path in bindings.items():
        position = 20 if path == unique_path else 10
        adapter.guard_owned_context(ctx)
        number = adapter.row_number(uuid)
        pointer = adapter.pointer_for_number(number)
        need(type(pointer) is int and pointer > 0 and adapter.number_for_pointer(pointer) == number,
             'Initial position numeric mapping mismatch')
        record = {'uuid': uuid, 'position': position, 'edit_may_be_open': True,
                  'Edit_return': adapter.edit(pointer)}
        report.setdefault('position_fixture_calls', []).append(record)
        event('position_fixture_Edit_observed')
        need(type(record['Edit_return']) is int and record['Edit_return'] == 1, 'Position Edit failed')
        record['Position_return'] = adapter.sp.ksSpcPosition(position)
        event('position_fixture_Set_observed')
        need(type(record['Position_return']) is int and record['Position_return'] == 1,
             'ksSpcPosition did not return long1')
        record['End_pointer'] = adapter.end()
        event('position_fixture_End_observed')
        need(type(record['End_pointer']) is int and record['End_pointer'] > 0
             and adapter.number_for_pointer(record['End_pointer']) == number, 'Position End mismatch')
        record['edit_may_be_open'] = False
        expected['rows'][uuid]['columns']['3'] = str(position)
    after = semantic_capture(session, owner, bindings)
    report['position_fixture_after'] = after
    if restore_inheritance:
        import pythoncom
        from win32com.client import VARIANT

        # This is an explicitly selected fixture-authoring route, before the
        # source-change baseline. Never do this as repair during a refresh test.
        local_expected = deepcopy(expected)
        for uuid in bindings:
            for c in ['4', '5']:
                flag = after['properties'][uuid][c]['from_source']
                need(type(flag) is bool, 'Invalid source flag after fixture numbering')
                local_expected['properties'][uuid][c]['from_source'] = flag
        need(local_expected == after, 'Numbering changed fields beyond positions/source flags')
        manager = session.cast(session.app, 'IPropertyMng')
        for uuid, path in bindings.items():
            for pid in [4, 5]:
                adapter.guard_owned_context(ctx)
                keeper = session.cast(occurrence(session, owner, path), 'IPropertyKeeper')
                prop = manager.GetProperty(session.doc(owner), float(pid))
                need(prop is not None and float(prop.Id) == pid, 'Wrong fixture source property')
                returned = keeper.SetPropertyValue(prop, VARIANT(pythoncom.VT_EMPTY, None), False)
                report.setdefault('position_fixture_source_restore', []).append(
                    {'uuid': uuid, 'property_id': pid, 'return': returned})
                event('position_fixture_inheritance_restore_observed')
                strict_bool(returned, 'fixture inheritance restore')
        after = semantic_capture(session, owner, bindings)
        report['position_fixture_restored'] = after
    # Initial same-source group has the same position on both UUID rows; the
    # unique control has another nonblank position. Do not waive other changes.
    previous, current = deepcopy(expected), deepcopy(after)
    previous['context'].pop('reference')
    current['context'].pop('reference')
    need(previous == current, 'Initial numbering changed unexpected payload/properties/identity')


def run(session, config, report, event):
    import pythoncom
    from win32com.client import VARIANT

    from kompas_mcp import documents

    oracle = runpy.run_path(config['refresh_oracle'])
    plan_source = oracle['source_property_refresh_plan']
    verify = oracle['verify_property_refresh']
    progress = oracle['verify_source_refresh_progress']
    pid, selected_case = config['property_id'], config['target_case']
    need(type(pid) is int and pid in {4, 5} and selected_case in {'unique', 'group'},
         'Explicit tested property/selection required')
    need(config.get('reset_order', 'first_visible') in {'first_visible', 'hidden_first'},
         'Explicit selected-row batch order required')
    folder = session.root/'group_refresh'
    owner, source_b, paths = build_fixture(session, folder, event)
    layout = config.get('occurrence_layout', 'nested')
    need(layout in {'nested', 'direct'}, 'Explicit synthetic occurrence layout required')
    if layout == 'direct':
        session.close(owner)
        owner = new_assembly(session, folder, 'Synthetic direct owner', 'SYNTH-DIRECT-OWNER',
                             [folder/'SYNTH-SOURCE-A.a3d']*2+[source_b])
        paths, unique_path = [[0], [1]], [2]
    else:
        session.call(documents.insert_component, session.k, owner['document']['handle'],
                     str(source_b), linked=True)
        inserted = occurrence(session, owner, [1])
        inserted.CreateSpcObjects, inserted.RevealComposition, inserted.Fixed = True, False, True
        strict_bool(inserted.Update(), 'initial synthetic unique occurrence')
        unique_path = [1]
    owner_path = Path(session.doc(owner).PathName)
    if config.get('seed_positions') is True:
        initialize_positions(session, owner, paths, unique_path, report, event,
                             config.get('restore_seed_inheritance') is True)
    session.save(owner, owner_path)
    session.close(owner)
    owner = session.open(owner_path, read_only=True)
    raw = snapshot(session, owner)
    bindings = identify_rows(raw, paths+[unique_path])
    selected = list(identify_rows(raw, [unique_path] if selected_case == 'unique' else paths))
    initial = semantic_capture(session, owner, bindings)
    initial_summary = group_summary(session, owner, bindings)
    report.update(property_id=pid, selection=selected_case, occurrence_layout=layout, all_bindings=bindings,
                  selected_uuids=selected, initial=initial, initial_group_summary=initial_summary,
                  oracle_sha256=sha(config['refresh_oracle']))
    need(len(bindings) == 3 and len(selected) == (1 if selected_case == 'unique' else 2),
         'Unexpected three-row synthetic fixture')
    session.close(owner)
    source_path = Path(source_b) if selected_case == 'unique' else folder/'SYNTH-SOURCE-A.a3d'
    before_source_files = native_files(folder)
    source = session.open(source_path)
    root = top(session, source)
    if pid == 4:
        root.Marking = 'SYNTH-CURRENT-DESIGNATION'
    else:
        root.Name = 'Synthetic current grouped name'
    report['source_Update_return'] = root.Update()
    event('source_metadata_Update_observed')
    strict_bool(report['source_Update_return'], 'own source metadata Update')
    volume = session.call(session.k.measure, source['document_id'])['volume_mm3']
    need(math.isclose(volume, 1040. if selected_case == 'unique' else 800., abs_tol=1e-5),
         'Source geometry changed during metadata setup')
    report['source_save'] = session.save(source, source_path)
    session.close(source)
    source = session.open(source_path, read_only=True)
    current_source = property_values(session, source, [])
    report['actual_source_properties'] = current_source
    session.close(source)
    files = native_files(folder)
    changed = [p for p, h in before_source_files.items() if files.get(p) != h]
    need(files.keys() == before_source_files.keys() and changed == [str(source_path)],
         'Unexpected setup native write boundary')
    report['native_files_before_refresh'] = files
    report['setup_changed_files'] = changed
    owner = session.open(owner_path, read_only=True)
    before = semantic_capture(session, owner, bindings)
    source_values = {u: {c: v['value'] for c, v in current_source.items()} for u in selected}
    for uuid in selected:
        need(before['rows'][uuid]['geometry'][0]['source'] == str(source_path),
             'Target occurrence source mismatch')
    plan = plan_source(before, selected, source_values, [pid], allow_property_value_refresh=pid == 4)
    report.update(before_refresh=before, refresh_plan=plan,
                  owner_values_already_current=not plan['declared_property_cache_changes'],
                  baseline_group_summary=group_summary(session, owner, bindings))
    event('stale_selected_field_and_source_inheritance_verified')
    session.close(owner)
    for cycle in range(2):
        owner = session.open(owner_path, read_only=True)
        state = semantic_capture(session, owner, bindings)
        report.setdefault('baseline_saved_ro', []).append(state)
        verify(before, state)
        need(group_summary(session, owner, bindings) == report['baseline_group_summary'],
             'Baseline grouping is not stable through reopening')
        session.close(owner)
        need(native_files(folder) == files, 'Baseline RO wrote native files')
        event('baseline_saved_RO_verified', cycle=cycle+1)
    copy_native(folder, Path(config['receipts'])/'baseline-native-copy')
    owner = session.open(owner_path)
    session.doc(owner).Active = True
    verify(before, semantic_capture(session, owner, bindings))
    adapter = TextAdapter(session, owner, bindings)
    ctx = context(session, owner)
    manager = session.cast(session.app, 'IPropertyMng')
    report['SetPropertyValue_signature'] = str(inspect.signature(
        session.k.modules['kAPI7'].IPropertyKeeper.SetPropertyValue))
    selected.sort(key=lambda u: before['rows'][u]['is_first'],
                  reverse=config.get('reset_order', 'first_visible') == 'first_visible')
    report['reset_order'] = list(selected)
    for uuid in selected:
        adapter.guard_owned_context(ctx)
        keeper = session.cast(occurrence(session, owner, bindings[uuid]), 'IPropertyKeeper')
        prop = manager.GetProperty(session.doc(owner), float(pid))
        need(prop is not None and float(prop.Id) == pid, 'Wrong native property identity')
        returned = keeper.SetPropertyValue(prop, VARIANT(pythoncom.VT_EMPTY, None), False)
        record = {'row_uuid': uuid, 'property_id': pid, 'return': returned, 'BaseUnit': False}
        report.setdefault('property_calls', []).append(record)
        event('property_source_reset_return_observed')
        strict_bool(returned, 'SetPropertyValue VT_EMPTY')
        record['after'] = semantic_capture(session, owner, bindings)
        record['group_summary'] = group_summary(session, owner, bindings)
        event('property_source_reset_state_observed')
        progress(plan, record['after'])
        need(native_files(folder) == files, 'Native disk write before result Save')
    after = semantic_capture(session, owner, bindings)
    report['after_refresh'] = after
    verify(plan['expected_after'], after)
    report['after_group_summary'] = group_summary(session, owner, bindings)
    need(report['after_group_summary'] == report['baseline_group_summary'],
         'Final native grouping/positions/quantities changed')
    report['saved'] = session.save(owner, owner_path)
    saved_files = native_files(folder)
    report['native_files_after_refresh'] = saved_files
    report['result_changed_files'] = [p for p, h in files.items() if saved_files.get(p) != h]
    need(saved_files.keys() == files.keys() and report['result_changed_files'] == [str(owner_path)],
         'Unexpected refresh dependency writeback')
    session.close(owner)
    for cycle in range(2):
        owner = session.open(owner_path, read_only=True)
        state = semantic_capture(session, owner, bindings)
        report.setdefault('saved_ro', []).append(state)
        verify(plan['expected_after'], state)
        summary = group_summary(session, owner, bindings)
        report.setdefault('saved_ro_group_summary', []).append(summary)
        need(summary == report['baseline_group_summary'], 'Saved native grouping/positions/quantities drift')
        volume = session.call(session.k.measure, owner['document_id'])['volume_mm3']
        report.setdefault('saved_ro_volumes', []).append(volume)
        need(math.isclose(volume, 2640., abs_tol=1e-5), 'Saved geometry volume mismatch')
        session.close(owner)
        need(native_files(folder) == saved_files, 'Result RO wrote native files')
        event('result_saved_RO_verified', cycle=cycle+1)
    copy_native(folder, Path(config['receipts'])/'result-native-copy')
    report.update(acceptance='property_source_batch_exact_saved_two_RO',
                  UUID_links_positions_grouping_FromSource_preserved=True,
                  geometry_or_whole_row_edit_during_refresh=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
    output = Path(config['receipts'])/'text.json'
    need(not output.exists(), 'Existing receipt; reconcile, do not replay')
    report = {'phase': 'starting', 'saved': False, 'events': [], 'runner_sha256': sha(__file__)}
    session, started = None, time.monotonic()

    def flush():
        report['elapsed_seconds'] = time.monotonic()-started
        temp = output.with_suffix('.tmp')
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(output)

    def event(stage, **data):
        report['events'].append({'stage': stage, **data})
        flush()
        print(stage, flush=True)

    flush()
    try:
        session = NativeOwnedSession(config)
        report.update(application=session.identity, baseline=list(session.baseline.values()))
        need(not session.root.exists(), 'A new isolated synthetic root is required')
        session.root.mkdir()
        run(session, config, report, event)
        report['phase'] = 'complete'
    except Exception:  # noqa: BLE001 - retain rejected RAM, no implicit recovery/save/retry
        report.update(phase='failed', error=traceback.format_exc())
    finally:
        if session is not None:
            report['owned_remaining'] = [{'reference': ref, **{
                k: v for k, v in e.items() if k != 'result'}} for ref, e in session.owned.items()]
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
