"""Detached oracle for stale plain text with already-current inherited properties.

Does not connect, mutate, infer native geometry membership or declare persistence.
The native adapter must independently prove exact owner/UUID/occurrence identity.
"""

from copy import deepcopy


def current_property_text_plan(state, row_uuids, *, restore_sync=False, expected_sync=True,
                               normalize_display_metadata=False):
    """Require actual stale cells and FromSource=True; preserve all other evidence.

    ``restore_sync=True`` explicitly permits False→True for selected rows as part
    of a controlled stale-fixture experiment. It is never an implicit fallback.
    All grouping/position/property/geometry/pose evidence remains frozen.
    ``normalize_display_metadata=True`` additionally declares the selected Name/
    Marking display caches as outputs equal to already-current property values;
    persistent object IDs, metadata keys, source paths and poses remain frozen.
    """
    before = deepcopy(state)
    if (not isinstance(row_uuids, list) or not row_uuids
            or any(not isinstance(u, str) or not u.strip() for u in row_uuids)
            or len(set(row_uuids)) != len(row_uuids) or type(restore_sync) is not bool
            or type(expected_sync) is not bool or type(normalize_display_metadata) is not bool):
        raise ValueError('Explicit unique selected row UUIDs and transition policy required')
    expected, plans = deepcopy(before), []
    for uuid in row_uuids:
        row, props = before['rows'][uuid], before['properties'][uuid]
        if (type(row['state']) is not int or row['state'] != 0
                or row['edit_source'] is not False or type(row['sync']) is not bool
                or (not restore_sync and row['sync'] is not expected_sync)
                or len(row['geometry']) != 1):
            raise ValueError('Require independent existing singleton row and explicit sync policy')
        cells = []
        for column in [4, 5]:
            text, prop = row['columns'][str(column)], props[str(column)]
            if type(text) is not str or type(prop['value']) is not str or prop['from_source'] is not True:
                raise ValueError('Current native property must have string value and FromSource=True')
            if text != prop['value']:
                cells.append({'column': column, 'execution': 1, 'block': 0,
                              'before': text, 'after': prop['value']})
                expected['rows'][uuid]['columns'][str(column)] = prop['value']
        if not cells:
            raise ValueError('Selected row is already current; stale text was not reproduced')
        expected['rows'][uuid]['sync'] = True if restore_sync else expected_sync
        if normalize_display_metadata:
            # These are display caches of the very properties being refreshed,
            # not occurrence identity. Never discard IDs or match by basename.
            geometry = row['geometry'][0]
            identity = {key: geometry[key] for key in ['object_id', 'metadata_key', 'source']}
            if any(not isinstance(v, str) or not v for v in identity.values()):
                raise ValueError('Exact persistent occurrence identity required for display refresh')
            cache = {'name': props['5']['value'], 'marking': props['4']['value']}
            expected['rows'][uuid]['geometry'][0].update(cache)
            for tree in ['top_tree', 'main_tree']:
                found = [node for node in expected[tree]
                         if all(node.get(key) == value for key, value in identity.items())]
                if len(found) != 1:
                    raise ValueError('Display refresh occurrence must be exact singleton in each tree')
                found[0].update(cache)
        plans.append({'row_uuid': uuid, 'expected_context': deepcopy(before['context']),
                      'expected_sync': expected['rows'][uuid]['sync'], 'cells': cells})
    return {'plans': plans, 'expected_after': expected, 'stale_rows': list(row_uuids),
            'restore_sync': restore_sync, 'stale_text_observed': True,
            'normalize_display_metadata': normalize_display_metadata,
            'saved_acceptance': False}


def verify_property_refresh(expected, actual):
    """Compare the entire detached oracle, ignoring only document runtime Reference.

    Geometry references may be detached only AFTER a native exact fresh singleton
    check. Callers must not remove object IDs, metadata, poses or FromSource.
    """
    previous, current = deepcopy(expected), deepcopy(actual)
    previous['context'].pop('reference')
    current['context'].pop('reference')
    if previous != current:
        raise ValueError('Refresh changed UUID/membership/position/grouping/properties/poses or other payload')


def source_property_refresh_plan(state, row_uuids, source_values, property_ids, *,
                                 allow_property_value_refresh=False):
    """Declare selected property/source-cache changes before a native reset batch.

    Source values must be read and SHA-pinned independently by the caller. By
    default owner values must already match them. Explicit cache refresh permits
    ONLY the selected property values to become current; FromSource stays True.
    Final grouping and positions are never relaxed by this plan.
    """
    if (not isinstance(property_ids, list) or not property_ids
            or any(type(p) is not int or p not in {4, 5} for p in property_ids)
            or len(set(property_ids)) != len(property_ids)
            or type(allow_property_value_refresh) is not bool
            or not isinstance(row_uuids, list) or not row_uuids
            or len(set(row_uuids)) != len(row_uuids)
            or set(source_values) != set(row_uuids)):
        raise ValueError('Explicit unique targets, property IDs and exact source-value mapping required')
    desired = deepcopy(state)
    changes = []
    for uuid in row_uuids:
        for c in ['4', '5']:
            prop, wanted = state['properties'][uuid][c], source_values[uuid][c]
            if prop['from_source'] is not True or type(wanted) is not str:
                raise ValueError('Source refresh requires inherited properties and native string source values')
            if prop['value'] != wanted:
                if int(c) not in property_ids or not allow_property_value_refresh:
                    raise ValueError('Owner property is not independently current; cache change not declared')
                desired['properties'][uuid][c]['value'] = wanted
                changes.append({'row_uuid': uuid, 'property_id': int(c),
                                'before': prop['value'], 'after': wanted})
    result = current_property_text_plan(desired, row_uuids, normalize_display_metadata=True)
    if any(cell['column'] not in property_ids for plan in result['plans'] for cell in plan['cells']):
        raise ValueError('Stale cells outside the declared property batch')
    result.update(selected_properties=list(property_ids), source_values=deepcopy(source_values),
                  declared_property_cache_changes=changes, before=deepcopy(state))
    return result


def verify_source_refresh_progress(plan, actual):
    """Bounded intermediate batch gate; strict final equality remains mandatory.

    Native regrouping may temporarily change selected Draw/IsFirst/position
    while peers are updated. All IDs, membership, poses, inheritance, controls and
    undeclared fields stay exact. This is NOT a final acceptance predicate.
    """
    before, final = plan['before'], plan['expected_after']
    candidate = deepcopy(before)
    selected = plan['stale_rows']

    def allow(parent, current, old, new, key):
        if current[key] not in [old[key], new[key]]:
            raise ValueError('Undeclared intermediate value: '+key)
        parent[key] = deepcopy(current[key])

    for uuid in selected:
        previous, wanted, current = before['rows'][uuid], final['rows'][uuid], actual['rows'][uuid]
        for c in plan['selected_properties']:
            key = str(c)
            allow(candidate['rows'][uuid]['columns'], current['columns'],
                  previous['columns'], wanted['columns'], key)
            allow(candidate['properties'][uuid][key], actual['properties'][uuid][key],
                  before['properties'][uuid][key], final['properties'][uuid][key], 'value')
        if len(selected) > 1:
            for flag in ['draw', 'is_first']:
                if type(current[flag]) is not bool:
                    raise ValueError('Intermediate grouping flag is not BOOL')
                candidate['rows'][uuid][flag] = current[flag]
            if type(current['columns']['3']) is not str:
                raise ValueError('Intermediate position is not native text')
            candidate['rows'][uuid]['columns']['3'] = current['columns']['3']
        for key in ['name', 'marking']:
            allow(candidate['rows'][uuid]['geometry'][0], current['geometry'][0],
                  previous['geometry'][0], wanted['geometry'][0], key)
        geometry = previous['geometry'][0]
        identity = {k: geometry[k] for k in ['object_id', 'metadata_key', 'source']}
        for tree in ['top_tree', 'main_tree']:
            matches = [i for i, node in enumerate(before[tree])
                       if all(node.get(k) == v for k, v in identity.items())]
            if len(matches) != 1:
                raise ValueError('Intermediate occurrence identity is ambiguous')
            i = matches[0]
            for key in ['name', 'marking']:
                allow(candidate[tree][i], actual[tree][i], before[tree][i], final[tree][i], key)
    verify_property_refresh(candidate, actual)
