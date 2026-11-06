"""Collision-free sketch namespaces from a fresh native variable inventory."""

import re


def reserve_prefix(prefix, existing):
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", prefix):
        raise ValueError("Use a short ASCII variable prefix")
    names = {name.casefold() for name in existing}
    for index in range(1, 10001):
        candidate = prefix if index == 1 else f"{prefix}_{index}"
        if not any(name == candidate.casefold() or name.startswith(candidate.casefold() + "_")
                   for name in names):
            return candidate
    raise ValueError("No unused variable namespace available")


def native_names(k, document_id):
    from .parameters import _collection

    collection = _collection(k, document_id, None)
    return {collection.GetByIndex(i).name for i in range(collection.GetCount())}


def ensure_unused(k, document_id, name):
    from .parameters import _collection

    collection = _collection(k, document_id, None)
    names = {collection.GetByIndex(i).name.casefold() for i in range(collection.GetCount())}
    # Native lookup can include names not enumerated by a cached parent table.
    if name.casefold() in names or collection.GetByName(name, True, False) is not None:
        raise ValueError(f"Driving variable already exists; refusing reuse: {name}")
