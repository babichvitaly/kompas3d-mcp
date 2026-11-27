"""Controlled stale-model-SP fixture with actual inherited source properties.

Exclusive STA, fresh handover/new synthetic root only. Geometry is never assigned.
The setup explicitly freezes synchronization and replaces a synthetic source by
a same-geometry new revision; it does not reproduce an unsolicited production bug.
Reuses the failure-preserving runner shell; raw/config/native output stays private.
"""

import inspect
import math
import runpy
import shutil
from copy import deepcopy
from pathlib import Path

import validate_specification_text as runner
from native_owned_session import file_tree, need, sha
from validate_specification_reference import (
    build_fixture,
    identify_rows,
    native_files,
    occurrence,
    property_values,
    snapshot,
    strict_bool,
    top,
)
from validate_specification_text import TextAdapter, context, semantic_capture


def create_manual_frozen_row(session, owner, report, event):
    """Initial fixture authoring only; never used to refresh an existing row."""
    part = occurrence(session, owner, [1])
    adapter = TextAdapter(session, owner, {})
    expected_context = context(session, owner)
    adapter.guard_owned_context(expected_context)
    native = session.k.api.ksPart(session.k.app.TransferInterface(
        part, session.k.constants['ksAPI5Auto'], 0))
    restored = session.cast(session.k.app.TransferInterface(
        native, session.k.constants['ksAPI7Dual'], 0), 'IPart7')
    need(restored.Reference == part.Reference, 'Initial API5 component transfer mismatch')
    record = {'edit_may_be_open': True, 'geometry_linking_only_during_initial_creation': True}
    report['manual_row_creation'] = record
    record['Create_return'] = adapter.sp.ksSpcObjectCreate(
        expected_context['layout'], expected_context['style'], 15, 0, 0., 0)
    event('manual_initial_row_Create_observed')
    need(type(record['Create_return']) is int and record['Create_return'] == 1,
         'Initial API5 row Create did not return long1')
    record['Include_return'] = adapter.sp.D3SpcIncludePart(native, False)
    event('manual_initial_row_include_observed')
    strict_bool(record['Include_return'], 'initial D3SpcIncludePart(fillTexts=False)')
    record['Set_returns'] = []
    for c, text in [(4, 'SYNTH-SOURCE-B'), (5, 'Synthetic source B')]:
        result = adapter.sp.ksSetSpcObjectColumnText(c, 1, 0, text)
        record['Set_returns'].append(result)
        event('manual_initial_row_text_observed')
        need(type(result) is int and result == 1, 'Initial column Set did not return long1')
    record['End_pointer'] = adapter.end()
    event('manual_initial_row_End_observed')
    need(type(record['End_pointer']) is int and record['End_pointer'] > 0,
         'Initial row End did not return native pointer')
    record['edit_may_be_open'] = False
    number = adapter.number_for_pointer(record['End_pointer'])
    rows = session.doc(owner).SpecificationDescriptions.Item(0).BaseObjects
    found = [r for i in range(rows.Count) if (r := rows.Item(i)).UniqueNumber == number]
    need(len(found) == 1, 'New manual row numeric identity not unique')
    record['UUID'], record['sync'] = str(found[0].UniqueMetaObjectKey), found[0].SyncronizeWithProperties
    need(record['sync'] is False, 'New manual row is not frozen; fixture not established')


def set_sync(adapter, row_uuids, value, report, event, label, route):
    expected_context = context(adapter.session, adapter.owner)
    for uuid in row_uuids:
        adapter.guard_owned_context(expected_context)
        number = adapter.row_number(uuid)
        ptr = adapter.pointer_for_number(number)
        need(type(ptr) is int and ptr > 0 and adapter.number_for_pointer(ptr) == number,
             'Invalid API5 numeric mapping for sync operation')
        before = adapter.sp.ksGetSpcPropertyFill(ptr)
        need(type(before) is bool, 'Sync getter did not return native BOOL')
        record = {'uuid': uuid, 'number': number, 'pointer': ptr, 'before': before,
                  'wanted': value, 'route': route, 'edit_may_be_open': False}
        report.setdefault(label, []).append(record)
        if route in {'edit_set_end', 'api7_edit_end'}:
            record['edit_may_be_open'] = True
            record['Edit_return'] = adapter.edit(ptr)
            event(label+'_Edit_observed')
            need(type(record['Edit_return']) is int and record['Edit_return'] == 1,
                 'Sync Edit did not return native long1')
        if route in {'api7_edit_end', 'api7_update'}:
            adapter.row_object(uuid).SyncronizeWithProperties = value
            record['Set_return'] = None
            record['Set_contract'] = 'API7 property put, void'
        else:
            record['Set_return'] = adapter.sp.ksSetSpcPropertyFill(ptr, int(value))
        event(label+'_return_observed')
        if route not in {'api7_edit_end', 'api7_update'}:
            strict_bool(record['Set_return'], 'ksSetSpcPropertyFill')
        if route == 'api7_update':
            record['Update_return'] = adapter.row_object(uuid).Update()
            event(label+'_API7_Update_observed')
            strict_bool(record['Update_return'], 'API7 sync flag Update')
        if route in {'edit_set_end', 'api7_edit_end'}:
            record['End_pointer'] = adapter.end()
            event(label+'_End_observed')
            need(type(record['End_pointer']) is int and record['End_pointer'] > 0,
                 'Sync End did not return positive native pointer')
            record['edit_may_be_open'] = False
            need(adapter.number_for_pointer(record['End_pointer']) == number, 'Sync End numeric drift')
        record['after'] = adapter.sp.ksGetSpcPropertyFill(ptr)
        record['API7_after'] = adapter.row_object(uuid).SyncronizeWithProperties
        need(type(record['after']) is bool and record['after'] is value, 'Sync readback mismatch')
        need(type(record['API7_after']) is bool and record['API7_after'] is value, 'API7 sync readback mismatch')
        adapter.guard_owned_context(expected_context)


def run(session, config, report, event):
    from kompas_mcp import documents

    if config.get('fixture_kind') == 'reset_property_override':
        return run_reset_property_override(session, config, report, event)
    if config.get('fixture_kind') == 'source_metadata_change':
        return run_source_metadata_change(session, config, report, event)
    oracle = runpy.run_path(config['refresh_oracle'])
    verify = oracle['verify_property_refresh']
    need(config.get('sync_route') in {'direct', 'edit_set_end', 'api7_edit_end', 'api7_update'},
         'Explicit sync route required')
    if config.get('fixture_kind') == 'manual_frozen':
        need({'ksAPI5Auto', 'ksAPI7Dual'} <= session.k.constants.keys(),
             'Installed API5/7 interface constants unavailable')
        report['initial_creation_signatures'] = {name: str(inspect.signature(getattr(
            session.k.api.ksSpecification, name))) for name in ['ksSpcObjectCreate', 'D3SpcIncludePart']}
    report.update(case_runner_sha256=sha(__file__),
                  refresh_oracle_sha256=sha(config['refresh_oracle']),
                  text_helper_sha256=sha(config['text_helper']),
                  controlled_setup=config.get('fixture_kind', 'automatic')+' + own source revision',
                  spontaneous_production_stale_reproduced=False)
    folder = session.root/'stale'
    owner, source_b, paths = build_fixture(session, folder, event)
    session.call(documents.insert_component, session.k, owner['document']['handle'],
                 str(source_b), linked=True)
    control = occurrence(session, owner, [1])
    manual = config.get('fixture_kind') == 'manual_frozen'
    need(not manual or config['target_case'] == 'unique', 'Manual fixture selects unique occurrence only')
    control.CreateSpcObjects, control.RevealComposition, control.Fixed = not manual, False, True
    strict_bool(control.Update(), 'new synthetic unique occurrence setup')
    if manual:
        need(session.doc(owner).SpecificationDescriptions.Item(0).BaseObjects.Count == 2,
             'Unexpected automatic unique row before manual initial creation')
        create_manual_frozen_row(session, owner, report, event)
    owner_path = Path(session.doc(owner).PathName)
    session.save(owner, owner_path)
    session.close(owner)
    owner = session.open(owner_path)
    session.doc(owner).Active = True
    raw = snapshot(session, owner)
    bindings = identify_rows(raw, paths+[[1]])
    selected = list(identify_rows(raw, [[1]] if config['target_case'] == 'unique' else paths))
    need(len(bindings) == 3, 'Expected complete three-row fixture mapping')
    adapter = TextAdapter(session, owner, bindings)
    original = semantic_capture(session, owner, bindings)
    report.update(initial=original, all_bindings=bindings, selected_uuids=selected,
                  sync_signatures={name: str(inspect.signature(getattr(
                      session.k.api.ksSpecification, name))) for name in [
                          'ksGetSpcPropertyFill', 'ksSetSpcPropertyFill']})
    if manual:
        need(all(original['rows'][uuid]['sync'] is False for uuid in selected),
             'Manual row did not preserve SyncFalse through fixture save/reopen')
    else:
        set_sync(adapter, selected, False, report, event, 'setup_sync_false', config['sync_route'])
    frozen = semantic_capture(session, owner, bindings)
    expected_frozen = deepcopy(original)
    for uuid in selected:
        expected_frozen['rows'][uuid]['sync'] = False
    verify(expected_frozen, frozen)
    exercise_from_frozen(session, config, report, event, owner, folder, source_b,
                         bindings, selected, frozen)


def exercise_from_frozen(session, config, report, event, owner, folder, source_b,
                         bindings, selected, frozen):
    """Continue a proved frozen own fixture; never creates or replaces SP rows."""
    oracle = runpy.run_path(config['refresh_oracle'])
    plan_stale, verify = oracle['current_property_text_plan'], oracle['verify_property_refresh']
    author = runpy.run_path(config['text_helper'])['author_existing_row_text_owned']
    owner_path = Path(session.doc(owner).PathName)
    report['frozen_before_source_change'] = frozen
    report['frozen_save'] = session.save(owner, owner_path)
    session.close(owner)
    # Revision path avoids an in-place filename/cache update. All source files
    # are generated by this run; no engineering files or prior fixtures are read.
    source_old = Path(source_b) if config['target_case'] == 'unique' else folder/'SYNTH-SOURCE-A.a3d'
    source_new = folder/'SYNTH-SOURCE-CURRENT.a3d'
    session.guard()
    session.inside(source_new)
    need(not source_new.exists(), 'Never overwrite a source revision')
    shutil.copy2(source_old, source_new)
    source = session.open(source_new)
    part = top(session, source)
    part.Name, part.Marking = 'Synthetic current source', 'SYNTH-CURRENT'
    strict_bool(part.Update(), 'own revision source properties')
    report['source_revision_save'] = session.save(source, source_new)
    session.close(source)
    owner = session.open(owner_path)
    session.doc(owner).Active = True
    for uuid in selected:
        target = occurrence(session, owner, bindings[uuid])
        need(str(target.FileName) == str(source_old), 'Wrong old source occurrence')
        target.FileName = str(source_new)
        updated = target.Update()
        report.setdefault('source_replacement_updates', []).append({'uuid': uuid, 'return': updated})
        event('source_replacement_return_observed')
        strict_bool(updated, 'own source revision replacement')
    stale = semantic_capture(session, owner, bindings)
    report['stale_before_owner_save'] = stale
    report['stale_oracle_before_owner_save'] = plan_stale(stale, selected, restore_sync=True)
    for uuid in selected:
        need(all(stale['properties'][uuid][str(c)]['value'] == value
                 for c, value in [(4, 'SYNTH-CURRENT'), (5, 'Synthetic current source')]),
             'Source revision properties are not already current')
        need(stale['rows'][uuid]['columns'] == frozen['rows'][uuid]['columns'],
             'Frozen row text changed during setup; stale fixture not established')
    event('stale_text_with_current_FromSource_before_save_proven')
    report['stale_setup_files_before_save'] = native_files(folder)
    report['stale_save'] = session.save(owner, owner_path)
    report['stale_setup_files_after_save'] = native_files(folder)
    report['setup_writeback_files'] = [p for p, h in report['stale_setup_files_before_save'].items()
                                       if report['stale_setup_files_after_save'].get(p) != h]
    session.close(owner)
    # A stale fixture is accepted only after two independent read-only reopenings.
    for cycle in range(2):
        owner = session.open(owner_path, read_only=True)
        state = semantic_capture(session, owner, bindings)
        report.setdefault('stale_saved_ro', []).append(state)
        verify(stale, state)
        plan_stale(state, selected, restore_sync=True)
        session.close(owner)
        need(native_files(folder) == report['stale_setup_files_after_save'],
             'Stale read-only baseline changed disk files')
        event('stale_fixture_saved_RO_verified', cycle=cycle+1)
    owner = session.open(owner_path)
    session.doc(owner).Active = True
    adapter = TextAdapter(session, owner, bindings)
    before = semantic_capture(session, owner, bindings)
    verify(stale, before)
    preserve_false = config.get('refresh_route') == 'preserve_false_text'
    planned = plan_stale(before, selected, restore_sync=not preserve_false, expected_sync=False)
    report.update(before_refresh=before, refresh_oracle=planned,
                  refresh_native_files_before=native_files(folder),
                  refresh_all_files_before=file_tree([folder]))
    if not preserve_false:
        set_sync(adapter, selected, True, report, event, 'restore_sync_true', config['sync_route'])
    after_enable = semantic_capture(session, owner, bindings)
    report['after_sync_enable'] = after_enable
    expected = planned['expected_after']
    if not preserve_false and after_enable == expected:
        report['refresh_route'] = 'ksSetSpcPropertyFill_restore_true'
    else:
        # Only continue to text editing if the complete state is still stale,
        # now with Sync=True and every property/FromSource unchanged.
        still_stale = deepcopy(before)
        if not preserve_false:
            for uuid in selected:
                still_stale['rows'][uuid]['sync'] = True
        verify(still_stale, after_enable)
        direct_plan = plan_stale(after_enable, selected, expected_sync=not preserve_false)
        report['stale_before_text_write'] = direct_plan
        event('stale_current_FromSource_before_text_write_proven', sync=not preserve_false)
        for plan in direct_plan['plans']:
            plan['expected_context'] = context(session, owner)
            result = author(plan, adapter)
            report.setdefault('text_edits', []).append(result)
            event('API5_refresh_text_return_observed', status=result['status'])
            need(result['status'] == 'text_verified_in_adapter',
                 'Text refresh rejected complete payload gate; no Save/retry')
        report['refresh_route'] = ('API5_text_preserve_explicit_SyncFalse' if preserve_false
                                   else 'restore_sync_then_API5_existing_row_text')
    after = semantic_capture(session, owner, bindings)
    report['after_refresh'] = after
    verify(expected, after)
    need(native_files(folder) == report['refresh_native_files_before'], 'Disk write before refresh Save')
    report['saved'] = session.save(owner, owner_path)
    saved_files = native_files(folder)
    report.update(refresh_native_files_after=saved_files, refresh_all_files_after=file_tree([folder]))
    changed = [p for p, h in report['refresh_native_files_before'].items() if saved_files.get(p) != h]
    report['refresh_writeback_files'] = changed
    need(saved_files.keys() == report['refresh_native_files_before'].keys()
         and changed == [str(owner_path)], 'Unexpected refresh dependency writeback')
    session.close(owner)
    for cycle in range(2):
        owner = session.open(owner_path, read_only=True)
        state = semantic_capture(session, owner, bindings)
        report.setdefault('saved_ro', []).append(state)
        verify(expected, state)
        volume = session.call(session.k.measure, owner['document_id'])['volume_mm3']
        need(math.isclose(volume, 2640., abs_tol=1e-5), 'Saved material volume mismatch')
        report.setdefault('saved_ro_volumes', []).append(volume)
        if cycle == 0:
            report['preview'] = session.call(session.k.preview, owner['document_id'],
                                             str(Path(config['receipts'])/'saved-preview.png'))
        session.close(owner)
        need(native_files(folder) == saved_files, 'Result read-only cycle changed disk files')
        event('refresh_saved_RO_verified', cycle=cycle+1)
    report.update(acceptance='controlled_stale_current_properties_refresh_two_RO',
                  stale_fixture_reproduced=True, full_observed_refresh_preservation=True)


def run_reset_property_override(session, config, report, event):
    """Experimental unset-override hypothesis; no documented inheritance guarantee.

    SetPropertyValue's third argument is BaseUnit, NOT FromSource. Only native
    readback may establish that an empty/null value restored source inheritance.
    """
    import pythoncom
    from win32com.client import VARIANT

    from kompas_mcp import documents

    need(config.get('reset_variant') in {'empty', 'null'}, 'Explicit reset variant required')
    oracle = runpy.run_path(config['refresh_oracle'])
    plan_stale, verify = oracle['current_property_text_plan'], oracle['verify_property_refresh']
    report.update(case_runner_sha256=sha(__file__), reset_variant=config['reset_variant'],
                  reset_inheritance_is_unproved_hypothesis=True,
                  SetPropertyValue_signature=str(inspect.signature(
                      session.k.modules['kAPI7'].IPropertyKeeper.SetPropertyValue)))
    folder = session.root/'reset'
    owner, source_b, paths = build_fixture(session, folder, event)
    session.call(documents.insert_component, session.k, owner['document']['handle'],
                 str(source_b), linked=True)
    part = occurrence(session, owner, [1])
    part.CreateSpcObjects, part.RevealComposition, part.Fixed = True, False, True
    strict_bool(part.Update(), 'new synthetic unique occurrence')
    owner_path = Path(session.doc(owner).PathName)
    session.save(owner, owner_path)
    session.close(owner)
    owner = session.open(owner_path)
    session.doc(owner).Active = True
    raw = snapshot(session, owner)
    bindings = identify_rows(raw, paths+[[1]])
    selected = list(identify_rows(raw, [[1]]))
    need(len(bindings) == 3 and len(selected) == 1, 'Wrong reset fixture membership')
    uuid = selected[0]
    adapter = TextAdapter(session, owner, bindings)
    initial = semantic_capture(session, owner, bindings)
    report.update(initial=initial, all_bindings=bindings, selected_uuids=selected,
                  baseline_files=native_files(folder))
    need(all(p['from_source'] is True for p in initial['properties'][uuid].values()),
         'Initial synthetic occurrence is not inherited')
    ctx = context(session, owner)
    adapter.guard_owned_context(ctx)
    number = adapter.row_number(uuid)
    ptr = adapter.pointer_for_number(number)
    need(type(ptr) is int and ptr > 0 and adapter.number_for_pointer(ptr) == number,
         'Fixture text injection mapping mismatch')
    injection = {'edit_may_be_open': True, 'Edit_return': adapter.edit(ptr)}
    report['fixture_text_injection'] = injection
    event('fixture_text_Edit_observed')
    need(type(injection['Edit_return']) is int and injection['Edit_return'] == 1, 'Fixture Edit failed')
    injection['Set_returns'] = []
    for column, text in [(4, 'SYNTH-STALE-TEXT'), (5, 'Synthetic stale text')]:
        adapter.guard_owned_context(ctx)
        need(adapter.get_column_text(ptr, column, 1, 0)
             == initial['rows'][uuid]['columns'][str(column)], 'Fixture column address mismatch')
        result = adapter.set_column_text(column, 1, 0, text)
        injection['Set_returns'].append(result)
        event('fixture_text_Set_observed')
        need(type(result) is int and result == 1, 'Fixture Set failed')
    injection['End_pointer'] = adapter.end()
    event('fixture_text_End_observed')
    need(type(injection['End_pointer']) is int and injection['End_pointer'] > 0,
         'Fixture End did not return pointer')
    injection['edit_may_be_open'] = False
    need(adapter.number_for_pointer(injection['End_pointer']) == number, 'Fixture End numeric drift')
    injected = semantic_capture(session, owner, bindings)
    report['injected_local_override'] = injected
    expected_injection = deepcopy(initial)
    for c, value in [(4, 'SYNTH-STALE-TEXT'), (5, 'Synthetic stale text')]:
        expected_injection['rows'][uuid]['columns'][str(c)] = value
        expected_injection['properties'][uuid][str(c)] = {'value': value, 'from_source': False}
    for item in [expected_injection['rows'][uuid]['geometry'][0]] + [
            node for tree in ['top_tree', 'main_tree'] for node in expected_injection[tree]
            if node['path'] == [1]]:
        item.update(name='Synthetic stale text', marking='SYNTH-STALE-TEXT')
    verify(expected_injection, injected)
    keeper = session.cast(occurrence(session, owner, [1]), 'IPropertyKeeper')
    manager = session.cast(session.app, 'IPropertyMng')
    variant_type = pythoncom.VT_EMPTY if config['reset_variant'] == 'empty' else pythoncom.VT_NULL
    for column in [4, 5]:
        adapter.guard_owned_context(ctx)
        prop = manager.GetProperty(session.doc(owner), float(column))
        need(prop is not None and float(prop.Id) == column, 'Wrong property identity during reset')
        result = keeper.SetPropertyValue(prop, VARIANT(variant_type, None), False)
        record = {'column': column, 'variant_type': variant_type, 'BaseUnit': False, 'return': result}
        report.setdefault('reset_calls', []).append(record)
        event('property_reset_return_observed')
        strict_bool(result, 'SetPropertyValue reset hypothesis')
        record['state_after'] = semantic_capture(session, owner, bindings)
        event('property_reset_readback_observed')
    stale = semantic_capture(session, owner, bindings)
    report['after_property_reset'] = stale
    for c in ['4', '5']:
        need(stale['properties'][uuid][c] == initial['properties'][uuid][c],
             'Reset did not restore the current source property and FromSource=True')
    planned = plan_stale(stale, selected)
    report['stale_before_refresh_write'] = stale
    report['stale_oracle'] = planned
    event('stale_SyncTrue_current_FromSource_before_refresh_write_proven')
    refresh_stale_sync_true(session, config, report, event, owner, folder, bindings,
                            selected, stale, planned, report['baseline_files'])


def refresh_stale_sync_true(session, config, report, event, owner, folder, bindings,
                            selected, stale, planned, baseline_files):
    """Exact text refresh only after a separately established native stale oracle."""
    verify = runpy.run_path(config['refresh_oracle'])['verify_property_refresh']
    author = runpy.run_path(config['text_helper'])['author_existing_row_text_owned']
    adapter = TextAdapter(session, owner, bindings)
    ctx = context(session, owner)
    need(len(selected) == 1, 'This transaction selects one unique row with duplicate controls')
    number = adapter.row_number(selected[0])
    ptr = adapter.pointer_for_number(number)
    need(type(ptr) is int and ptr > 0 and adapter.number_for_pointer(ptr) == number,
         'Refresh numeric mapping mismatch')
    owner_path = Path(session.doc(owner).PathName)
    expected = planned['expected_after']
    adapter.guard_owned_context(ctx)
    report['fill_true_return'] = adapter.sp.ksSetSpcPropertyFill(ptr, 1)
    event('fill_true_refresh_return_observed')
    strict_bool(report['fill_true_return'], 'fill_true refresh candidate')
    filled = semantic_capture(session, owner, bindings)
    report['after_fill_true'] = filled
    if filled == expected:
        report['refresh_route'] = 'ksSetSpcPropertyFill_true_on_stale_SyncTrue'
    else:
        verify(stale, filled)
        result = author(planned['plans'][0], adapter)
        report['text_refresh'] = result
        event('API5_text_refresh_return_observed', status=result['status'])
        need(result['status'] == 'text_verified_in_adapter', 'Full text refresh gate failed; no Save')
        report['refresh_route'] = 'API5_existing_text_already_current_properties'
    after = semantic_capture(session, owner, bindings)
    report['after_refresh'] = after
    verify(expected, after)
    need(native_files(folder) == baseline_files, 'Unexpected native disk write during RAM test')
    report['saved'] = session.save(owner, owner_path)
    saved_files = native_files(folder)
    report['saved_files'] = saved_files
    report['writeback_files'] = [p for p, h in baseline_files.items() if saved_files.get(p) != h]
    need(saved_files.keys() == baseline_files.keys()
         and report['writeback_files'] == [str(owner_path)], 'Unexpected result dependency writeback')
    session.close(owner)
    for cycle in range(2):
        owner = session.open(owner_path, read_only=True)
        state = semantic_capture(session, owner, bindings)
        report.setdefault('saved_ro', []).append(state)
        verify(expected, state)
        volume = session.call(session.k.measure, owner['document_id'])['volume_mm3']
        need(math.isclose(volume, 2640., abs_tol=1e-5), 'Saved reset fixture volume mismatch')
        report.setdefault('saved_ro_volumes', []).append(volume)
        session.close(owner)
        need(native_files(folder) == saved_files, 'Read-only result cycle changed files')
        event('refresh_saved_RO_verified', cycle=cycle+1)
    report.update(acceptance='controlled_stale_SyncTrue_current_properties_refresh_two_RO',
                  stale_fixture_reproduced=True, full_observed_refresh_preservation=True)


def run_source_metadata_change(session, config, report, event):
    """Edit an own source while its owner is closed; never update the occurrence."""
    from kompas_mcp import documents

    verify = runpy.run_path(config['refresh_oracle'])['verify_property_refresh']
    plan_stale = runpy.run_path(config['refresh_oracle'])['current_property_text_plan']
    report.update(case_runner_sha256=sha(__file__),
                  controlled_setup='same-filename own source metadata change while owner closed',
                  sync_flag_writes=0, geometry_writes_after_fixture=0,
                  owner_rebuild_calls=0, occurrence_Update_calls_after_source_edit=0)
    folder = session.root/'source_change'
    owner, source_b, paths = build_fixture(session, folder, event)
    session.call(documents.insert_component, session.k, owner['document']['handle'],
                 str(source_b), linked=True)
    part = occurrence(session, owner, [1])
    part.CreateSpcObjects, part.RevealComposition, part.Fixed = True, False, True
    strict_bool(part.Update(), 'initial synthetic unique occurrence')
    owner_path = Path(session.doc(owner).PathName)
    session.save(owner, owner_path)
    session.close(owner)
    owner = session.open(owner_path, read_only=True)
    raw = snapshot(session, owner)
    bindings = identify_rows(raw, paths+[[1]])
    selected = list(identify_rows(raw, [[1]]))
    initial = semantic_capture(session, owner, bindings)
    report.update(initial=initial, all_bindings=bindings, selected_uuids=selected,
                  files_before_source_edit=native_files(folder))
    session.close(owner)
    source = session.open(source_b)
    root = top(session, source)
    need(config.get('source_columns', [5]) in [[5], [4, 5]], 'Explicit source metadata fields required')
    root.Name = 'Synthetic current source'
    if 4 in config.get('source_columns', [5]):
        root.Marking = 'SYNTH-CURRENT'
    report['source_root_Update_return'] = root.Update()
    event('source_root_metadata_Update_observed')
    strict_bool(report['source_root_Update_return'], 'own source metadata Update')
    volume = session.call(session.k.measure, source['document_id'])['volume_mm3']
    need(math.isclose(volume, 1040., abs_tol=1e-5), 'Source material changed during metadata setup')
    report['source_save'] = session.save(source, source_b)
    session.close(source)
    source = session.open(source_b, read_only=True)
    report['actual_saved_source_properties'] = property_values(session, source, [])
    session.close(source)
    files = native_files(folder)
    report['files_after_source_edit'] = files
    changed = [p for p, h in report['files_before_source_edit'].items() if files.get(p) != h]
    need(files.keys() == report['files_before_source_edit'].keys() and changed == [str(source_b)],
         'Source metadata setup changed unexpected native files')
    report['source_only_writeback'] = changed
    owner = session.open(owner_path)
    session.doc(owner).Active = True
    stale = semantic_capture(session, owner, bindings)
    report['source_changed_owner_readback_before_any_owner_Update'] = stale
    for uuid in selected:
        need(all(stale['properties'][uuid][str(c)] == {
                    'value': report['actual_saved_source_properties'][str(c)]['value'],
                    'from_source': True} for c in [4, 5]),
             'Owner does not expose already-current inherited source properties')
    planned = plan_stale(stale, selected)
    report.update(stale_before_refresh_write=stale, stale_oracle=planned)
    event('stale_SyncTrue_current_FromSource_without_owner_Update_proven')
    session.close(owner)
    # The owner disk has not been written since baseline creation. Reopen it
    # twice against the edited source to distinguish a retained stale SP payload
    # from an observation-order artefact in one RAM snapshot.
    for cycle in range(2):
        owner = session.open(owner_path, read_only=True)
        state = semantic_capture(session, owner, bindings)
        report.setdefault('stale_saved_ro', []).append(state)
        verify(stale, state)
        plan_stale(state, selected)
        session.close(owner)
        need(native_files(folder) == files, 'Stale read-only baseline wrote files')
        event('stale_fixture_saved_RO_verified', cycle=cycle+1)
    owner = session.open(owner_path)
    session.doc(owner).Active = True
    before = semantic_capture(session, owner, bindings)
    verify(stale, before)
    report['before_refresh'] = before
    refresh_stale_sync_true(session, config, report, event, owner, folder, bindings,
                            selected, before, plan_stale(before, selected), files)


if __name__ == '__main__':
    raise SystemExit(runner.main(run_case=run))
