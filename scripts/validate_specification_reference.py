"""Owned synthetic model-SP identity investigation; never opens engineering inputs.

Requires an explicit fresh handover and isolated root. One STA worker. Evidence
of a failed gate is retained; no failed mutation is silently repeated or saved.
"""

import argparse
import inspect
import json
import math
import time
import traceback
from pathlib import Path

from native_owned_session import NativeOwnedSession, key, need, sha


def values(value):
    return [] if value is None else list(value) if isinstance(value, (tuple, list)) else [value]


def strict_bool(value, label):
    need(type(value) is bool, label+' did not return BOOL')
    need(value, label+' returned False')
    return value


def top(session, document, main=False):
    doc = session.doc(document)
    return (session.cast(doc, 'IKompasDocument3D1').MainTopPart if main
            else session.cast(doc, 'IKompasDocument3D').TopPart)


def occurrence(session, document, path, main=False):
    obj = top(session, document, main)
    for index in path:
        need(0 <= index < obj.Parts.Count, 'Missing explicit synthetic occurrence')
        obj = obj.Parts.Part(index)
    return session.cast(obj, 'IPart7')


def description(session, document):
    descriptions = session.doc(document).SpecificationDescriptions
    need(descriptions.Count == 1, 'Expected one explicit synthetic SP description')
    return descriptions.Item(0)


def part_identity(session, document, obj):
    part = session.cast(obj, 'IPart7')
    model = session.cast(obj, 'IModelObject')
    api = session.cast(obj, 'IKompasAPIObject')
    keeper = session.cast(obj, 'IPropertyKeeper')
    doc1 = session.cast(session.doc(document), 'IKompasDocument1')
    object_id = str(doc1.GetObjectId(api, None))
    found = doc1.FindObjectById(object_id, None) if object_id else None
    return {'raw_class': type(obj).__name__, 'raw_reference': str(obj.Reference),
            'part_reference': str(part.Reference), 'model_reference': str(model.Reference),
            'api_reference': str(api.Reference), 'valid': bool(part.Valid),
            'metadata_key': str(keeper.UniqueMetaObjectKey), 'object_id': object_id,
            'roundtrip_reference': None if found is None else str(
                session.cast(found, 'IModelObject').Reference),
            'source': str(part.FileName), 'name': str(part.Name), 'marking': str(part.Marking),
            'matrix': list(part.Placement.GetMatrix3D()),
            'fixed': bool(part.Fixed), 'hidden': bool(part.Hidden)}


def tree(session, document, main):
    result = []

    def walk(obj, path):
        need(len(path) <= 6 and len(result) < 50, 'Synthetic traversal exceeded bounds')
        result.append({'path': list(path), **part_identity(session, document, obj)})
        for i in range(obj.Parts.Count):
            walk(obj.Parts.Part(i), (*path, i))

    walk(top(session, document, main), ())
    return result


def snapshot(session, document):
    session.guard()
    doc = session.doc(document)
    desc = description(session, document)
    top_tree, main_tree = tree(session, document, False), tree(session, document, True)
    need(desc.BaseObjects.Count <= 100, 'Too many synthetic model-SP rows')
    rows = []
    for i in range(desc.BaseObjects.Count):
        row = desc.BaseObjects.Item(i)
        need(row.Columns.Count <= 30, 'Too many synthetic columns')
        columns = [{'type': int(c.ColumnType), 'text': str(c.Text.Str)}
                   for j in range(row.Columns.Count) if (c := row.Columns.Item(j)) is not None]
        geom = [part_identity(session, document, obj) for obj in values(row.Geometry)]
        rows.append({'uuid': str(row.UniqueMetaObjectKey), 'section': int(row.Section),
                     'state': int(row.State), 'draw': bool(row.Draw),
                     'is_first': bool(row.IsFirstObject), 'sync': bool(row.SyncronizeWithProperties),
                     'edit_source': bool(row.EditSourceObject), 'columns': columns, 'geometry': geom})
    edit = session.cast(doc, 'IKompasDocument3D1').EditObject
    result = {'document_path': str(doc.PathName), 'changed': bool(doc.Changed),
              'delegate': bool(desc.DelegateMode), 'need_rebuild': bool(desc.NeedRebuild),
              'edit_object_reference': None if edit is None else str(edit.Reference),
              'top_tree': top_tree, 'main_tree': main_tree, 'rows': rows}
    session.guard()
    return result


def identify_rows(snap, paths):
    targets = {tuple(item['path']): item for item in snap['top_tree']}
    result = {}
    for path in paths:
        target = targets[tuple(path)]
        found = [r for r in snap['rows'] if len(r['geometry']) == 1
                 and r['geometry'][0]['model_reference'] == target['model_reference']]
        need(len(found) == 1, 'No exact singleton row for target '+str(path))
        result[found[0]['uuid']] = list(path)
    return result


def native_files(folder):
    return {str(p): sha(p) for p in sorted(folder.rglob('*'))
            if p.is_file() and p.suffix.lower() in {'.m3d', '.a3d'}}


def property_values(session, document, path):
    part = occurrence(session, document, path)
    keeper = session.cast(part, 'IPropertyKeeper')
    manager = session.cast(session.app, 'IPropertyMng')
    result = {}
    for pid in [4, 5]:
        prop = manager.GetProperty(session.doc(document), float(pid))
        need(prop is not None and float(prop.Id) == pid, 'Wrong native property identity')
        raw = list(keeper.GetPropertyValue(prop, None, False, False))
        need(len(raw) == 3 and raw[0] is True and type(raw[2]) is bool,
             'Native property getter did not confirm value/source state')
        result[str(pid)] = {'value': str(raw[1]), 'from_source': raw[2]}
    return result


def new_assembly(session, folder, name, marking, sources, reveal=False, freeze_positions=False):
    from kompas_mcp import documents

    result = session.create('assembly')
    root = top(session, result)
    root.Name, root.Marking = name, marking
    strict_bool(root.Update(), 'new assembly properties')
    session.save(result, folder/(marking+'.a3d'))
    for i, source in enumerate(sources):
        session.call(documents.insert_component, session.k, result['document']['handle'],
                     str(source), linked=True)
        part = occurrence(session, result, [i])
        part.CreateSpcObjects = True
        part.RevealComposition = reveal
        part.Fixed = True
        strict_bool(part.Update(), 'inserted synthetic component properties')
    if session.doc(result).SpecificationDescriptions.Count == 0:
        added = session.doc(result).SpecificationDescriptions.Add('', 0, '')
        need(added is not None, 'Default model-SP description unavailable')
    if freeze_positions:
        from kompas_mcp.drawings import _messages_no

        tune = description(session, result).SpecificationTuning
        # The observed setup asked whether to clear positions. A negative answer
        # returned False: keep that failure, never clear numbers or hide the BOOL.
        with _messages_no(session.k):
            tune.CalculatePosition = False
            strict_bool(tune.Update(), 'disable synthetic automatic position recalculation')
    session.save(result, folder/(marking+'.a3d'))
    return result


def build_fixture(session, folder, event, freeze_positions=False):
    from kompas_mcp.models import ExtrusionSpec, SketchSpec

    need(not folder.exists(), 'Do not reuse a synthetic fixture baseline')
    folder.mkdir(parents=True)
    paths = []
    for suffix, width in [('A', 20.), ('B', 26.)]:
        result = session.create('part')
        sk = session.call(session.k.sketch, result['document_id'], SketchSpec(
            name='Synthetic rectangle', curves=[{'kind': 'polyline',
                'points': [[0., 0.], [width, 0.], [width, 10.], [0., 10.]]}]))
        session.call(session.k.feature, result['document_id'], ExtrusionSpec(
            name='Synthetic prism', sketch_id=sk['sketch_id'], depth=4.))
        measure = session.call(session.k.measure, result['document_id'])
        need(math.isclose(measure['volume_mm3'], width*10*4, abs_tol=1e-5), 'Wrong prism volume')
        part = top(session, result)
        part.Name, part.Marking = 'Synthetic leaf '+suffix, 'SYNTH-LEAF-'+suffix
        strict_bool(part.Update(), 'synthetic source properties')
        path = folder/('leaf-'+suffix+'.m3d')
        session.save(result, path)
        session.close(result)
        source = new_assembly(session, folder, 'Synthetic source '+suffix,
                              'SYNTH-SOURCE-'+suffix, [path], freeze_positions=freeze_positions)
        paths.append(Path(session.doc(source).PathName))
        session.close(source)
        event('source_created', variant=suffix, measured_volume=measure['volume_mm3'])
    product = new_assembly(session, folder, 'Synthetic product', 'SYNTH-PRODUCT', [paths[0]]*2,
                           freeze_positions=freeze_positions)
    product_path = Path(session.doc(product).PathName)
    session.close(product)
    owner = new_assembly(session, folder, 'Synthetic owner', 'SYNTH-OWNER', [product_path], reveal=True,
                         freeze_positions=freeze_positions)
    return owner, paths[1], [[0, 0], [0, 1]]


def run_case(session, phase, report, event):
    folder = session.root/phase
    owner, donor, target_paths = build_fixture(session, folder, event, phase == 'direct_frozen')
    report['calculate_position'] = bool(description(session, owner).SpecificationTuning.CalculatePosition)
    initial = snapshot(session, owner)
    report['initial'] = initial
    event('synthetic_fixture_built', rows=len(initial['rows']))
    targets = identify_rows(initial, target_paths)
    report['target_uuids'] = targets
    owner_path = Path(session.doc(owner).PathName)
    report['baseline_files'] = native_files(folder)
    session.close(owner)
    owner = session.open(owner_path, read_only=True)
    baseline = snapshot(session, owner)
    report['baseline_saved_ro'] = baseline
    need(set(targets) <= {r['uuid'] for r in baseline['rows']}, 'Baseline row UUID lost on RO')
    identify_rows(baseline, target_paths)
    session.close(owner)
    if phase == 'fixture':
        return
    need(phase in {'same_geometry', 'direct_only', 'direct_frozen'},
         'Unknown explicit synthetic case')
    owner = session.open(owner_path)
    report['baseline_volume'] = session.call(session.k.measure, owner['document_id'])['volume_mm3']
    for path in target_paths:
        part = occurrence(session, owner, path)
        need(key(part.FileName) != key(donor), 'Replacement is not old to new')
        part.FileName = str(donor)
        strict_bool(part.Update(), 'synthetic source replacement')
    desc = description(session, owner)
    report['immediate_source_columns'] = [
        {'uuid': str(r.UniqueMetaObjectKey), 'columns': [
            {'type': int(c.ColumnType), 'text': str(c.Text.Str)}
            for j in range(r.Columns.Count) if (c := r.Columns.Item(j)) is not None]}
        for i in range(desc.BaseObjects.Count) if (r := desc.BaseObjects.Item(i)) is not None]
    moved = snapshot(session, owner)
    report['after_source_replacement'] = moved
    event('source_replacement_observed')
    need(identify_rows(moved, target_paths) == targets, 'Source replacement changed exact row binding')
    report['replacement_volume'] = session.call(session.k.measure, owner['document_id'])['volume_mm3']
    need(math.isclose(report['replacement_volume']/report['baseline_volume'], 26/20,
                      abs_tol=1e-8), 'Source replacement geometry did not change to donor')
    for uuid, path in (targets.items() if phase not in {'direct_only', 'direct_frozen'} else []):
        row = next(description(session, owner).BaseObjects.Item(i)
                   for i in range(description(session, owner).BaseObjects.Count)
                   if str(description(session, owner).BaseObjects.Item(i).UniqueMetaObjectKey) == uuid)
        geom = values(row.Geometry)
        need(len(geom) == 1, 'Target geometry is not singleton')
        report.setdefault('updates', []).append({'uuid': uuid, 'sync_before': bool(
            row.SyncronizeWithProperties), 'strategy': phase})
        need(row.SyncronizeWithProperties is True, 'Expected automatic synchronization')
        row.Geometry = geom[0]
        returned = row.Update()
        report['updates'][-1]['return'] = returned
        strict_bool(returned, 'synthetic row update')
        event('row_updated', uuid=uuid)
    after = snapshot(session, owner)
    report['after_refresh'] = after
    new_targets = identify_rows(after, target_paths)
    need(new_targets == targets, 'Exact Geometry/UUID target mapping changed')
    accept_case(session, owner, baseline, after, targets, report, folder, owner_path, event)


def accept_case(session, owner, baseline, after, targets, report, folder, owner_path, event):
    before_by_uuid = {r['uuid']: r for r in baseline['rows']}
    after_by_uuid = {r['uuid']: r for r in after['rows']}
    need(before_by_uuid.keys() == after_by_uuid.keys(), 'SP row UUID set changed')
    for uuid, previous in before_by_uuid.items():
        current = after_by_uuid[uuid]
        if uuid not in targets:
            need(current == previous, 'Non-target row changed')
        else:
            need([{**c} for c in current['columns'] if c['type'] not in {4, 5}] ==
                 [{**c} for c in previous['columns'] if c['type'] not in {4, 5}],
                 'Other target column text changed')
            for field in ['section', 'state', 'draw', 'is_first', 'sync', 'edit_source']:
                need(current[field] == previous[field], 'Target row flag changed: '+field)
            wanted = property_values(session, owner, targets[uuid])
            report.setdefault('target_properties', {})[uuid] = wanted
            text = {c['type']: c['text'] for c in current['columns']}
            need(text[4] == wanted['4']['value'] == 'SYNTH-SOURCE-B'
                 and text[5] == wanted['5']['value'] == 'Synthetic source B', 'Stale target text')
            need(all(x['from_source'] for x in wanted.values()), 'Target property inheritance changed')
    report['saved'] = session.save(owner, owner_path)
    report['after_saved_files'] = native_files(folder)
    changed = {key(p) for p, h in report['baseline_files'].items()
               if report['after_saved_files'].get(p) != h}
    allowed = {key(owner_path)}
    if report['case'] == 'direct_frozen':
        allowed.add(key(owner_path.with_name('SYNTH-PRODUCT.a3d')))
    report['saved_closure_changes'] = sorted(changed)
    need(changed == allowed and report['baseline_files'].keys() == report['after_saved_files'].keys(),
         'Native save changed files outside the explicit owner/subassembly writeback set')
    session.close(owner)
    for cycle in range(2):
        owner = session.open(owner_path, read_only=True)
        saved = snapshot(session, owner)
        report.setdefault('saved_ro', []).append(saved)
        volume = session.call(session.k.measure, owner['document_id'])['volume_mm3']
        report.setdefault('saved_ro_volumes', []).append(volume)
        need(math.isclose(volume, report['replacement_volume'], abs_tol=1e-5), 'Saved geometry mismatch')
        need(identify_rows(saved, list(targets.values())) == targets, 'Saved exact Geometry/UUID mismatch')
        need({r['uuid']: r['columns'] for r in saved['rows']} ==
             {r['uuid']: r['columns'] for r in after['rows']}, 'Saved SP text mismatch')
        for row in saved['rows']:
            previous = before_by_uuid[row['uuid']]
            for field in ['section', 'state', 'draw', 'is_first', 'sync', 'edit_source']:
                need(row[field] == previous[field], 'Saved row flag changed: '+field)
            for field in ['metadata_key', 'object_id', 'matrix', 'fixed', 'hidden']:
                need(row['geometry'][0][field] == previous['geometry'][0][field],
                     'Saved occurrence identity/pose changed: '+field)
        need({uuid: property_values(session, owner, path) for uuid, path in targets.items()} ==
             report['target_properties'], 'Saved native properties changed')
        session.close(owner)
        need(native_files(folder) == report['after_saved_files'], 'RO changed native files')
        event('saved_ro_checked', cycle=cycle+1)
    report['acceptance'] = 'synthetic_direct_replacement_SP_UUID_membership_saved_verified'
    report['production_stale_text_reproduced'] = False


def verify_saved_direct(session, config, report, event):
    prior = json.loads(Path(config['cleanup_from_receipt']).read_text(encoding='utf-8-sig'))
    original = json.loads(Path(config['direct_original_receipt']).read_text(encoding='utf-8-sig'))
    need(prior['case'] == 'finalize_direct' and prior.get('saved')
         and len(session.owned) == 1, 'Expected only the explicitly saved direct-only remainder')
    owner_path = Path(prior['saved']['path'])
    need(sha(owner_path) == prior['saved']['sha256'], 'Saved own owner changed since failure')
    changed = {key(p) for p, h in prior['baseline_files'].items()
               if prior['after_saved_files'].get(p) != h}
    expected_changed = {key(owner_path), key(owner_path.with_name('SYNTH-PRODUCT.a3d'))}
    need(changed == expected_changed, 'Unexpected saved closure writeback')
    need(native_files(owner_path.parent) == prior['after_saved_files'], 'Saved native files drifted')
    report.update(saved_closure_changes=sorted(changed),
                  owner_only_writeback=False,
                  reconciled_receipt_sha256=config['cleanup_receipt_sha256'],
                  raw_original_phase=original['phase'], raw_save_phase=prior['phase'],
                  target_uuids=original['target_uuids'])
    for entry in list(session.owned.values()):
        session.close(entry['result'])
    event('exact_saved_RAM_remainder_closed_without_save')
    expected_rows = {r['uuid']: r for r in original['baseline_saved_ro']['rows']}
    for cycle in range(2):
        owner = session.open(owner_path, read_only=True)
        snap = snapshot(session, owner)
        report.setdefault('saved_ro', []).append(snap)
        targets = identify_rows(snap, list(original['target_uuids'].values()))
        need(targets == original['target_uuids'], 'Saved target UUID/membership changed')
        need(set(expected_rows) == {r['uuid'] for r in snap['rows']}, 'Saved SP row set changed')
        for row in snap['rows']:
            previous = expected_rows[row['uuid']]
            props = property_values(session, owner, targets[row['uuid']])
            text = {c['type']: c['text'] for c in row['columns']}
            need(text[4] == props['4']['value'] == 'SYNTH-SOURCE-B'
                 and text[5] == props['5']['value'] == 'Synthetic source B'
                 and all(x['from_source'] for x in props.values()), 'Saved properties/text mismatch')
            need([c for c in row['columns'] if c['type'] not in {4, 5}] ==
                 [c for c in previous['columns'] if c['type'] not in {4, 5}],
                 'Other saved column changed')
            for field in ['section', 'state', 'draw', 'is_first', 'sync', 'edit_source']:
                need(row[field] == previous[field], 'Saved row flag changed: '+field)
            for field in ['metadata_key', 'object_id', 'matrix', 'fixed', 'hidden']:
                need(row['geometry'][0][field] == previous['geometry'][0][field],
                     'Saved occurrence identity/pose changed: '+field)
        volume = session.call(session.k.measure, owner['document_id'])['volume_mm3']
        report.setdefault('volumes', []).append(volume)
        need(math.isclose(volume, original['replacement_volume'], abs_tol=1e-5), 'Saved volume changed')
        session.close(owner)
        need(native_files(owner_path.parent) == prior['after_saved_files'], 'RO changed disk files')
        event('independent_saved_RO_verified', cycle=cycle+1)
    report['acceptance'] = 'synthetic_direct_replacement_SP_UUID_membership_saved_verified'
    report['production_stale_text_reproduced'] = False


def audit_direct(session, config, report, event):
    """Independent read-only dimensional audit; does not relabel failed full-payload gates."""
    original = json.loads(Path(config['direct_original_receipt']).read_text(encoding='utf-8-sig'))
    saved = json.loads(Path(config['direct_saved_receipt']).read_text(encoding='utf-8-sig'))
    path = Path(saved['saved']['path'])
    need(native_files(path.parent) == saved['after_saved_files'], 'Saved own closure changed')
    baseline = {r['uuid']: r for r in original['baseline_saved_ro']['rows']}
    targets = original['target_uuids']
    report.update(original_phase=original['phase'], saved_phase=saved['phase'],
                  full_payload_preservation=False, saved_ro=[], payload_changes=[])
    for cycle in range(2):
        owner = session.open(path, read_only=True)
        snap = snapshot(session, owner)
        report['saved_ro'].append(snap)
        need(identify_rows(snap, list(targets.values())) == targets, 'Saved UUID/membership mismatch')
        need(set(baseline) == {r['uuid'] for r in snap['rows']}, 'Saved SP row set changed')
        changes = []
        for row in snap['rows']:
            previous = baseline[row['uuid']]
            props = property_values(session, owner, targets[row['uuid']])
            text = {c['type']: c['text'] for c in row['columns']}
            need(text[4] == props['4']['value'] == 'SYNTH-SOURCE-B'
                 and text[5] == props['5']['value'] == 'Synthetic source B'
                 and all(x['from_source'] for x in props.values()), 'Saved properties/text mismatch')
            for field in ['section', 'state', 'draw', 'is_first', 'sync', 'edit_source']:
                need(row[field] == previous[field], 'Saved row flag changed: '+field)
            for field in ['metadata_key', 'object_id', 'matrix', 'fixed', 'hidden']:
                need(row['geometry'][0][field] == previous['geometry'][0][field],
                     'Saved occurrence identity/pose changed: '+field)
            before = {c['type']: c['text'] for c in previous['columns']}
            delta = {str(t): [before[t], text[t]] for t in before if before[t] != text[t]}
            need(set(delta) <= {'3', '4', '5'}, 'Unclassified saved column change')
            changes.append({'uuid': row['uuid'], 'columns': delta})
        report['payload_changes'].append(changes)
        volume = session.call(session.k.measure, owner['document_id'])['volume_mm3']
        need(math.isclose(volume, original['replacement_volume'], abs_tol=1e-5), 'Saved volume mismatch')
        report.setdefault('volumes', []).append(volume)
        session.close(owner)
        need(native_files(path.parent) == saved['after_saved_files'], 'RO changed own disk files')
        event('saved_uuid_geometry_properties_verified', cycle=cycle+1)
    copy = Path(config['receipts'])/'native-copy'
    need(not copy.exists(), 'Do not overwrite own artifact evidence')
    import shutil

    shutil.copytree(session.root, copy)
    expected = native_files(session.root)
    need({str(Path(p).relative_to(session.root)): h for p, h in expected.items()} ==
         {str(Path(p).relative_to(copy)): h for p, h in native_files(copy).items()},
         'Copied own native artifacts differ')
    report.update(uuid_membership_properties_geometry_verified=True,
                  position_preservation=False, production_stale_text_reproduced=False,
                  saved_closure_changes=saved['after_saved_files'], copied_native_files=len(expected))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--phase', required=True,
                        choices=['fixture', 'same_geometry',
                                 'direct_only', 'direct_frozen', 'cleanup', 'cleanup_direct',
                                 'cleanup_frozen', 'finalize_direct', 'verify_direct', 'audit_direct'])
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
    output = Path(config['receipts'])/(args.phase+'.json')
    need(not output.exists(), 'Existing receipt; reconcile, do not replay')
    report = {'phase': 'starting', 'case': args.phase, 'events': [], 'saved': False,
              'runner_sha256': sha(__file__)}
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
        session = NativeOwnedSession(config, config.get('cleanup_ledger')
                                     if args.phase in {'cleanup', 'cleanup_direct', 'cleanup_frozen',
                                                       'finalize_direct', 'verify_direct'}
                                     else None)
        report['application'], report['baseline'] = session.identity, list(session.baseline.values())
        report['installed_signatures'] = {name: str(inspect.signature(getattr(
            session.k.modules['kAPI7'].ISpecificationDescriptions, name))) for name in ['Add']}
        session.root.mkdir(exist_ok=True)
        event('fresh_session_ready')
        if args.phase.startswith('cleanup'):
            for entry in list(session.owned.values())[::-1]:
                session.close(entry['result'])
            event('exact_owned_remnants_closed')
        elif args.phase == 'verify_direct':
            verify_saved_direct(session, config, report, event)
        elif args.phase == 'audit_direct':
            audit_direct(session, config, report, event)
        elif args.phase == 'finalize_direct':
            prior = json.loads(Path(config['cleanup_from_receipt']).read_text(encoding='utf-8-sig'))
            need(prior['case'] == 'direct_only' and not prior.get('updates')
                 and prior['saved'] is False and len(session.owned) == 1,
                 'Only reconcile the source-replaced direct-only document without row mutations')
            owner = next(iter(session.owned.values()))['result']
            current = snapshot(session, owner)
            report.update(reconciled_receipt_sha256=config['cleanup_receipt_sha256'],
                          reconciliation='Compare text with native properties, not IPart7 tree Name',
                          after_refresh=current, baseline_files=prior['baseline_files'],
                          replacement_volume=prior['replacement_volume'],
                          target_uuids=prior['target_uuids'])
            need(identify_rows(current, list(prior['target_uuids'].values())) == prior['target_uuids'],
                 'Reconciled exact target membership changed')
            need({r['uuid']: r['columns'] for r in current['rows']} ==
                 {r['uuid']: r['columns'] for r in prior['after_refresh']['rows']},
                 'Reconciled text changed since the failed oracle')
            event('exact_direct_only_reconciliation_read')
            owner_path = Path(session.doc(owner).PathName)
            accept_case(session, owner, prior['baseline_saved_ro'], current, prior['target_uuids'],
                        report, owner_path.parent, owner_path, event)
        else:
            run_case(session, args.phase, report, event)
        report['phase'] = 'complete'
    except Exception:  # noqa: BLE001 - retain partial native evidence; never replay mutation
        report.update(phase='failed', error=traceback.format_exc())
    finally:
        if session is not None:
            report['owned_remaining'] = [{'reference': ref, **{
                k: v for k, v in e.items() if k != 'result'}} for ref, e in session.owned.items()]
            try:
                report['final_guard'] = session.guard()
                report['preservation'] = session.verify_files()
            except Exception:  # noqa: BLE001 - no cleanup when ownership is uncertain
                report['preservation_error'] = traceback.format_exc()
            session.release()
        flush()
        terminal = Path(config['receipts'])/(args.phase+'-terminal.json')
        need(not terminal.exists(), 'Existing terminal receipt')
        terminal.write_text(json.dumps({'phase': report['phase'], 'report': str(output),
            'verification': {'artifacts': 'not_verified', 'physical_acceptance': 'pending'}},
            indent=2), encoding='utf-8')
    return int(report['phase'] == 'failed')


if __name__ == '__main__':
    raise SystemExit(main())
