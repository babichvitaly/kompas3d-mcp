"""Opt-in direct-occurrence property-source reset with a guarded STA adapter.

No COM imports, connections, saves or retries. Source evidence must come from
independent native property reads bound to file hashes. Complete native capture,
exact membership and exclusive ownership remain the adapter's responsibility.
"""

import re
from copy import deepcopy
from pathlib import PurePosixPath, PureWindowsPath

from .specification_refresh import (
    source_property_refresh_plan,
    verify_property_refresh,
    verify_source_refresh_progress,
)


def _absolute(value):
    return (type(value) is str and bool(value)
            and (PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()))


def plan_owned_source_refresh(state, bindings, row_uuids, source_evidence, property_ids,
                              group_summary, *, allow_property_value_refresh=False):
    """Detached dry-run plan for the empirically accepted direct style1 route.

    A nested target is rejected even if its source basename matches. A source
    proof is {exact_path: {sha256: hex64, values: {'4': str, '5': str}}}; matching
    source hashes later binds the independent read to the same saved revision.
    Local overrides and unproven owner/style contexts are never reset implicitly.
    """
    context = state['context']
    if (not _absolute(context.get('owner')) or not context.get('reference')
            or type(context.get('kind')) is not int or context['kind'] != 5
            or type(context.get('description_index')) is not int or context['description_index'] != 0
            or type(context.get('style')) is not int or context['style'] != 1
            or not context.get('layout') or type(context.get('source')) is not str):
        raise ValueError('Explicit saved assembly/description0/style1 context required')
    if (type(bindings) is not dict or set(bindings) != set(state['rows'])
            or type(row_uuids) is not list or not row_uuids
            or any(type(u) is not str or not u for u in row_uuids)
            or len(set(row_uuids)) != len(row_uuids) or not set(row_uuids) <= set(bindings)):
        raise ValueError('Complete exact UUID bindings and unique selected targets required')
    sources = {}
    for uuid in row_uuids:
        path = bindings[uuid]
        if type(path) is not list or len(path) != 1 or type(path[0]) is not int or path[0] < 0:
            raise ValueError('Nested occurrence context is not accepted; select its proven direct owner')
        row = state['rows'][uuid]
        if len(row['geometry']) != 1:
            raise ValueError('Exact singleton native membership required')
        geometry = row['geometry'][0]
        found = [n for n in state['top_tree'] if n.get('path') == path]
        if (len(found) != 1 or {k: v for k, v in found[0].items() if k != 'path'} != geometry
                or geometry.get('valid') is not True
                or not all(type(geometry.get(k)) is str and geometry[k]
                           for k in ['object_id', 'metadata_key', 'source'])
                or not _absolute(geometry['source'])):
            raise ValueError('Selected geometry does not match its exact direct occurrence')
        sources[uuid] = geometry['source']
    if type(source_evidence) is not dict or set(source_evidence) != set(sources.values()):
        raise ValueError('Independent exact source-path evidence required; no basename matching')
    for proof in source_evidence.values():
        if (type(proof) is not dict or set(proof) != {'sha256', 'values'}
                or type(proof['sha256']) is not str or not re.fullmatch('[a-f0-9]{64}', proof['sha256'])
                or type(proof['values']) is not dict or set(proof['values']) != {'4', '5'}
                or any(type(v) is not str for v in proof['values'].values())):
            raise ValueError('Independent source values4/5 and SHA256 required')
    if type(group_summary) is not dict or set(group_summary) != set(state['rows']):
        raise ValueError('Complete native per-UUID group summary required')
    values = {u: source_evidence[path]['values'] for u, path in sources.items()}
    batch = source_property_refresh_plan(state, row_uuids, values, property_ids,
                                         allow_property_value_refresh=allow_property_value_refresh)
    return deepcopy({'operation': 'direct_property_source_reset', 'context': context,
                     'bindings': bindings, 'source_evidence': source_evidence,
                     'group_summary': group_summary, 'batch': batch})


def refresh_owned_sources(plan, adapter, *, dry_run=True):
    """Default to guarded diagnostics; explicit execution returns UNSAVED evidence.

    Required adapter methods: guard_owned_context(context), capture_state(),
    source_evidence(), group_summary(), reset_source_property(uuid, property_id).
    The reset must implement the exact scoped VT_EMPTY/BaseUnit=False operation.
    It must not edit entire rows, change Geometry, rebuild or save. Failures retain
    partial RAM for explicit reconciliation; this helper never repairs or retries.
    """
    result = {'operation': 'direct_property_source_reset', 'status': 'failed', 'events': [],
              'saved': False, 'mutation_possible': False, 'retry_allowed': False,
              'native_acceptance': 'pending'}
    phase = 'preflight'
    try:
        if type(dry_run) is not bool or plan['operation'] != result['operation']:
            raise ValueError('Explicit dry-run policy and direct source-reset plan required')
        plan = deepcopy(plan)
        batch, context = plan['batch'], plan['context']
        # Revalidate externally supplied plans instead of trusting edited expected
        # snapshots, grouping waivers or a forged direct/nested route marker.
        rebuilt = plan_owned_source_refresh(batch['before'], plan['bindings'], batch['stale_rows'],
                                            plan['source_evidence'], batch['selected_properties'],
                                            plan['group_summary'],
                                            allow_property_value_refresh=bool(
                                                batch['declared_property_cache_changes']))
        if rebuilt != plan:
            raise ValueError('Source refresh plan was changed after preflight')
        required = ['guard_owned_context', 'capture_state', 'source_evidence', 'group_summary',
                    'reset_source_property']
        if any(not callable(getattr(adapter, name, None)) for name in required):
            raise TypeError('Incomplete guarded property-source adapter')

        def call(name, *args, mutates=False):
            nonlocal phase
            phase = 'guard_before_'+name
            adapter.guard_owned_context(deepcopy(context))
            phase = name
            if mutates:
                result['mutation_possible'] = True
            value = getattr(adapter, name)(*args)
            result['events'].append(name)
            return deepcopy(value)

        def sources():
            if call('source_evidence') != plan['source_evidence']:
                raise ValueError('Source revision/values changed since independent native read')

        sources()
        before = call('capture_state')
        if before['context'] != context:
            raise ValueError('Runtime owner/description context changed')
        verify_property_refresh(batch['before'], before)
        if call('group_summary') != plan['group_summary']:
            raise ValueError('Native grouping changed before mutation')
        result['before'] = before
        if dry_run:
            sources()
            result.update(status='ready_without_mutation', plan=plan)
            return result
        selected = sorted(batch['stale_rows'], key=lambda u: before['rows'][u]['is_first'], reverse=True)
        for uuid in selected:
            for pid in batch['selected_properties']:
                sources()
                verify_source_refresh_progress(batch, call('capture_state'))
                returned = call('reset_source_property', uuid, pid, mutates=True)
                result.setdefault('reset_returns', []).append(
                    {'row_uuid': uuid, 'property_id': pid, 'return': returned})
                if type(returned) is not bool or not returned:
                    raise ValueError('Source reset did not return native BOOL True')
                sources()
                result['after'] = call('capture_state')
                verify_source_refresh_progress(batch, result['after'])
        result['after'] = call('capture_state')
        verify_property_refresh(batch['expected_after'], result['after'])
        if call('group_summary') != plan['group_summary']:
            raise ValueError('Final native grouping/positions/quantities changed')
        sources()
        phase = 'final_ownership_guard'
        adapter.guard_owned_context(deepcopy(context))
        result.update(status='verified_unsaved', expected_after=batch['expected_after'])
    except Exception as exc:  # noqa: BLE001 - retain partial RAM, never retry/save/repair
        result.update(failed_phase=phase, error=f'{type(exc).__name__}: {exc}',
                      recovery='Reconcile only owned RAM before further native actions')
    return result
