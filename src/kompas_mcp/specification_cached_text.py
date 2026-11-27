"""Guarded API5 text authoring after source values AND display caches are current.

This is explicit text authoring on existing rows, not a properties resync. No
connections, native imports, save, retry or edit-context recovery are provided.
"""

import re
from copy import deepcopy
from math import isfinite
from pathlib import PurePosixPath, PureWindowsPath

from .specification_refresh import (
    source_property_refresh_plan,
    verify_property_refresh,
    verify_source_refresh_progress,
)


def plan_cached_text_refresh(state, row_uuids, source_evidence, property_ids, group_summary):
    """Require independently current sources/properties/caches before text-only writes."""
    ctx = state['context']
    absolute = lambda p: (type(p) is str and bool(p)
                          and (PurePosixPath(p).is_absolute() or PureWindowsPath(p).is_absolute()))
    if (not absolute(ctx.get('owner')) or not ctx.get('reference') or type(ctx.get('kind')) is not int
            or ctx['kind'] != 5 or type(ctx.get('description_index')) is not int
            or ctx['description_index'] != 0 or type(ctx.get('style')) is not int or ctx['style'] != 1
            or not ctx.get('layout') or type(ctx.get('source')) is not str):
        raise ValueError('Explicit saved owner/description0/style1 required')
    if (type(row_uuids) is not list or not row_uuids
            or any(type(u) is not str or not u for u in row_uuids)
            or len(set(row_uuids)) != len(row_uuids)):
        raise ValueError('Explicit unique existing UUIDs required')
    sources = {}
    for u in row_uuids:
        row = state['rows'][u]
        if len(row['geometry']) != 1:
            raise ValueError('Fresh exact singleton membership required')
        geometry = row['geometry'][0]
        if (geometry.get('valid') is not True or not all(
                type(geometry.get(k)) is str and geometry[k] for k in ['object_id', 'metadata_key'])
                or not absolute(geometry.get('source'))):
            raise ValueError('Persistent occurrence identity required')
        sources[u] = geometry['source']
    if type(source_evidence) is not dict or set(source_evidence) != set(sources.values()):
        raise ValueError('Independent exact source-path evidence required')
    for proof in source_evidence.values():
        if (type(proof) is not dict or set(proof) != {'sha256', 'values'}
                or type(proof['sha256']) is not str or not re.fullmatch('[a-f0-9]{64}', proof['sha256'])
                or type(proof['values']) is not dict or set(proof['values']) != {'4', '5'}
                or any(type(v) is not str for v in proof['values'].values())):
            raise ValueError('Independent native values4/5 and SHA256 required')
    if type(group_summary) is not dict or set(group_summary) != set(state['rows']):
        raise ValueError('Complete native per-UUID summary required')
    values = {u: source_evidence[p]['values'] for u, p in sources.items()}
    batch = source_property_refresh_plan(state, row_uuids, values, property_ids)
    text_only = deepcopy(state)
    for u in row_uuids:
        for c in property_ids:
            text_only['rows'][u]['columns'][str(c)] = batch['expected_after']['rows'][u]['columns'][str(c)]
    # The property oracle would also correct display caches. Reject if any such
    # correction is still necessary; API5 authoring here is only literal text.
    verify_property_refresh(text_only, batch['expected_after'])
    return deepcopy({'operation': 'cached_source_text_authoring', 'context': ctx,
                     'source_evidence': source_evidence, 'group_summary': group_summary, 'batch': batch})


def author_cached_text_owned(plan, adapter, *, dry_run=True):
    """Diagnose by default; explicit execution retains partial RAM on any failure.

    Adapter reads must capture all rows/properties/poses with fresh native exact
    membership. Every call is guarded against the pinned runtime context. Save
    and two independent reopenings belong to the caller, never to this helper.
    """
    result = {'operation': 'cached_source_text_authoring', 'status': 'failed', 'saved': False,
              'events': [], 'mutation_possible': False, 'edit_may_be_open': False,
              'retry_allowed': False, 'native_acceptance': 'pending'}
    phase = 'preflight'
    try:
        if type(dry_run) is not bool or plan['operation'] != result['operation']:
            raise ValueError('Explicit text-only plan and dry-run policy required')
        plan = deepcopy(plan)
        batch, ctx = plan['batch'], plan['context']
        if plan_cached_text_refresh(batch['before'], batch['stale_rows'], plan['source_evidence'],
                                    batch['selected_properties'], plan['group_summary']) != plan:
            raise ValueError('Text plan changed after preflight')
        required = ['guard_owned_context', 'capture_state', 'source_evidence', 'group_summary',
                    'row_number', 'pointer_for_number', 'number_for_pointer', 'get_column_text',
                    'edit', 'set_column_text', 'end']
        if any(not callable(getattr(adapter, name, None)) for name in required):
            raise TypeError('Incomplete guarded API5 text adapter')

        def call(name, *args, mutates=False):
            nonlocal phase
            phase = 'guard_before_'+name
            adapter.guard_owned_context(deepcopy(ctx))
            phase = name
            if mutates:
                result['mutation_possible'] = True
            value = getattr(adapter, name)(*args)
            result['events'].append(name)
            return deepcopy(value)

        def sources():
            if call('source_evidence') != plan['source_evidence']:
                raise ValueError('Saved source revision or values changed')

        def numeric(value):
            if type(value) not in {int, float} or not isfinite(value) or value <= 0:
                raise ValueError('Native UniqueNumber must be positive finite, not BOOL')
            return value

        def pointer(value):
            if type(value) is not int or value <= 0:
                raise ValueError('Native object pointer must be positive long, not BOOL')
            return value

        def long1(value):
            if type(value) is not int or value != 1:
                raise ValueError('API5 Edit/Set must return native long1')

        sources()
        before = call('capture_state')
        if before['context'] != ctx:
            raise ValueError('Runtime owner/description mismatch')
        verify_property_refresh(batch['before'], before)
        if call('group_summary') != plan['group_summary']:
            raise ValueError('Native grouping changed before editing')
        result['before'] = before
        if dry_run:
            sources()
            result.update(status='ready_without_mutation', plan=plan)
            return result
        targets = {p['row_uuid']: p for p in batch['plans']}
        for u in sorted(targets, key=lambda k: before['rows'][k]['is_first'], reverse=True):
            sources()
            verify_source_refresh_progress(batch, call('capture_state'))
            number = numeric(call('row_number', u))
            ptr = pointer(call('pointer_for_number', number))
            if numeric(call('number_for_pointer', ptr)) != number:
                raise ValueError('Existing UUID/numeric mapping mismatch')
            cells = targets[u]['cells']
            for c in cells:
                if call('get_column_text', ptr, c['column'], c['execution'], c['block']) != c['before']:
                    raise ValueError('Exact API5 text address differs from full snapshot')
            verify_source_refresh_progress(batch, call('capture_state'))
            result['edit_may_be_open'] = True
            record = {'row_uuid': u, 'number': number, 'Edit_return': call('edit', ptr, mutates=True)}
            result.setdefault('text_calls', []).append(record)
            long1(record['Edit_return'])
            record['Set_returns'] = []
            for c in cells:
                value = call('set_column_text', c['column'], c['execution'], c['block'],
                             c['after'], mutates=True)
                record['Set_returns'].append(value)
                long1(value)
            record['End_pointer'] = pointer(call('end', mutates=True))
            result['edit_may_be_open'] = False
            if numeric(call('number_for_pointer', record['End_pointer'])) != number:
                raise ValueError('End pointer numeric roundtrip failed')
            if numeric(call('row_number', u)) != number:
                raise ValueError('Existing UUID numeric identity drift')
            result['after'] = call('capture_state')
            verify_source_refresh_progress(batch, result['after'])
            sources()
        result['after'] = call('capture_state')
        verify_property_refresh(batch['expected_after'], result['after'])
        if call('group_summary') != plan['group_summary']:
            raise ValueError('Final native grouping/positions/quantity changed')
        sources()
        phase = 'final_ownership_guard'
        adapter.guard_owned_context(deepcopy(ctx))
        result.update(status='verified_unsaved', expected_after=batch['expected_after'])
    except Exception as exc:  # noqa: BLE001 - preserve partial text/edit context, never retry
        result.update(failed_phase=phase, error=f'{type(exc).__name__}: {exc}',
                      recovery='Reconcile only owned RAM and edit context before continuing')
    return result
