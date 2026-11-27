"""Explicit API5 text-only continuation after verified immediate-owner refresh.

The prior synthetic receipt and entire saved closure are SHA-pinned. Does not
repeat an outer nested property reset. API7 visual Edit is deliberately unused.
Any FromSource/identity/group/position drift is rejected before Save.
"""

import json
import runpy
from pathlib import Path

from native_owned_session import need, sha
from validate_specification_group_refresh import copy_native, group_summary
from validate_specification_nested_owner import main, saved_observation, verify_observation
from validate_specification_reference import native_files
from validate_specification_text import TextAdapter, context, semantic_capture


def run(session, config, report, event):
    report['continuation_runner_sha256'] = sha(__file__)
    receipt = Path(config['input_receipt'])
    need(sha(receipt) == config['input_receipt_sha256'], 'Prior synthetic receipt changed')
    prior = json.loads(receipt.read_text(encoding='utf-8-sig'))
    need(prior['phase'] == 'complete' and prior['owned_remaining'] == []
         and prior['inner_acceptance'] == 'direct_pair_exact_saved_two_RO'
         and prior['outer_acceptance'] is False, 'Explicit completed two-owner baseline required')
    oracle = runpy.run_path(config['refresh_oracle'])
    verify, planner, progress = (oracle[n] for n in [
        'verify_property_refresh', 'source_property_refresh_plan', 'verify_source_refresh_progress'])
    observed = prior['outer_saved_ro'][-1]['observation']
    path = session.inside(observed['state']['context']['owner'])
    files = prior['native_files_after_refresh']
    need(native_files(path.parent) == files, 'Saved synthetic closure differs from pinned baseline')
    pid, bindings = prior['property_id'], observed['bindings']
    selected = prior['plans']['outer']['stale_rows']
    source_values = prior['actual_source_properties']
    values = {u: {c: v['value'] for c, v in source_values.items()} for u in selected}
    # At this stage the prior child Save has already refreshed display metadata.
    # Owner property values must independently match source; no cache-value waiver.
    plan = planner(observed['state'], selected, values, [pid])
    report.update(before_refresh=observed, plan=plan, native_files_before_refresh=files,
                  method='API5_existing_text_only_after_inner_refresh', property_id=pid)
    for cycle in range(2):
        state = saved_observation(session, path, list(bindings.values()))
        report.setdefault('baseline_saved_ro', []).append(state)
        verify_observation(verify, observed, state)
        need(native_files(path.parent) == files, 'Baseline RO changed disk')
        event('baseline_saved_RO_verified', cycle=cycle+1)
    owner = session.open(path)
    session.doc(owner).Active = True
    adapter, ctx = TextAdapter(session, owner, bindings), context(session, owner)
    verify(observed['state'], semantic_capture(session, owner, bindings))
    if config.get('use_text_helper') is True:
        import importlib

        from specification_source_adapter import SourceAdapter, load_frozen_helper

        package = load_frozen_helper(config)
        helper = importlib.import_module(package.__package__+'.specification_cached_text')
        source_paths = {observed['state']['rows'][u]['geometry'][0]['source'] for u in selected}
        sources = {p: {c: v['value'] for c, v in source_values.items()} for p in source_paths}
        native = SourceAdapter(session, owner, bindings, sources)
        wanted = helper.plan_cached_text_refresh(
            semantic_capture(session, owner, bindings), selected, native.source_evidence(), [pid],
            observed['summary'])
        report['text_helper_sha256'] = sha(helper.__file__)
        report['helper_dry_run'] = helper.author_cached_text_owned(wanted, native)
        event('text_helper_dry_run_observed')
        need(report['helper_dry_run']['status'] == 'ready_without_mutation', 'Text helper preflight failed')
        need(native_files(path.parent) == files, 'Text dry-run wrote disk')
        report['helper_execution'] = helper.author_cached_text_owned(wanted, native, dry_run=False)
        event('text_helper_execution_observed')
        need(report['helper_execution']['status'] == 'verified_unsaved', 'Text helper rejected')
        need(native_files(path.parent) == files, 'Text helper wrote disk before explicit Save')
    else:
        for u in sorted(selected, key=lambda x: observed['state']['rows'][x]['is_first'], reverse=True):
            adapter.guard_owned_context(ctx)
            number = adapter.row_number(u)
            pointer = adapter.pointer_for_number(number)
            need(type(pointer) is int and pointer > 0 and adapter.number_for_pointer(pointer) == number,
                 'Existing UUID/numeric pointer mismatch')
            before = adapter.get_column_text(pointer, pid, 1, 0)
            wanted = plan['expected_after']['rows'][u]['columns'][str(pid)]
            need(type(before) is str and before == observed['state']['rows'][u]['columns'][str(pid)],
                 'Exact API5 getter column does not match complete snapshot')
            record = {'row_uuid': u, 'number': number, 'before': before, 'after_text': wanted,
                      'edit_may_be_open': True}
            report.setdefault('text_calls', []).append(record)
            event('before_API5_Edit')
            adapter.guard_owned_context(ctx)
            record['Edit_return'] = adapter.edit(pointer)
            event('API5_Edit_observed')
            need(type(record['Edit_return']) is int and record['Edit_return'] == 1, 'Edit not long1')
            adapter.guard_owned_context(ctx)
            record['Set_return'] = adapter.set_column_text(pid, 1, 0, wanted)
            event('API5_Set_observed')
            need(type(record['Set_return']) is int and record['Set_return'] == 1, 'Set not long1')
            adapter.guard_owned_context(ctx)
            record['End_pointer'] = adapter.end()
            event('API5_End_observed')
            need(type(record['End_pointer']) is int and record['End_pointer'] > 0
                 and adapter.number_for_pointer(record['End_pointer']) == number, 'End numeric roundtrip failed')
            record['edit_may_be_open'] = False
            record['after'] = semantic_capture(session, owner, bindings)
            event('after_API5_End_state_captured')
            progress(plan, record['after'])
            need(native_files(path.parent) == files, 'Native write before result Save')
    after = {'state': semantic_capture(session, owner, bindings), 'bindings': bindings,
             'summary': group_summary(session, owner, bindings)}
    expected = {**observed, 'state': plan['expected_after']}
    report['after_refresh'] = after
    verify_observation(verify, expected, after)
    report['outer_saved'] = session.save(owner, path)
    saved_files = native_files(path.parent)
    report['native_files_after_refresh'] = saved_files
    need(files.keys() == saved_files.keys()
         and [p for p in files if files[p] != saved_files[p]] == [str(path)],
         'Outer Save wrote other dependencies')
    session.close(owner)
    for cycle in range(2):
        state = saved_observation(session, path, list(bindings.values()))
        report.setdefault('saved_ro', []).append(state)
        verify_observation(verify, expected, state)
        need(native_files(path.parent) == saved_files, 'Result RO changed disk')
        event('outer_text_result_saved_RO_verified', cycle=cycle+1)
    copy_native(path.parent, Path(config['receipts'])/'result-native-copy')
    report['acceptance'] = 'outer_existing_text_only_exact_saved_two_RO'


if __name__ == '__main__':
    raise SystemExit(main(run_case=run, existing_root=True))
