"""Bounded exact-byte file placement plan for explicit relative native references.

No filesystem access, CAD parsing, connections or native acceptance. Callers
must extract complete stored edges and prove their exact canonical targets from
pinned evidence; filenames or equal hashes alone are never identity evidence.
"""

import posixpath
import re
from collections import defaultdict, deque
from pathlib import PureWindowsPath


def _canonical(value):
    if (type(value) is not str or not value or '\\' in value or value.startswith('/')
            or PureWindowsPath(value).drive or '|' in value or '\x00' in value
            or any(x in {'', '.', '..'} for x in value.split('/'))):
        raise ValueError('Canonical archive paths must be explicit normalized relative paths')
    for component in value.split('/'):
        device = component.split('.')[0].rstrip(' .').upper()
        if (re.search(r'[<>:"|?*\x00-\x1f]', component) or component.endswith((' ', '.'))
                or device in {'CON', 'PRN', 'AUX', 'NUL'}
                or re.fullmatch(r'(COM|LPT)[1-9¹²³]', device)):
            raise ValueError('Destination is ambiguous or invalid on Windows')
    return value


def plan_reference_copies(files, edges, *, prefix, max_files=5000, max_edges=20000):
    """Close stored-path destinations using explicitly pinned byte-copy aliases.

    ``files`` maps canonical archive paths to SHA256. Each edge declares parent,
    stored relative path, canonical target and both endpoint hashes. ``prefix``
    reserves space inside an owned root for ancestor-relative destinations.
    Conflicting origins fail even if their bytes have equal hashes. No CAD file
    contents are rewritten and no existing files may be adopted by a stager.
    """
    _canonical(prefix)
    if (type(files) is not dict or not files or type(edges) is not list
            or type(max_files) is not int or not 1 <= max_files <= 100000
            or type(max_edges) is not int or not 1 <= max_edges <= 500000
            or len(files) > max_files or len(edges) > max_edges):
        raise ValueError('Explicit files/edge inventories and finite positive bounds required')
    for name, digest in files.items():
        _canonical(name)
        if type(digest) is not str or not re.fullmatch('[a-f0-9]{64}', digest):
            raise ValueError('Every archive file requires a pinned SHA256')
    if len({p.casefold() for p in files}) != len(files):
        raise ValueError('Canonical paths collide on the destination filesystem')
    indexed = defaultdict(list)
    for edge in edges:
        if type(edge) is not dict or set(edge) != {
                'parent', 'stored', 'target', 'parent_sha256', 'target_sha256'}:
            raise ValueError('Complete explicit edge endpoints and hashes required')
        parent, target, stored = edge['parent'], edge['target'], edge['stored']
        if (parent not in files or target not in files or edge['parent_sha256'] != files[parent]
                or edge['target_sha256'] != files[target]):
            raise ValueError('Edge canonical identity or endpoint hashes differ from archive pins')
        if (type(stored) is not str or not stored or '\x00' in stored or '|' in stored
                or PureWindowsPath(stored).drive or stored.startswith(('/', '\\'))):
            raise ValueError('Absolute/drive-relative/library paths need a different protocol')
        indexed[parent].append(edge)
    placements = {prefix+'/'+p: p for p in files}
    by_case = {p.casefold(): p for p in placements}
    queue, expanded, observations = deque(placements), set(), []
    while queue:
        parent = queue.popleft()
        if parent.casefold() in expanded:
            continue
        expanded.add(parent.casefold())
        origin = placements[parent]
        for edge in indexed[origin]:
            if len(observations) >= max_edges:
                raise ValueError('Expanded reference-edge bound exceeded')
            destination = posixpath.normpath(posixpath.join(
                posixpath.dirname(parent), edge['stored'].replace('\\', '/')))
            if destination in {'.', '..'} or destination.startswith(('../', '/')):
                raise ValueError('Stored reference escapes the owned root')
            _canonical(destination)
            previous = by_case.get(destination.casefold())
            target = edge['target']
            if previous is not None and placements[previous] != target:
                raise ValueError('Conflicting canonical origins at one destination; same SHA is insufficient')
            if previous is None:
                if len(placements) >= max_files:
                    raise ValueError('Expanded file-placement bound exceeded')
                placements[destination] = target
                by_case[destination.casefold()] = destination
                queue.append(destination)
            observations.append({'parent': parent, 'stored': edge['stored'],
                                 'destination': previous or destination, 'canonical_target': target})
    # A file cannot simultaneously be a parent directory for another placement.
    names = set(by_case)
    for name in placements:
        pieces = name.casefold().split('/')
        if any('/'.join(pieces[:i]) in names for i in range(1, len(pieces))):
            raise ValueError('File/directory destination collision')
    return {'status': 'ready_for_exclusive_filesystem_stage', 'prefix': prefix,
            'placements': {p: {'origin': origin, 'sha256': files[origin]}
                           for p, origin in placements.items()},
            'edges': observations, 'original_files': len(files), 'cad_bytes_rewritten': 0,
            'native_acceptance': 'pending', 'portable_saved_verified': False}
