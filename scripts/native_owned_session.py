"""Attach-only single-STA harness for explicit synthetic native acceptance.

No native imports/actions at module import. Configuration and private receipts
stay outside the public repository. Never adopt a pre-existing document.
"""

import ctypes
import hashlib
import json
import os
from pathlib import Path


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def key(path):
    return os.path.normcase(os.path.realpath(path)) if path else ''


def file_tree(roots):
    result = {}
    for root in roots:
        folder = Path(root)
        need(folder.is_dir(), 'Protected tree absent')
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                result[key(path)] = sha(path)
    return result


def require_disjoint_root(root, protected_roots):
    destination = Path(root).resolve()
    for folder in protected_roots:
        protected = Path(folder).resolve()
        need(not destination.is_relative_to(protected)
             and not protected.is_relative_to(destination),
             'Synthetic root must be disjoint from protected/installed trees')


def process_identity(app):
    from ctypes import wintypes

    import win32process

    hwnd = int(app.MainWindowHandle)
    need(hwnd > 0, 'No observed native window')
    pid = int(win32process.GetWindowThreadProcessId(hwnd)[1])
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),)*4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenProcess(4096, False, pid)
    need(handle, 'Cannot query observed CAD process')
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        need(kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)),
             'Process creation time unavailable')
        created = (int(times[0].dwHighDateTime) << 32) | int(times[0].dwLowDateTime)
    finally:
        kernel.CloseHandle(handle)
    need(created > 0, 'Invalid process creation time')
    return {'pid': pid, 'hwnd': hwnd, 'process_creation_time_100ns': created}


def inventory(app):
    count = int(app.Documents.Count)
    docs = [app.Documents.Item(i) for i in range(count)]
    need(all(d is not None for d in docs) and app.Documents.Count == count,
         'Unstable native document inventory')
    rows = [{'reference': str(d.Reference), 'path': str(d.PathName),
             'kind': int(d.DocumentType), 'changed': bool(d.Changed),
             'read_only': bool(d.ReadOnly), 'visible': bool(d.Visible)} for d in docs]
    need(len({r['reference'] for r in rows}) == count, 'Duplicate native document references')
    return docs, rows


def validate_protected_handover(config, identity, protected, expected):
    """Keep legacy clean-RO default; explicitly pin dirty user documents if requested."""
    policy = config.get('protected_document_policy', 'clean_saved_ro')
    need(policy in {'clean_saved_ro', 'preserve_exact_state'}, 'Unknown protected document policy')
    if policy == 'preserve_exact_state':
        need(config.get('expected_application') == identity,
             'Exact-state protection requires fresh process identity')
        by_reference = lambda rows: sorted(rows, key=lambda row: row['reference'])
        need(by_reference(protected) == by_reference(expected),
             'Exact-state documents differ from fresh handover')
        need(all(r['path'] for r in protected), 'Exact-state protection requires saved file paths')
    else:
        need(all(r['read_only'] and not r['changed'] and r['path'] for r in protected),
             'Protected handover must contain only clean saved RO documents')


class NativeOwnedSession:
    def __init__(self, config, cleanup_ledger=None):
        import pythoncom
        import win32api
        import win32event
        from win32com import client

        from kompas_mcp import documents
        from kompas_mcp.backend import Kompas

        self.mutex = win32event.CreateMutex(None, True, 'Local\\CodexKompasSdkNativeWorker')
        need(win32api.GetLastError() != 183, 'Another synthetic native worker owns the mutex')
        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        self.root = Path(config['native_root']).resolve()
        require_disjoint_root(self.root, config['protected_roots'])
        self.config, self.owned = config, {}
        self.k, self.documents = Kompas(), documents
        sdk = Path(config['sdk'])
        modules = {}
        for name in ('kAPI5', 'kAPI7', 'ksConstants', 'ksConstants3D'):
            tlb = pythoncom.LoadTypeLib(str(sdk/'lib'/(name+'.tlb')))
            guid, lcid, _, major, minor, *_ = tlb.GetLibAttr()
            modules[name] = client.gencache.EnsureModule(guid, lcid, major, minor)
        # GetActiveObject cannot start a new CAD instance or replace the observed one.
        raw = client.GetActiveObject('KOMPAS.Application.5')
        wrapper = modules['kAPI5'].KompasObject
        self.k.app = wrapper(raw._oleobj_.QueryInterface(wrapper.CLSID, pythoncom.IID_IDispatch))
        self.k.api, self.k.sdk, self.k.modules = modules['kAPI5'], sdk, modules
        for name in ('ksConstants', 'ksConstants3D'):
            self.k.constants.update({k: v for k, v in vars(modules[name].constants).items()
                                     if not k.startswith('_')})
        self.k.connect = lambda *a, **kw: {'connected': True, 'attached_existing_only': True}
        self.app = self.k.app.ksGetApplication7()
        self.identity = process_identity(self.app)
        self.version = list(self.k.app.ksGetSystemVersion())
        need(len(self.version) > 1 and self.version[1] == 25, 'Synthetic recipe requires v25')
        live_docs, rows = inventory(self.app)
        handover = json.loads(Path(config['handover']).read_text(encoding='utf-8-sig'))
        expected = handover['after']['documents']
        normalize = lambda rs: sorted((key(r['path']), r['kind'], r['read_only'],
                                      r['changed'], r['visible']) for r in rs)
        adopted = cleanup_ledger or []
        if adopted:
            need(self.identity == config['cleanup_expected_application'],
                 'Cleanup process differs from independently discovered run identity')
            receipt = Path(config['cleanup_from_receipt'])
            need(sha(receipt) == config['cleanup_receipt_sha256'], 'Cleanup receipt changed')
            failure = json.loads(receipt.read_text(encoding='utf-8-sig'))
            need(failure['phase'] == 'failed' and not failure.get('preservation_error'),
                 'Cleanup requires reconciled failed receipt with a passing preservation guard')
            narrow = lambda rs: sorted((key(r['path']), r['kind'], r['read_only']) for r in rs)
            need(narrow(adopted) == narrow(failure['owned_remaining']),
                 'Cleanup ledger differs from exact failed-run remainder')
            previous = {r['reference']: r for r in failure['final_guard']}
            for row in adopted:
                self.inside(row['path'])
                need(row == previous.get(row['reference']), 'Cleanup native reference/state differs')
        need(normalize(rows) == normalize(expected+adopted),
             'Fresh inventory differs from explicit handover and scoped cleanup ledger')
        protected = [r for r in rows if key(r['path']) in {key(e['path']) for e in expected}]
        validate_protected_handover(config, self.identity, protected, expected)
        self.baseline = {r['reference']: r for r in protected}
        for row in adopted:
            need(row['read_only'] or config.get('cleanup_allow_dirty_owned') is True,
                 'This reconciliation permits closing only own RO remnants by default')
            actual = next((r for r in rows if r['reference'] == row['reference']), None)
            need(actual == row, 'Fresh cleanup candidate differs')
            doc = next(d for d in live_docs if str(d.Reference) == row['reference'])
            result = {'document': self.k.pack(doc, row['reference'])}
            self.k.owned_documents.add(row['reference'])
            self.owned[row['reference']] = {**row, 'result': result}
        self.protected_files = file_tree(config['protected_roots'])
        for path, expected_sha in handover.get('open_file_sha256', {}).items():
            need(self.protected_files.get(key(path)) == expected_sha,
                 'Protected disk file differs from fresh discovery')
        import kompas_mcp

        self.install_roots = [str(Path(kompas_mcp.__file__).parent), str(sdk/'lib')]
        require_disjoint_root(self.root, self.install_roots)
        self.installed_files = file_tree(self.install_roots)
        need(all(key(r['path']) in self.protected_files for r in protected),
             'Protected document outside pinned immutable trees')
        self.guard()

    def guard(self):
        need(process_identity(self.app) == self.identity, 'CAD process identity changed')
        _, rows = inventory(self.app)
        actual = {r['reference']: r for r in rows}
        need({ref: actual.get(ref) for ref in self.baseline} == self.baseline,
             'Pre-existing protected document changed')
        need(set(actual) == set(self.baseline) | set(self.owned), 'Unexpected native documents')
        for ref, entry in self.owned.items():
            row = actual[ref]
            need(key(row['path']) == key(entry['path']) and row['kind'] == entry['kind']
                 and row['read_only'] == entry['read_only'], 'Owned document identity drift')
        return rows

    def inside(self, path):
        p = Path(path).resolve()
        need(p != self.root and p.is_relative_to(self.root), 'Path outside isolated synthetic root')
        return p

    def track(self, result):
        doc = self.k.handles[result['document']['handle']]
        ref = str(doc.Reference)
        need(ref not in self.baseline and ref not in self.owned, 'Creation/open reused an existing doc')
        if doc.PathName:
            self.inside(doc.PathName)
        self.owned[ref] = {'path': str(doc.PathName), 'kind': int(doc.DocumentType),
                           'read_only': bool(doc.ReadOnly), 'result': result}
        self.guard()
        return result

    def create(self, kind):
        self.guard()
        result = self.track(self.documents.create_document(self.k, kind, visible=False))
        self.doc(result).Active = True
        self.guard()
        return result

    def open(self, path, read_only=False):
        path = self.inside(path)
        rows = self.guard()
        need(not any(key(r['path']) == key(path) for r in rows), 'Already open synthetic path')
        return self.track(self.documents.open_document(self.k, str(path),
                          read_only=read_only, visible=False, reuse_existing=False))

    def doc(self, result):
        doc = self.k.handles[result['document']['handle']]
        need(str(doc.Reference) in self.owned, 'No owned document for this handle')
        return doc

    def save(self, result, path):
        self.guard()
        doc, target = self.doc(result), self.inside(path)
        need(not doc.ReadOnly, 'Cannot save a read-only document')
        need(not target.exists() or key(doc.PathName) == key(target),
             'Cannot overwrite a different existing file, even inside the synthetic root')
        target.parent.mkdir(parents=True, exist_ok=True)
        # Explicitly owned native SaveAs is void. File/path/Changed are the gates.
        returned = doc.SaveAs(str(target))
        need(returned is None, 'Unexpected Automation SaveAs contract')
        self.owned[str(doc.Reference)]['path'] = str(doc.PathName)
        need(key(doc.PathName) == key(target) and not doc.Changed
             and target.is_file() and target.stat().st_size > 0, 'Unconfirmed owned save')
        self.guard()
        return {'path': str(target), 'sha256': sha(target), 'SaveAs_return': returned}

    def close(self, result):
        self.guard()
        doc = self.doc(result)
        ref = str(doc.Reference)
        self.documents.close_document(self.k, result['document']['handle'], discard_changes=True)
        del self.owned[ref]
        self.guard()

    def cast(self, obj, interface):
        return self.documents._cast(self.k, obj, interface)

    def call(self, action, *args, **kwargs):
        self.guard()
        result = action(*args, **kwargs)
        self.guard()
        return result

    def verify_files(self):
        actual = file_tree(self.config['protected_roots'])
        need(actual == self.protected_files, 'Protected file inventory/SHA changed')
        need(file_tree(self.install_roots) == self.installed_files, 'Installed SDK/package files changed')
        self.guard()
        return {'protected_files': len(actual), 'unchanged': True,
                'installed_files': len(self.installed_files), 'installed_unchanged': True}

    def release(self):
        import win32api
        import win32event

        win32event.ReleaseMutex(self.mutex)
        win32api.CloseHandle(self.mutex)
