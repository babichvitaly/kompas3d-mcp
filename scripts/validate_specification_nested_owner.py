"""Opt-in two-owner source-property experiment on new synthetic documents.

Refresh only direct occurrences in their saved immediate owner. Observe the
outer owner's existing nested SP rows separately; no outer repair or save is
implicit. Every accepted owner keeps its own UUID/payload/positions/source flags.
"""

import argparse
import json
import math
import runpy
import time
import traceback
from pathlib import Path

from native_owned_session import NativeOwnedSession, need, sha
from validate_specification_group_refresh import copy_native, group_summary, initialize_positions
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


def saved_observation(session, path, paths):
    owner = session.open(path, read_only=True)
    bindings = identify_rows(snapshot(session, owner), paths)
    state = semantic_capture(session, owner, bindings)
    summary = group_summary(session, owner, bindings)
    volume = session.call(session.k.measure, owner['document_id'])['volume_mm3']
    session.close(owner)
    need(math.isclose(volume, 2640., abs_tol=1e-5), 'Owner geometry volume mismatch')
    return {'bindings': bindings, 'state': state, 'summary': summary, 'volume': volume}


def verify_observation(verify, expected, actual):
    need(expected['bindings'] == actual['bindings'], 'Owner UUID/occurrence paths drift')
    verify(expected['state'], actual['state'])
    need(expected['summary'] == actual['summary'], 'Native group summary/positions drift')


def make_plan(planner, observation, source, pid, source_path):
    targets = [u for u, p in observation['bindings'].items() if p[-1] in {0, 1}]
    need(len(targets) == 2 and len(observation['bindings']) == 3, 'Explicit duplicate pair required')
    state = observation['state']
    for u in targets:
        need(state['rows'][u]['geometry'][0]['source'] == str(source_path),
             'Target does not refer to the independently verified source')
        need(state['rows'][u]['columns']['3'].isdigit(), 'Selected positions must be nonblank numbers')
    values = {u: {c: v['value'] for c, v in source.items()} for u in targets}
    return planner(state, targets, values, [pid], allow_property_value_refresh=pid == 4)


def run(session, config, report, event):
    import pythoncom
    from win32com.client import VARIANT

    from kompas_mcp import documents

    oracle = runpy.run_path(config['refresh_oracle'])
    verify, planner, progress = (oracle[n] for n in [
        'verify_property_refresh', 'source_property_refresh_plan', 'verify_source_refresh_progress'])
    pid = config['property_id']
    need(type(pid) is int and pid in {4, 5}, 'Explicit property4/5 required')
    folder = session.root/'nested_owner'
    template, source_b, _ = build_fixture(session, folder, event)
    session.close(template)
    inner_path = folder/'SYNTH-PRODUCT.a3d'
    inner = session.open(inner_path)
    session.call(documents.insert_component, session.k, inner['document']['handle'], str(source_b), linked=True)
    part = occurrence(session, inner, [2])
    part.CreateSpcObjects, part.RevealComposition, part.Fixed = True, False, True
    strict_bool(part.Update(), 'initial direct control')
    initialize_positions(session, inner, [[0], [1]], [2], report, event, restore_inheritance=True)
    session.save(inner, inner_path)
    session.close(inner)
    outer = new_assembly(session, folder, 'Synthetic context owner', 'SYNTH-CONTEXT-OWNER',
                         [inner_path], reveal=True)
    outer_path = Path(session.doc(outer).PathName)
    session.close(outer)
    paths = {'inner': [[0], [1], [2]], 'outer': [[0, 0], [0, 1], [0, 2]]}
    owners = {'inner': inner_path, 'outer': outer_path}
    report['initial'] = {k: saved_observation(session, p, paths[k]) for k, p in owners.items()}
    source_path = folder/'SYNTH-SOURCE-A.a3d'
    disk = native_files(folder)
    source = session.open(source_path)
    root = top(session, source)
    if pid == 4:
        root.Marking = 'SYNTH-CURRENT-DESIGNATION'
    else:
        root.Name = 'Synthetic current nested name'
    report['source_Update_return'] = root.Update()
    event('source_Update_observed')
    strict_bool(report['source_Update_return'], 'source metadata Update')
    volume = session.call(session.k.measure, source['document_id'])['volume_mm3']
    need(math.isclose(volume, 800., abs_tol=1e-5), 'Source geometry changed')
    report['source_save'] = session.save(source, source_path)
    session.close(source)
    source = session.open(source_path, read_only=True)
    source_values = property_values(session, source, [])
    session.close(source)
    files = native_files(folder)
    need(files.keys() == disk.keys() and [p for p in disk if disk[p] != files[p]] == [str(source_path)],
         'Source-change fixture changed another native file')
    report.update(actual_source_properties=source_values, native_files_before_refresh=files,
                  property_id=pid, refresh_owner='inner_direct_occurrences',
                  outer_observation_only=True)
    before, plans = {}, {}
    for label, path in owners.items():
        before[label] = saved_observation(session, path, paths[label])
        plans[label] = make_plan(planner, before[label], source_values, pid, source_path)
        report.update(before_refresh=before, plans=plans)
        event('stale_owner_verified', owner=label)
        for cycle in range(2):
            observed = saved_observation(session, path, paths[label])
            report.setdefault('baseline_saved_ro', {}).setdefault(label, []).append(observed)
            verify_observation(verify, before[label], observed)
            need(native_files(folder) == files, 'Baseline RO changed native files')
            event('baseline_saved_RO_verified', owner=label, cycle=cycle+1)
    copy_native(folder, Path(config['receipts'])/'baseline-native-copy')
    inner = session.open(inner_path)
    session.doc(inner).Active = True
    bindings, plan = before['inner']['bindings'], plans['inner']
    verify(before['inner']['state'], semantic_capture(session, inner, bindings))
    adapter, manager = TextAdapter(session, inner, bindings), session.cast(session.app, 'IPropertyMng')
    ctx = context(session, inner)
    selected = sorted(plan['stale_rows'], key=lambda u: before['inner']['state']['rows'][u]['is_first'],
                      reverse=True)
    if config.get('use_source_helper') is True:
        from specification_source_adapter import SourceAdapter, load_frozen_helper

        helper = load_frozen_helper(config)
        sources = {str(source_path): {c: v['value'] for c, v in source_values.items()}}
        native = SourceAdapter(session, inner, bindings, sources)
        wanted = helper.plan_owned_source_refresh(
            semantic_capture(session, inner, bindings), bindings, selected, native.source_evidence(), [pid],
            before['inner']['summary'], allow_property_value_refresh=pid == 4)
        report['source_helper_sha256'] = sha(helper.__file__)
        report['helper_dry_run'] = helper.refresh_owned_sources(wanted, native)
        event('helper_dry_run_observed')
        need(report['helper_dry_run']['status'] == 'ready_without_mutation', 'Helper preflight failed')
        need(native_files(folder) == files, 'Dry-run changed disk')
        report['helper_execution'] = helper.refresh_owned_sources(wanted, native, dry_run=False)
        event('helper_execution_observed')
        need(report['helper_execution']['status'] == 'verified_unsaved', 'Helper execution rejected')
        need(native_files(folder) == files, 'Helper wrote native disk before explicit Save')
    else:
        for u in selected:
            adapter.guard_owned_context(ctx)
            keeper = session.cast(occurrence(session, inner, bindings[u]), 'IPropertyKeeper')
            prop = manager.GetProperty(session.doc(inner), float(pid))
            need(prop is not None and float(prop.Id) == pid, 'Wrong direct owner property')
            returned = keeper.SetPropertyValue(prop, VARIANT(pythoncom.VT_EMPTY, None), False)
            record = {'row_uuid': u, 'property_id': pid, 'return': returned}
            report.setdefault('property_calls', []).append(record)
            event('inner_source_reset_return_observed')
            strict_bool(returned, 'inner direct source reset')
            record['after'] = semantic_capture(session, inner, bindings)
            record['summary'] = group_summary(session, inner, bindings)
            progress(plan, record['after'])
            need(native_files(folder) == files, 'Disk changed before inner Save')
            event('inner_source_reset_state_verified')
    after = {'bindings': bindings, 'state': semantic_capture(session, inner, bindings),
             'summary': group_summary(session, inner, bindings)}
    expected = {**before['inner'], 'state': plan['expected_after']}
    report['inner_after_refresh'] = after
    verify_observation(verify, expected, after)
    report['inner_saved'] = session.save(inner, inner_path)
    saved_files = native_files(folder)
    report['native_files_after_refresh'] = saved_files
    need(saved_files.keys() == files.keys()
         and [p for p in files if files[p] != saved_files[p]] == [str(inner_path)],
         'Immediate-owner Save changed other dependencies/outer owner')
    session.close(inner)
    for cycle in range(2):
        observed = saved_observation(session, inner_path, paths['inner'])
        report.setdefault('inner_saved_ro', []).append(observed)
        verify_observation(verify, expected, observed)
        need(native_files(folder) == saved_files, 'Inner RO changed disk')
        event('inner_result_saved_RO_verified', cycle=cycle+1)
    # This stage observes only. Never save the outer document to bypass a failed
    # propagation gate or repair its positions/UUIDs/geometry after the fact.
    outer_expected = {**before['outer'], 'state': plans['outer']['expected_after']}
    accepted = []
    for cycle in range(2):
        observed = saved_observation(session, outer_path, paths['outer'])
        record = {'observation': observed}
        report.setdefault('outer_saved_ro', []).append(record)
        try:
            verify_observation(verify, outer_expected, observed)
            record['exact_expected_refresh'] = True
        except (ValueError, RuntimeError) as exc:
            record.update(exact_expected_refresh=False, rejection=str(exc))
        accepted.append(record['exact_expected_refresh'])
        need(native_files(folder) == saved_files, 'Outer RO changed disk')
        event('outer_after_inner_save_observed', cycle=cycle+1, accepted=accepted[-1])
    copy_native(folder, Path(config['receipts'])/'result-native-copy')
    report.update(inner_acceptance='direct_pair_exact_saved_two_RO', outer_acceptance=all(accepted),
                  acceptance=('inner_and_outer_exact_two_RO' if all(accepted)
                              else 'inner_accepted_outer_propagation_not_accepted'),
                  outer_Save_calls=0, geometry_or_whole_row_edit_during_refresh=False)


def main(run_case=run, *, existing_root=False):
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    config = json.loads(Path(parser.parse_args().config).read_text(encoding='utf-8-sig'))
    output = Path(config['receipts'])/'text.json'
    need(not output.exists(), 'Existing receipt; reconcile, do not replay')
    report = {'phase': 'starting', 'events': [], 'runner_sha256': sha(__file__), 'inner_saved': False}
    started, session = time.monotonic(), None

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
        if existing_root:
            need(session.root.is_dir(), 'Explicit continuation root is absent')
        else:
            need(not session.root.exists(), 'New synthetic root required')
            session.root.mkdir()
        run_case(session, config, report, event)
        report['phase'] = 'complete'
    except Exception:  # noqa: BLE001 - retain failed RAM, no implicit retry/save/cleanup
        report.update(phase='failed', error=traceback.format_exc())
    finally:
        if session is not None:
            report['owned_remaining'] = [{'reference': ref, **{k: v for k, v in e.items() if k != 'result'}}
                                         for ref, e in session.owned.items()]
            try:
                report['final_guard'] = session.guard()
                report['preservation'] = session.verify_files()
            except Exception:  # noqa: BLE001 - unknown preservation forbids automatic recovery
                report['preservation_error'] = traceback.format_exc()
            session.release()
        flush()
        terminal = Path(config['receipts'])/'text-terminal.json'
        need(not terminal.exists(), 'Existing terminal receipt')
        terminal.write_text(json.dumps({'phase': report['phase'], 'report': str(output)}, indent=2))
    return int(report['phase'] == 'failed')


if __name__ == '__main__':
    raise SystemExit(main())
