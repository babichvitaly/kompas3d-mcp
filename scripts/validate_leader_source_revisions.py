"""Explicitly authorized native synthetic leader source-revision acceptance.

Requires an external handover/configuration; never starts CAD, installs SDK,
touches product geometry or rebuilds all documents. No implicit retries.
"""

import argparse
import json
import math
import shutil
import time
import traceback
from pathlib import Path

from native_owned_session import NativeOwnedSession, key, need, sha


def values(value):
    return [] if value is None else list(value) if isinstance(value, (tuple, list)) else [value]


def view(session, drawing, number):
    views = session.cast(session.doc(drawing), 'IKompasDocument2D').ViewsAndLayersManager.Views
    native = views.ViewByNumber(number)
    need(native is not None and native.Valid and number > 0, 'Missing own associative view')
    return native, session.cast(native, 'IAssociationView')


def component(session, model, part_path):
    root = session.cast(session.doc(model), 'IKompasDocument3D').TopPart
    need(root.Parts.Count == 1, 'Synthetic source must contain exactly one inserted component')
    part = root.Parts.Part(0)
    need(part.Valid and key(part.FileName) == key(part_path), 'Wrong synthetic inserted component')
    return part


def projected_bottom(session, drawing, model, number, part_path):
    v, av = view(session, drawing, number)
    need(key(av.SourceFileName) == key(session.doc(model).PathName), 'View/source model mismatch')
    part = component(session, model, part_path)
    raw = values(av.AssociationObjects(part))  # inserted component only, never MainTopPart
    need(0 < len(raw) <= 100, 'Unexpected projection size for a synthetic rectangular plate')
    candidates, seen = [], set()
    for item in raw:
        base = session.cast(item, 'IDrawingObject')
        reference = str(base.Reference)
        if reference in seen:
            continue
        seen.add(reference)
        extra = session.cast(base, 'IDrawingObject1')
        if not (base.Valid and not base.Temp and extra.IsVisibleInAssociationView
                and extra.IsInAssociationView and extra.IsGeometryObject and extra.IsCurve):
            continue
        need(str(extra.GetView().Reference) == str(v.Reference), 'Foreign curve view owner')
        if int(base.DrawingObjectType) != session.k.constants['ksDrLineSeg']:
            continue
        base.DrawingObjectParamType = -7
        line = session.cast(base, 'ILineSegment')
        points = [[float(line.X1), float(line.Y1)], [float(line.X2), float(line.Y2)]]
        if abs(points[0][1]-points[1][1]) < 1e-7 and math.dist(*points) > 1.:
            candidates.append((points[0][1], -math.dist(*points), reference, base))
    need(candidates, 'No visible horizontal material line in inserted synthetic component')
    candidates.sort(key=lambda item: item[:3])
    need(len(candidates) == 1 or abs(candidates[0][0]-candidates[1][0]) > 1e-7,
         'Ambiguous bottom material edge')
    return candidates[0][3]


def snapshot(session, drawing, model, number, part_path):
    session.guard()
    v, av = view(session, drawing, number)
    leaders = session.cast(v, 'ISymbols2DContainer').Leaders
    need(leaders.Count == 1, 'Synthetic view must contain exactly one native leader')
    leader = leaders.Leader(0)
    leader_obj = session.cast(leader, 'IDrawingObject')
    need(str(session.cast(leader, 'IDrawingObject1').GetView().Reference) == str(v.Reference),
         'Leader not owned by explicit synthetic view')
    branches = session.cast(leader, 'IBranchs')
    need(branches.BranchCount == 1, 'Synthetic leader lost its single branch')
    material = projected_bottom(session, drawing, model, number, part_path)
    line = session.cast(material, 'ILineSegment')
    data = {}
    for name, mode in [('view', -7), ('paper', -2)]:
        leader_obj.DrawingObjectParamType = mode
        material.DrawingObjectParamType = mode
        data[name] = {'tip': [float(branches.BranchX(0)), float(branches.BranchY(0))],
                      'shelf': [float(branches.X0), float(branches.Y0)],
                      'points': [[float(line.X1), float(line.Y1)], [float(line.X2), float(line.Y2)]]}
    leader_obj.DrawingObjectParamType = -7
    material.DrawingObjectParamType = -7
    base = branches.GetBaseObject(0)
    constraints = []
    for raw in values(session.cast(leader, 'IDrawingObject1').Constraints):
        c = session.cast(raw, 'IParametriticConstraint')
        constraints.append({'type': int(c.ConstraintType), 'valid': bool(c.Valid),
                            'index': int(c.Index), 'segment_index': int(c.SegmentIndex),
                            'partner_index': int(c.PartnerIndex),
                            'partner_segment_index': int(c.PartnerSegmentIndex)})
    part = component(session, model, part_path)
    data.update(leader_reference=str(leader_obj.Reference), material_reference=str(material.Reference),
                base_reference=None if base is None else str(base.Reference),
                base_valid=bool(base is not None and base.Valid), constraints=constraints,
                base_matches_material=bool(base is not None and str(base.Reference) == str(material.Reference)),
                field=str(session.cast(leader, 'IPositionLeader').Positions.Str),
                source=str(av.SourceFileName), source_sha256=sha(av.SourceFileName),
                part_matrix=list(part.Placement.GetMatrix3D()), part_fixed=bool(part.Fixed),
                view_pose=[float(v.X), float(v.Y), float(v.Scale), float(v.Angle)],
                projection_matrix=list(av.ProjectionMatrix))
    need(data['view_pose'][2] > 0, 'Nonpositive synthetic view scale')
    need(abs(data['view_pose'][3]) < 1e-8, 'Fixture requires an unrotated view')
    x, y, scale, _ = data['view_pose']
    errors = []
    for local, paper in zip([data['view']['tip'], *data['view']['points']],
                            [data['paper']['tip'], *data['paper']['points']], strict=True):
        errors.append(math.dist([x+scale*local[0], y+scale*local[1]], paper))
    data['native_coordinate_frame_residual'] = max(errors)
    need(max(errors) < 1e-5, 'Native -7/-2 coordinate witnesses disagree: '+json.dumps(data))
    session.guard()
    return data


def raster(session, drawing, path):
    need(not path.exists(), 'No raster overwrite')
    native = session.k.api.ksDocument2D(session.k.app.ksGetDocumentByReference(
        session.doc(drawing).Reference))
    settings = native.RasterFormatParam()
    need(settings is not None and settings.Init(), 'Cannot initialize own raster export')
    settings.format = session.k.constants['ksRasterFormatPNG']
    settings.colorBPP, settings.extResolution = 24, 150
    need(native.SaveAsToRasterFormat(str(path), settings), 'Own raster export failed')
    need(path.is_file() and path.stat().st_size > 0, 'Empty own raster export')
    return {'path': str(path), 'sha256': sha(path)}


def measurement(before, after):
    a, b = before['paper'], after['paper']
    delta = lambda p, q: [p[i]-q[i] for i in (0, 1)]
    pairings = [[delta(points[i], a['points'][i]) for i in (0, 1)]
                for points in (b['points'], b['points'][::-1])]
    shifts = min(pairings, key=lambda ds: math.dist(ds[0], ds[1]))
    need(math.dist(*shifts) < 1e-5, 'Material segment did not translate rigidly')
    tip_delta = delta(b['tip'], a['tip'])
    return {'material_delta': shifts[0], 'tip_delta': tip_delta,
            'material_displacement': math.hypot(*shifts[0]),
            'residual': math.dist(shifts[0], tip_delta),
            'follows': math.dist(shifts[0], tip_delta) < 1e-5}


def run_cases(session, report, event):
    from kompas_mcp import assemblies
    from kompas_mcp.models import ExtrusionSpec, SketchSpec

    root, k = session.root, session.k
    root.mkdir(parents=True, exist_ok=False)
    part_path = root/'synthetic-part.m3d'
    event('before_create_synthetic_part')
    plate = session.create('part')
    sketch = session.call(k.sketch, plate['document_id'], SketchSpec(
        name='Synthetic rectangle', curves=[{'kind': 'polyline',
                                             'points': [[0., 0.], [32., 0.], [32., 24.], [0., 24.]]}]))
    session.call(k.feature, plate['document_id'], ExtrusionSpec(
        name='Synthetic plate', sketch_id=sketch['sketch_id'], depth=6.))
    volume = session.call(k.measure, plate['document_id'])
    need(math.isclose(volume['volume_mm3'], 32*24*6, abs_tol=1e-5), 'Wrong synthetic part volume')
    report['synthetic_part'] = session.save(plate, part_path)
    session.close(plate)
    part_sha = sha(part_path)
    report['cases'] = []

    strategies = session.config.get('strategies', ['same_filename', 'unique_revision'])
    need(strategies and len(strategies) == len(set(strategies))
         and set(strategies) <= {'same_filename', 'unique_revision'}, 'Invalid explicit strategy set')
    for strategy in strategies:
        folder = root/strategy
        folder.mkdir(exist_ok=False)
        source0, drawing_path = folder/'source-r0.a3d', folder/'leader.cdw'
        case = {'strategy': strategy, 'states': {}, 'measurements': {}, 'images': {}}
        report['cases'].append(case)
        event('before_create_baseline', strategy=strategy)
        model = session.create('assembly')
        session.call(session.documents.insert_component, k, model['document']['handle'],
                     str(part_path), linked=True)
        need(session.call(k.document(model['document_id']).RebuildDocument), 'New assembly rebuild failed')
        session.save(model, source0)
        matrix0 = list(component(session, model, part_path).Placement.GetMatrix3D())
        session.close(model)
        source0_sha = sha(source0)
        model = session.open(source0, read_only=True)
        drawing = session.create('drawing')
        created = session.call(session.documents.create_standard_views, k,
            drawing['document']['handle'], str(source0), ['front'], x=75., y=150., scale=2.)
        need(created['created_count'] == 1, 'Expected one own projection')
        number = created['created_views'][0]['number']
        v, _ = view(session, drawing, number)
        edge = projected_bottom(session, drawing, model, number, part_path)
        edge.DrawingObjectParamType = -7
        line = session.cast(edge, 'ILineSegment')
        tip = [(float(line.X1)+float(line.X2))/2, (float(line.Y1)+float(line.Y2))/2]
        event('before_create_position_leader', strategy=strategy)
        leader = session.cast(v, 'ISymbols2DContainer').Leaders.Add(k.constants['ksDrPosLeader'])
        need(leader is not None, 'PositionLeader Add failed')
        session.cast(leader, 'IDrawingObject').DrawingObjectParamType = -7
        branches = session.cast(leader, 'IBranchs')
        branches.X0, branches.Y0 = tip[0]+12., tip[1]+14.
        need(branches.AddBranchByPoint(0, *tip), 'Synthetic branch creation failed')
        position = session.cast(leader, 'IPositionLeader')
        position.Positions.Str = '1'  # geometry-only fixture; no specification/UUID acceptance claim
        position.Horizontally, position.ShelfVisible = True, True
        need(leader.Update(), 'Own leader Update failed')
        case['SetBaseObject_return'] = branches.SetBaseObject(0, edge, -1)
        need(case['SetBaseObject_return'] is True and leader.Update(), 'Base setter/Update failed')
        session.guard()
        baseline = snapshot(session, drawing, model, number, part_path)
        need(baseline['base_valid'] and baseline['base_matches_material'], 'Initial base differs')
        need(any(c['type'] == 12 and c['valid'] for c in baseline['constraints']), 'No valid association')
        case['states']['baseline'] = baseline
        session.save(drawing, drawing_path)
        case['images']['baseline'] = session.call(raster, session, drawing, folder/'baseline.png')
        session.close(drawing)
        session.close(model)
        del leader, branches, position, edge, line, v
        need(sha(source0) == source0_sha, 'Baseline source changed while drawing was built')
        event('baseline_saved', strategy=strategy)

        model = session.open(source0)
        drawing = session.open(drawing_path)
        saved_baseline = snapshot(session, drawing, model, number, part_path)
        case['states']['baseline_reopened'] = saved_baseline
        need(math.dist(baseline['paper']['tip'], saved_baseline['paper']['tip']) < 1e-5,
             'Baseline tip failed to persist')
        session.close(model)
        source1 = source0
        if strategy == 'unique_revision':
            source1 = folder/'source-r1.a3d'
            need(not source1.exists(), 'Revision output already exists')
            shutil.copy2(source0, source1)  # byte-copy BEFORE editing, immutable r0 retained
            need(sha(source1) == source0_sha, 'Revision bytecopy mismatch')
        model = session.open(source1)
        matrix1 = list(matrix0)
        matrix1[12] += 7.
        matrix1[13] += 4.

        def place(model, matrix, label, strategy=strategy, case=case):
            event('before_source_placement', strategy=strategy, label=label)
            expected = list(component(session, model, part_path).Placement.GetMatrix3D())
            result = session.call(assemblies.place_components, k, model['document']['handle'],
                                  str(root), [{'index': 0, 'expected': expected, 'matrix': matrix}],
                                  dry_run=False)
            case.setdefault('placements', []).append({'label': label, 'result': result})
            actual = list(component(session, model, part_path).Placement.GetMatrix3D())
            need(max(abs(x-y) for x, y in zip(actual, matrix, strict=True)) < 1e-7,
                 'Synthetic placement readback differs')
            session.save(model, session.doc(model).PathName)

        def rebuild(drawing, source, label, strategy=strategy, case=case, number=number):
            event('before_own_view_rebuild', strategy=strategy, label=label)
            session.doc(drawing).Active = True
            _, av = view(session, drawing, number)
            if key(av.SourceFileName) != key(source):
                av.SourceFileName = str(source)
                update = session.call(av.Update)
                need(key(av.SourceFileName) == key(source), 'Revision source rebind failed')
                case.setdefault('source_updates', []).append({'label': label, 'returned': update})
            need(session.call(av.Rebuild), 'Own view rebuild failed')
            own2d = session.cast(session.doc(drawing), 'IKompasDocument2D1')
            need(session.call(own2d.RebuildDocument), 'Own 2D document rebuild failed')

        place(model, matrix1, 'moved')
        rebuild(drawing, source1, 'moved')
        moved = snapshot(session, drawing, model, number, part_path)
        case['states']['moved_immediate'] = moved
        case['measurements']['moved_immediate'] = measurement(saved_baseline, moved)
        need(case['measurements']['moved_immediate']['material_displacement'] > 1.,
             'Invalid stimulus: actual material did not move')
        session.save(drawing, drawing_path)
        case['images']['moved'] = session.call(raster, session, drawing, folder/'moved.png')
        source1_sha = sha(source1)
        session.close(drawing)
        session.close(model)
        event('moved_saved', strategy=strategy,
              follows=case['measurements']['moved_immediate']['follows'])

        case['restoration'] = []
        for cycle in range(2):
            model = session.open(source1, read_only=True)
            drawing = session.open(drawing_path, read_only=True)
            state = snapshot(session, drawing, model, number, part_path)
            case['states'][f'moved_ro_{cycle}'] = state
            case['measurements'][f'moved_ro_{cycle}'] = measurement(saved_baseline, state)
            session.close(drawing)
            session.close(model)
            need(sha(source1) == source1_sha, 'RO observation changed moved source')

        restore_source = source0
        if strategy == 'unique_revision':
            restore_source = folder/'source-r2.a3d'
            need(not restore_source.exists(), 'Restore revision already exists')
            shutil.copy2(source1, restore_source)
            need(sha(restore_source) == source1_sha, 'Restore revision bytecopy mismatch')
        model = session.open(restore_source)
        drawing = session.open(drawing_path)
        place(model, matrix0, 'restored')
        rebuild(drawing, restore_source, 'restored')
        restored = snapshot(session, drawing, model, number, part_path)
        case['states']['restored_immediate'] = restored
        session.save(drawing, drawing_path)
        case['images']['restored'] = session.call(raster, session, drawing, folder/'restored.png')
        session.close(drawing)
        session.close(model)
        for cycle in range(2):
            model = session.open(restore_source, read_only=True)
            drawing = session.open(drawing_path, read_only=True)
            state = snapshot(session, drawing, model, number, part_path)
            case['states'][f'restored_ro_{cycle}'] = state
            relative = measurement(saved_baseline, state)
            source_returned = max(abs(a-b) for a, b in zip(state['part_matrix'], matrix0,
                                                         strict=True)) < 1e-7
            source_returned = source_returned and state['part_fixed'] == saved_baseline['part_fixed']
            case['restoration'].append({'cycle': cycle, 'source_placement_restored': source_returned,
                'relative_tip_material_restored': relative['follows'],
                'absolute_page_tip_restored': math.dist(state['paper']['tip'],
                                                        saved_baseline['paper']['tip']) < 1e-5,
                'paper_return_measurement': relative})
            session.close(drawing)
            session.close(model)
        if strategy == 'unique_revision':
            need(sha(source0) == source0_sha and sha(source1) == source1_sha,
                 'Prior unique source revisions were modified')
        need(sha(part_path) == part_sha, 'Immutable synthetic part changed')
        case['passed_motion_cycle'] = all(m['follows'] for m in case['measurements'].values())
        case['restored_saved_ro_verified'] = all(r['source_placement_restored']
            and r['relative_tip_material_restored'] for r in case['restoration'])
        event('case_complete', strategy=strategy, follows=case['passed_motion_cycle'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--phase', choices=['discover', 'run', 'cleanup'], required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
    output = Path(config['receipts'])/(args.phase+'.json')
    if output.exists():
        raise RuntimeError('Existing receipt: reconcile, do not replay')
    sources = output.parent/('source-'+args.phase)
    sources.mkdir(parents=True, exist_ok=False)
    for source in [Path(__file__), Path(__file__).with_name('native_owned_session.py')]:
        shutil.copy2(source, sources/source.name)
    started = time.monotonic()
    report = {'phase': 'starting', 'native_mutations_requested': args.phase == 'run', 'events': [],
              'runner_sha256': sha(__file__), 'session_sha256': sha(
                  Path(__file__).with_name('native_owned_session.py'))}

    def flush():
        report['elapsed_seconds'] = time.monotonic()-started
        output.parent.mkdir(parents=True, exist_ok=True)
        tmp = output.with_suffix('.tmp')
        tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(output)

    flush()

    def event(stage, **data):
        report['events'].append({'stage': stage, 'seconds': time.monotonic()-started, **data})
        flush()
        print(stage, json.dumps(data, ensure_ascii=True), flush=True)

    session = None
    try:
        session = NativeOwnedSession(config, config.get('cleanup_ledger')
                                     if args.phase == 'cleanup' else None)
        report.update(application=session.identity, version=session.version,
                      baseline=list(session.baseline.values()))
        event('fresh_guarded_session_ready')
        if args.phase == 'run':
            run_cases(session, report, event)
        if args.phase == 'cleanup':
            for entry in list(session.owned.values())[::-1]:
                session.close(entry['result'])
            event('own_failed_run_RO_remnants_closed')
        report.update(application=session.identity, version=session.version,
                      baseline=list(session.baseline.values()), after=session.guard(),
                      preservation=session.verify_files(), phase=(
                          'complete_synthetic_comparison' if args.phase == 'run' else
                          'complete_owned_RO_cleanup' if args.phase == 'cleanup' else
                          'complete_readonly_discovery'))
    except Exception:  # noqa: BLE001 - preserve native failure without replay or cleanup mutation
        report.update(phase='failed', error=traceback.format_exc())
    finally:
        if session is not None:
            report['owned_remaining'] = [{'reference': ref, **{
                k: v for k, v in e.items() if k != 'result'}}
                for ref, e in session.owned.items()]
            try:
                report['final_guard'] = session.guard()
                report['preservation'] = session.verify_files()
            except Exception:  # noqa: BLE001 - no cleanup/replay when ownership guard fails
                report['phase_before_preservation_error'] = report['phase']
                report['phase'] = 'failed_preservation'
                report['preservation_error'] = traceback.format_exc()
            session.release()
        flush()
    print(json.dumps({'phase': report['phase'], 'receipt': str(output)}, ensure_ascii=True))
    return 1 if report['phase'].startswith('failed') else 0


if __name__ == '__main__':
    raise SystemExit(main())
