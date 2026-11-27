"""Read-only fresh native inventory and bounded installed SDK evidence.

Explicit exclusive ownership is required. Does not create or change CAD documents.
Private configuration/receipts are never checked into the public repository.
"""

import argparse
import html
import inspect
import json
import re
import traceback
import zipfile
from pathlib import Path

from native_owned_session import inventory, need, process_identity, sha

TOPICS = [
    'ikompasdocument3d_toppart.html', 'ikompasdocument3d1_maintoppart.html',
    'ikompasdocument3d1_editobject.html', 'ispecificationdescriptions_add.html',
    'ispecificationdescription_baseobjects.html', 'ispecificationdescription_delegatemode.html',
    'ispecificationbaseobject_geometry.html', 'ispecificationbaseobject_includegeometry.html',
    'ispecificationbaseobject_syncronizewithproperties.html', 'ispecificationobject_update.html',
    'ispecificationbaseobject_uniquemetaobjectkey.html', 'ipropertykeeper_uniquemetaobjectkey.html',
    'ikompasdocument1_getobjectid.html', 'ikompasdocument1_findobjectbyid.html',
    'ipropertykeeper_getpropertyvalue.html', 'ipropertykeeper_setpropertyvalue.html',
    'ipropertymng_getproperty.html', 'ipart7_createspcobjects.html',
    'ksspecification_ksgetspcpropertyfill.html', 'ksspecification_kssetspcpropertyfill.html',
]


def discover(config):
    import pythoncom
    import win32api
    import win32event
    from win32com import client

    mutex = win32event.CreateMutex(None, True, 'Local\\CodexKompasSdkNativeWorker')
    need(win32api.GetLastError() != 183, 'Another synthetic worker owns native mutex')
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    try:
        sdk = Path(config['sdk'])
        modules = {}
        for name in ('kAPI5', 'kAPI7', 'ksConstants', 'ksConstants3D'):
            tlb = pythoncom.LoadTypeLib(str(sdk/'lib'/(name+'.tlb')))
            guid, lcid, _, major, minor, *_ = tlb.GetLibAttr()
            modules[name] = client.gencache.EnsureModule(guid, lcid, major, minor)
        raw = client.GetActiveObject('KOMPAS.Application.5')
        wrapper = modules['kAPI5'].KompasObject
        app5 = wrapper(raw._oleobj_.QueryInterface(wrapper.CLSID, pythoncom.IID_IDispatch))
        app = app5.ksGetApplication7()
        identity = process_identity(app)
        docs, before = inventory(app)
        extras = [{'reference': str(d.Reference), 'active': bool(d.Active)} for d in docs]
        disk = {r['path']: sha(r['path']) for r in before if r['path'] and Path(r['path']).is_file()}
        topics = {}
        with zipfile.ZipFile(sdk/'Help'/'KOMPAS_SDK_ru-RU.zip') as archive:
            available = set(archive.namelist())
            for name in TOPICS:
                if name in available:
                    text = archive.read(name).decode('utf-8-sig')
                    text = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', text, flags=re.IGNORECASE | re.DOTALL)
                    topics[name] = ' '.join(html.unescape(re.sub('<[^>]+>', ' ', text)).split())
        classes = {}
        for name in ('IPart7', 'IKompasDocument3D1', 'ISpecificationDescriptions',
                     'ISpecificationBaseObject', 'ISpecificationObject', 'IPropertyKeeper',
                     'IPropertyMng', 'IKompasDocument1'):
            cls = getattr(modules['kAPI7'], name, None)
            if cls:
                classes[name] = {'get': list(getattr(cls, '_prop_map_get_', {})),
                                 'set': list(getattr(cls, '_prop_map_put_', {})),
                                 'methods': [n for n in dir(cls) if not n.startswith('_')
                                             and callable(getattr(cls, n))]}
        _, after = inventory(app)
        need(identity == process_identity(app) and before == after, 'Discovery state changed')
        need(all(sha(p) == h for p, h in disk.items()), 'Open document disk file changed')
        return {'phase': 'complete_readonly_discovery', 'application': identity,
                'version': list(app5.ksGetSystemVersion()), 'before': {'documents': before},
                'after': {'documents': after}, 'active_observations': extras,
                'open_file_sha256': disk, 'topics': topics, 'classes': classes,
                'api5_specification_signatures': {name: str(inspect.signature(getattr(
                    modules['kAPI5'].ksSpecification, name))) for name in [
                        'ksGetSpcPropertyFill', 'ksSetSpcPropertyFill']},
                'missing_topics': [n for n in TOPICS if n not in topics],
                'native_mutations': 0}
    finally:
        win32event.ReleaseMutex(mutex)
        win32api.CloseHandle(mutex)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--terminal')
    args = parser.parse_args()
    output = Path(args.output)
    need(not output.exists(), 'Existing discovery receipt; reconcile, do not replay')
    try:
        report = discover(json.loads(Path(args.config).read_text(encoding='utf-8-sig')))
    except Exception:  # noqa: BLE001 - preserve failed discovery without retry
        report = {'phase': 'failed_readonly_discovery', 'error': traceback.format_exc()}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.terminal:
        terminal = Path(args.terminal)
        need(not terminal.exists(), 'Existing terminal receipt')
        terminal.write_text(json.dumps({
            'phase': 'failed' if report['phase'].startswith('failed') else 'complete',
            'artifacts': [{'path': str(output), 'sha256': sha(output)}],
            'verification': {'artifacts': 'verified', 'physical_acceptance': 'pending'},
        }, indent=2), encoding='utf-8')
    print(json.dumps({'phase': report['phase'], 'receipt': str(output)}))
    return 1 if report['phase'].startswith('failed') else 0


if __name__ == '__main__':
    raise SystemExit(main())
