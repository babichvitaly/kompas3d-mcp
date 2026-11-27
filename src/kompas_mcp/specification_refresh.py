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
